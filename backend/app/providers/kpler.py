"""Kpler / MarineTraffic adapter — STUB. Fill in once the trial key and the endpoint list arrive.

Known shape (MarineTraffic API family, now sold by Kpler):
  - Vessel search:   /exportvessels or the vessel particulars endpoint (PS07)
  - Track history:   PS07 "Vessel Historical Track" — up to 12 months with the Pro tier,
                     parameters imo/mmsi, fromdate, todate, period (hourly/daily)
  - Area:            PS06 "Vessels in an Area" by bounding box
  - Static/ETA:      PS07 particulars or the Voyage Forecast endpoint
Every call bills credits; wire the same logging as the Datalastic adapter so the monthly spend is visible.

Ask Kpler for: price of 12 months of history per IMO, the cost of polling the five regions every
5 minutes, and written confirmation that positions may be stored and displayed in an internal tool."""
from __future__ import annotations

import os
from typing import Optional

from app.engine.types import Position, Vessel
from .base import LiveStatic, Neighbour, ProviderError, VesselMatch


class KplerProvider:
    name = "Kpler / MarineTraffic (stub)"

    def __init__(self, api_key: Optional[str] = None):
        self.key = api_key or os.environ.get("KPLER_API_KEY", "")
        if not self.key:
            raise ProviderError("KPLER_API_KEY is not set")

    def search_vessel(self, query: str) -> list[VesselMatch]:
        raise ProviderError("Kpler adapter not implemented yet: see app/providers/kpler.py")

    def get_vessel(self, imo: int) -> Optional[Vessel]:
        raise ProviderError("Kpler adapter not implemented yet")

    def get_track(self, imo: int, start_ms: int, end_ms: int) -> list[Position]:
        raise ProviderError("Kpler adapter not implemented yet")

    def get_vessels_near(self, lat: float, lon: float, radius_m: float, t0: int, t1: int) -> list[Neighbour]:
        raise ProviderError("Kpler adapter not implemented yet")

    def get_vessels_in_area(self, bbox):
        raise ProviderError("Kpler adapter not implemented yet")

    def get_static(self, imo: int) -> LiveStatic:
        raise ProviderError("Kpler adapter not implemented yet")
