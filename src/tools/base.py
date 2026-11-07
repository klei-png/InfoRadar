from dataclasses import dataclass
from typing import Any, Awaitable, Callable

@dataclass(frozen=True)
class Tool:
    """a capability unit that agent can call """
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[...,Awaitable[Any]]

_REGISTRY: dict[str, Tool] = {}

def register_tool(tool: Tool) -> Tool:
    if tool.name in _REGISTRY:
        raise ValueError(f"duplicate tool name: {tool.name}")
    _REGISTRY[tool.name] = tool
    return tool

def get_tool(name: str) -> Tool:
    if name not in _REGISTRY:
        raise ValueError(f"unknown tool: {name!r}; known={sorted(_REGISTRY)}")
    return _REGISTRY[name]

def all_tools() -> list[Tool]:
    return list(_REGISTRY.values())

def to_openai_schema(tool:Tool) -> dict:
    """transform open-ai function-calling format"""
    return {
        "type": "function",
        "function":{
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }
    }