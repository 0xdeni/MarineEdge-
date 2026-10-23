"""The provider adapter. Every AIS vendor is wrapped in these three calls, nothing else in the
code base talks to a vendor. Swap the provider in .env (VVT_PROVIDER=mock|datalastic|kpler)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from app.engine.types import Position, Vessel


@dataclass
class VesselMatch:
    imo: int
    name: str
    mmsi: str = ""
    flag: str = ""
    type: str = "other"
    sub: str = ""
    dwt: int = 0
    built: int = 0
    ex_names: list[str] | None = None


@dataclass
class Neighbour:
    vessel: Vessel
    t0: int
    t1: int
    lat: float
    lon: float


@dataclass
class LiveStatic:
    destination: str = ""
    eta: Optional[int] = None
    draught: Optional[float] = None
    nav: Optional[int] = None


class AISProvider(Protocol):
    name: str

    def search_vessel(self, query: str) -> list[VesselMatch]:
        """Name, IMO or MMSI → candidate vessels (several ships may share a name)."""
        ...

    def get_vessel(self, imo: int) -> Optional[Vessel]:
        """Static particulars for one IMO."""
        ...

    def get_track(self, imo: int, start_ms: int, end_ms: int) -> list[Position]:
        """Historical positions (the only call that costs credits on a paid provider)."""
        ...

    def get_vessels_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[Neighbour]:
        """Other vessels within radius_m during [t0, t1] (STS partner search)."""
        ...

    def get_vessels_in_area(self, bbox: tuple[float, float, float, float]) -> list[tuple[Vessel, Position]]:
        """Live positions inside [min_lon, min_lat, max_lon, max_lat] (region view)."""
        ...

    def get_static(self, imo: int) -> LiveStatic:
        """Latest AIS destination / ETA / draught."""
        ...


class ProviderError(RuntimeError):
    pass


class CreditsExhausted(ProviderError):
    pass
