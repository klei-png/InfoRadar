import logging
from pathlib import Path
from typing import Any
import yaml
from pydantic import ValidationError

from src.config.schema import ConfigError,ProviderConfig,SourceConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)

def _read_yaml(path: str) -> Any:
    p = Path(path)

    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise ConfigError(f"config file not found: {path}")
    if not p.is_file():
        raise ConfigError(f"config path is not a file: {path}")
    try:
        with p.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid yaml in {path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    if data is None:
        raise ConfigError(f"empty config file: {path}")
    return data

def _format_error(path: str, index: int, sid: str, e: ValidationError) -> str:
    lines = [f"invalid source in {path}:"]
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        lines.append(f"  sources[{index}].{loc}: {err['msg']} (id={sid!r})")
    return "\n".join(lines)

def load_sources(path: str = "config/sources.yaml") -> list[SourceConfig]:
    data = _read_yaml(path)
    if not isinstance(data, dict) or "sources" not in data:
        raise ConfigError(f"{path}: top-level 'sources' key is required")
    raw_list = data["sources"]
    if not isinstance(raw_list, list) or not raw_list:
        raise ConfigError(f"{path}: 'sources' must be a non-empty list")

    sources: list[SourceConfig] = []
    errors: list[str] = []
    for i, raw in enumerate(raw_list):
        sid = raw.get("id", "?") if isinstance(raw, dict) else "?"
        try:
            sources.append(SourceConfig.model_validate(raw))
        except ValidationError as e:
            errors.append(_format_error(path, i, sid, e))
    if errors:
        raise ConfigError("\n".join(errors))

    ids = [s.id for s in sources]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        raise ConfigError(f"{path}: duplicate source id: {dups}")

    logger.info("loaded %d source(s) from %s", len(sources), path)
    return sources

def load_providers(path: str = "config/search_providers.yaml") -> dict[str, ProviderConfig]:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level must be a mapping")
    raw = data.get("providers")
    if not isinstance(raw, dict) or not raw:
        raise ConfigError(f"{path}: 'providers' must be a non-empty mapping")

    out: dict[str, ProviderConfig] = {}
    errors: list[str] = []
    for name, cfg in raw.items():
        try:
            out[name] = ProviderConfig.model_validate(cfg)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                errors.append(f"  providers.{name}.{loc}: {err['msg']}")
    if errors:
        raise ConfigError(f"invalid providers in {path}:\n" + "\n".join(errors))
    return out

def load_profile(path: str = "config/profile.yaml") -> dict[str, Any]:
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top-level must be a mapping")
    return data