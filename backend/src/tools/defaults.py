from __future__ import annotations

import pathlib

import yaml

from src.tools.registry import default_registry
from src.tools.builtin import fetch_page, kb_search, read_evidence, web_search  # noqa: F401


def _load_provider_cfg() -> dict:
    p = pathlib.Path(__file__).resolve().parents[2] / "config" / "search_providers.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))["providers"]["tavily"]


default_registry.register(web_search.build_web_search_tool(_load_provider_cfg()))
default_registry.register(fetch_page.build_fetch_page_tool())
default_registry.register(kb_search.build_kb_search_tool())
default_registry.register(read_evidence.build_read_evidence_tool())
