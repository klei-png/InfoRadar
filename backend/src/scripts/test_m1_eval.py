"""M1 第 3 块验收：评估集离线部分（calc 工具确定性 + yaml 结构合法）。"""
import asyncio
import yaml
from pathlib import Path

from src.evals.smoke_runner import KINDS, build_calc_tool, _tool_schemas
from src.tools.registry import ToolRegistry


def test_smoke_yaml_valid():
    spec = yaml.safe_load((Path("src/evals/smoke.yaml").read_text(encoding="utf-8")))
    assert spec["name"] == "m1_smoke"
    for sc in spec["scenarios"]:
        assert sc["kind"] in KINDS, f"未知 kind: {sc['kind']}"


def test_calc_tool_deterministic():
    reg = ToolRegistry()
    reg.register(build_calc_tool())
    calc = reg.get("calc")
    r = asyncio.run(calc.handler(a=12, b=9, op="*"))
    assert r.ok and r.content == "108"
    r2 = asyncio.run(calc.handler(a=1, b=0, op="/"))
    assert not r2.ok  # 除法不在支持列表，确定性拒绝


def test_tool_schemas_shape():
    reg = ToolRegistry()
    reg.register(build_calc_tool())
    schemas = _tool_schemas(reg)
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "calc"
    assert schemas[0]["function"]["parameters"]["required"] == ["a", "b"]
