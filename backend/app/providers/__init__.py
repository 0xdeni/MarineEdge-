from __future__ import annotations

import os

from .base import AISProvider, CreditsExhausted, LiveStatic, Neighbour, ProviderError, VesselMatch  # noqa: F401


def make_provider(name: str | None = None, api_key: str | None = None, **kw) -> AISProvider:
    """Factory used by the API and the admin screen: mock | datalastic | kpler.
    The key comes from the admin settings file first, then the environment."""
    from app import settings_store
    name = (name or settings_store.provider_name()).lower()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider(**kw)
    key = api_key or settings_store.provider_key(name)
    if name == "aisstream":
        from .aisstream import OwnAISProvider
        if kw.get("store") is None:
            raise ProviderError("aisstream provider needs the store")
        return OwnAISProvider(kw["store"])
    if name == "datalastic":
        from .datalastic import DatalasticProvider
        return DatalasticProvider(api_key=key)
    if name == "kpler":
        from .kpler import KplerProvider
        return KplerProvider(api_key=key)
    raise ProviderError(f"unknown provider {name!r}")
