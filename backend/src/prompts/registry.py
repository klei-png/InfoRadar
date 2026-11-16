import logging
from dataclasses import dataclass

import yaml

from src.config.loader import PROJECT_ROOT
PROMPTS_FILE = PROJECT_ROOT / "config" / "prompts.yaml"

@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    system: str

def _load_all() -> dict[str, list[Prompt]]:
    raw = yaml.safe_load(PROMPTS_FILE.read_text(encoding="utf-8"))
    registry: dict[str,list[Prompt]] = {}
    for name, version in (raw or {}).items():
        registry[name] = [
            Prompt(name=name, version=v["version"], system=v["system"].strip())
            for v in version
        ]
    return registry

def get_prompt(name: str,version: str|None = None) -> Prompt:
    """ get the specified prompt; if version=None, get the latest version """
    registry = _load_all()
    if name not in registry:
        raise KeyError(f"prompt {name!r} not found in {PROMPTS_FILE}")
    candidates = registry[name]
    if version:
        for p in candidates:
            if p.version == version:
                return p
        raise KeyError(f"prompt {name!r} has no version {version!r}")
    return candidates[-1]

#get the version
def prompt_version(name: str) -> str:
    return get_prompt(name).version