"""M1 最小评估集 runner — spec §8。LLM_SMOKE=1 时才真实调用模型。
注意：evals 与 src/evals/run_eval.py（v1 打分链路）互不影响。"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

import yaml

from src.agent.policy import Policy
from src.agent.tool_executor import ToolExecutor
from src.agent.types import ModelConfig, RunContext, RunState, ToolCall, Usage
from src.llm.adapter import LiteLLMAdapter, ModelResponse
from src.tools.base import Tool, ToolDefinition, ToolResult
from src.tools.registry import ToolRegistry

EVAL_DIR = pathlib.Path(__file__).resolve().parent


# ---- 评估专用确定性工具（独立 registry，不污染 default_registry）----

def build_calc_tool() -> Tool:
    async def calc(a: int, b: int, op: str = "+") -> ToolResult:
        ops = {"+": a + b, "-": a - b, "*": a * b}
        if op not in ops:
            return ToolResult(ok=False, content=f"不支持 {op}", error_code="E_TOOL_FAILED")
        return ToolResult(ok=True, content=str(ops[op]))

    return Tool(
        defn=ToolDefinition(
            name="calc", description="计算两个整数的四则运算结果",
            input_schema={"type": "object", "required": ["a", "b"],
                          "properties": {
                              "a": {"type": "integer"}, "b": {"type": "integer"},
                              "op": {"type": "string", "enum": ["+", "-", "*"]}}},
        ),
        handler=calc,
    )


def _tool_schemas(registry: ToolRegistry) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.defn.name, "description": t.defn.description,
                          "parameters": t.defn.input_schema}}
            for t in registry.all()]


# ---- 场景执行 ----

async def run_completion(adapter, executor, registry, sc) -> tuple[dict, list[str]]:
    resp = await adapter.complete([{"role": "user", "content": sc["prompt"]}])
    fails = []
    if sc["expect"].get("content_not_empty") and not (resp.content or "").strip():
        fails.append("content 为空")
    return {"content": resp.content, "usage": resp.usage}, fails


async def run_tool_round(adapter, executor, registry, sc) -> tuple[dict, list[str]]:
    resp = await adapter.complete([{"role": "user", "content": sc["prompt"]}],
                                  tools=_tool_schemas(registry))
    fails = []
    want = sc["expect"].get("tool_name")
    if not resp.tool_calls:
        fails.append(f"模型未发出 tool_call（直接回了文本: {resp.content!r:.80}）")
        return {"tool_calls": []}, fails
    if want and not any(tc.name == want for tc in resp.tool_calls):
        fails.append(f"期望调用 {want}，实际 {[tc.name for tc in resp.tool_calls]}")
        return {"tool_calls": resp.tool_calls}, fails
    r = await executor.execute(resp.tool_calls[0])
    if sc["expect"].get("result_ok") and not r.ok:
        fails.append(f"工具执行失败: {r.content}")
    return {"tool_calls": resp.tool_calls, "result": r}, fails


async def run_mini_loop(adapter, executor, registry, sc) -> tuple[dict, list[str]]:
    """两轮微循环：模型→工具→回灌→终答。M2 正式 Loop 之前的端到端验证。"""
    messages: list[dict] = [{"role": "user", "content": sc["prompt"]}]
    schemas = _tool_schemas(registry)
    total = Usage()
    used_tools: list[str] = []
    final: str | None = None

    for _round in range(sc.get("max_rounds", 3)):
        resp = await adapter.complete(messages, tools=schemas)
        total.add(resp.usage)
        if not resp.tool_calls:
            final = resp.content
            break
        # assistant 消息（含原始 tool_calls，OpenAI 协议要求成对出现）
        messages.append({
            "role": "assistant",
            "content": resp.content or "",
            "tool_calls": [{"id": tc.call_id, "type": "function",
                            "function": {"name": tc.name,
                                         "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                           for tc in resp.tool_calls],
        })
        for tc in resp.tool_calls:          # ToolExecutor 执行 → tool 角色回灌
            r = await executor.execute(tc, ctx=RunContext(run_id="eval", state=RunState(run_id="eval")))
            used_tools.append(tc.name)
            messages.append({"role": "tool", "tool_call_id": tc.call_id, "content": r.content})
    else:
        final = None

    exp = sc["expect"]
    fails = []
    if exp.get("final_content_not_empty") and not (final or "").strip():
        fails.append("max_rounds 内未得到终答")
    if exp.get("tool_used") and exp["tool_used"] not in used_tools:
        fails.append(f"未使用工具 {exp['tool_used']}，实际 {used_tools}")
    if exp.get("usage_prompt_tokens_gt", 0) >= 0 and total.prompt_tokens <= 0:
        fails.append("Usage 未累加（token 统计链路断了）")
    return {"final": final, "used_tools": used_tools, "usage": total}, fails


KINDS = {"completion": run_completion, "tool_round": run_tool_round,
         "mini_loop": run_mini_loop}


def main() -> int:
    if os.environ.get("LLM_SMOKE") != "1":
        print("跳过：评估集需要真实 LLM。运行请设 LLM_SMOKE=1（CI 不跑评估）。")
        return 0
    spec = yaml.safe_load((EVAL_DIR / "smoke.yaml").read_text(encoding="utf-8"))
    registry = ToolRegistry()
    registry.register(build_calc_tool())
    adapter = LiteLLMAdapter(ModelConfig())
    executor = ToolExecutor(registry, Policy())
    exit_code = 0
    for sc in spec["scenarios"]:
        obs, fails = asyncio.run(KINDS[sc["kind"]](adapter, executor, registry, sc))
        status = "PASS" if not fails else "FAIL"
        print(f"[{status}] {sc['id']}" + ("" if not fails else f"  ← {'; '.join(fails)}"))
        if fails:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
