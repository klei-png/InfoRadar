import os
from src.config.schema import *

PROVIDER_OVERRIDABLE_KEYS = frozenset({"depth","timeout_s","max_results"})

def resolve_provider_cfg(source: SourceConfig,providers:dict[str,ProviderConfig]) -> ProviderRuntime:
    name = source.params.provider

    if name not in providers:
        raise ConfigError(
            f"source {source.id!r} references unknown provider {name!r}; "
            f"known={sorted(providers)}"
        )
    base = providers[name]

    env_key = f"{name.upper()}_API_KEY"
    api_key = os.environ.get(env_key,"").strip()
    if not api_key:
        raise ConfigError(f"missing API key for provider {name!r}: set env {env_key}")
    overrides = {
        k: getattr(source.params, k)
        for k in PROVIDER_OVERRIDABLE_KEYS
        if getattr(source.params, k, None) is not None
    }

    return ProviderRuntime(
        provider=name,
        api_key=api_key,
        endpoint=base.endpoint,
        depth=overrides.get("depth", base.depth),
        timeout_s=overrides.get("timeout_s", base.timeout_s),
        max_results=overrides.get("max_results", base.max_results),
    )

def enabled_sources(sources: list[SourceConfig]) -> list[SourceConfig]:
    return [s for s in sources if s.enabled]