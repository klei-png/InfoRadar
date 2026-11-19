from __future__ import annotations

import asyncio
import json
import logging
import os
import litellm

from typing import Any

from src.agent.types import ModelConfig, ToolCall, Usage
from litellm.exceptions import RateLimitError,ServiceUnavailableError,APIConnectionError,Timeout,InternalServerError

logger = logging.getLogger(__name__)
RETRYABLE = (RateLimitError,ServiceUnavailableError,APIConnectionError,Timeout,InternalServerError)

class ModelAdapterError(Exception):
    """ exception type for spec error code  E_MODEL_UNAVAILABLE；Loop layer change to FAILED """

class ModelResponse:
    def __init__(self,content: str | None, tool_calls: list[ToolCall],
                 usage: Usage, model_version: str | None) -> None:
        self.content = content
        self.tool_calls = tool_calls
        self.usage = usage
        self.model_version = model_version

class LiteLLMAdapter:
    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()

    async def complete(self, messages:list[dict[str,Any]],
                       tools: list[dict[str, Any]] | None = None,
                       config: ModelConfig | None = None) -> ModelResponse:
        cfg = config or self.config
        model = cfg.model or os.environ.get("LLM_MODEL","openai/glm-4-air")
        kwargs: dict[str, Any] = dict(
            model=model, messages=messages, temperature=cfg.temperature
        )
        if cfg.max_tokens:
            kwargs["max_tokens"] = cfg.max_tokens
        if tools:
            kwargs["tools"] = tools

        last_parse_error: Exception | None = None
        for parse_attempt in range(2):
            resp = await self._call_with_retry(kwargs, cfg.max_retries)
            try:
                calls = self._normalize_tool_calls(resp)
                break
            except (json.JSONDecodeError,AttributeError,TypeError,KeyError) as e:
                last_parse_error = e
                logger.warning("tool_calls 解析失败(第%d次)：%s",parse_attempt+1,e)
        else:
            raise ModelAdapterError(
                f"E_MODEL_UNAVAILABLE: tool_calls 解析重试耗尽：{last_parse_error}"
            )

        usage = Usage(
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
        )
        try:
            usage.cost_usd = litellm.completion_cost(resp)
        except Exception:
            pass
        content = resp.choices[0].message.content
        return ModelResponse(content=content,tool_calls=calls,
                             usage=usage,model_version=model)
    async def stream(self, message: list[dict[str, Any]],
                     config: ModelConfig | None = None) -> Any:
        raise NotImplementedError

    @staticmethod
    async def _call_with_retry(kwargs:dict[str,Any], max_retries: int) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, max_retries+1):
            try:
                return await litellm.acompletion(**kwargs)
            except RETRYABLE as e:
                last_exc = e
                #不确定retry_after被铺获的值的类型
                wait = getattr(e,"retry_after",None) or 2**attempt
                logger.warning("llm %d/%d 可重试错误：%s; 等%ss",
                               attempt,max_retries,e,wait)
                await asyncio.sleep(wait)
            except litellm.exceptions.BadRequestError as e:
                raise ModelAdapterError(f"E_MODEL_UNAVAILABLE: rejected: {e}") from e
        raise ModelAdapterError(
            f"E_MODEL_UNAVAILABLE: {max_retries}次重试耗尽: {last_exc}"
        ) from last_exc

    @staticmethod
    def _normalize_tool_calls(resp:Any) -> list[ToolCall]:
        raw = resp.choices[0].message.tool_calls or []
        calls: list[ToolCall] = []
        for tc in raw:
            fn = tc.function
            calls.append(ToolCall(
                call_id=tc.id,
                name=fn.name,
                arguments=json.loads(fn.arguments or "{}"),
            ))
        return calls
