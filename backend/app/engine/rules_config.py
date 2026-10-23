"""Loads config/rules.yaml into a plain nested dict with attribute access.
Defaults mirror the file so the engine still runs if the file is missing."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

DEFAULTS: dict[str, Any] = {
    "port_call": {"max_speed_kn": 0.5, "min_hours": 6, "port_radius_nm": 5, "merge_within_hours": 36},
    "ais_gap": {"min_hours": 6, "high_hours": 24, "near_sensitive_nm": 100, "coverage_min_fixes": 50, "coverage_max_hours": 72},
    "draught_change": {"min_meters": 1.0},
    "sts": {"max_dist_m": 500, "max_speed_kn": 1.0, "min_hours": 2, "max_lookups_per_vessel": 12},
    "position_jump": {"max_implied_kn": 30},
    "identity": {"medium_if_more_than": 1},
    "sanctions": {"lookback_months": 12, "lists": ["OFAC SDN", "EU", "UK"]},
    "history_months": 12,
}


class Rules(dict):
    """dict with attribute access: rules.ais_gap.min_hours"""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Rules(v) if isinstance(v, dict) else v


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_rules(path: str | os.PathLike | None = None) -> Rules:
    p = Path(path or os.environ.get("VVT_RULES", Path(__file__).resolve().parents[3] / "config" / "rules.yaml"))
    data = {}
    if yaml is not None and p.exists():
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    return Rules(_merge(DEFAULTS, data))
