from __future__ import annotations

import os

from .base import AISProvider, CreditsExhausted, LiveStatic, Neighbour, ProviderError, VesselMatch  # noqa: F401


def make_provider(name: str | None = None, **kw) -> AISProvider:
    """Factory used by the API: VVT_PROVIDER=mock|datalastic|kpler"""
    name = (name or os.environ.get("VVT_PROVIDER", "mock")).lower()
    if name == "mock":
        from .mock import MockProvider
        return MockProvider(**kw)
    if name == "datalastic":
        from .datalastic import DatalasticProvider
        return DatalasticProvider()
    if name == "kpler":
        from .kpler import KplerProvider
        return KplerProvider()
    raise ProviderError(f"unknown provider {name!r}")
