import asyncio
import logging
import os
from typing import Any

import litellm

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("LLM_MODEL","openai/glm-4-air")

class LLMError(Exception):
    """LLM gateway common error: retries exhausted or configuration missing"""

async def chat(
        messages: list[dict[str,str]],
        model: str | None = None,
        *,                  #keyword-only parameter separator
        json_mode: bool = False,
        temperature: float = 0.2,
        max_retries: int = 3,
) -> str:
    model = model or DEFAULT_MODEL
    kwargs: dict[str,Any] = dict(
        model=model, messages=messages, temperature=temperature
    )
    if json_mode:
        kwargs["response_format"] = {"type":"json_object"}

    last_exc: Exception | None = None
    for attempt in range(1,max_retries+1):
        try:
            resp = await litellm.acompletion(**kwargs)
            usage = resp.usage
            try:
                cost = litellm.completion_cost(resp)
                logger.info(
                    f"llm model={model} in={usage.prompt_tokens} out={usage.completion_tokens} cost={cost}"
                )
            except Exception:
                logger.info(f"llm model={model} in={usage.prompt_tokens} out={usage.completion_tokens}")
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_exc = e
            wait = 2 ** attempt
            logger.warning(f"llm attempt {attempt}/{max_retries} failed: {e}; retry in {wait}")
            await asyncio.sleep(wait)
    raise LLMError(f"chat failed after {max_retries} retries: {last_exc}") from last_exc