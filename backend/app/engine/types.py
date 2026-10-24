"""Engine data types. Plain dataclasses so the engine has no database or web dependency and the
same objects can be built from a provider response, a database row or a test fixture."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

H = 3_600_000          # one hour in ms
D = 24 * H
YEAR = 365 * D


@dataclass
class Position:
    t: int                 # epoch ms, UTC
    lat: float
    lon: float
    sog: float             # knots
    cog: float             # degrees
    draught: float         # metres, crew-entered
    nav: int = 0           # AIS nav status: 0 under way, 1 at anchor, 5 moored
    src: str = "T"         # "T" terrestrial, "S" satellite
    jump: bool = False     # set by the position-jump rule


@dataclass
class Port:
    id: str
    name: str
    country: str
    region: str
    lon: float
    lat: float
    approach_lon: float
    approach_lat: float
    kinds: str
    major: bool = False
    zone: Optional[str] = None
    anch: Optional[tuple[float, float, float]] = None   # (lon, lat, radius_nm)
    pseudo: bool = False


@dataclass
class Zone:
    id: str
    name: str
    basis: str
    poly: list[list[float]]   # [lon, lat] ring
    enabled: bool = True
    short: str = ""           # how a sentence names it: "Crimea", "Iranian waters"
    default_on: bool = True   # the default from config/zones.geojson; an admin's switch in the app overrides it


@dataclass
class Vessel:
    imo: int
    name: str
    mmsi: str = ""
    callsign: str = ""
    flag: str = ""
    type: str = "other"          # tanker | bulk | container | gas | other
    sub: str = ""
    dwt: int = 0
    gt: int = 0
    loa: float = 0
    beam: float = 0
    built: int = 0
    builder: str = ""
    draught_loaded: float = 0
    draught_ballast: float = 0
    region: str = "A"
    ex_names: list[str] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)      # {field, from, to, t}
    sanctions: list[dict] = field(default_factory=list)    # {list, programme, t}
    reg_owner: str = ""
    ben_owner: str = ""
    ism: str = ""
    operator: str = ""
    class_soc: str = ""
    pi: str = ""
    speed: float = 12.0


@dataclass
class PortCall:
    port: Port
    anchorage: bool
    arrive: int
    depart: int
    lat: float
    lon: float
    i0: int
    i1: int
    draught_in: float
    draught_out: float
    anch_hours: float = 0.0


@dataclass
class Voyage:
    n: int
    frm: Optional[PortCall]
    to: Optional[PortCall]
    i0: int
    i1: int
    depart: int
    arrive: Optional[int]
    nm: int
    draught_out: float
    draught_in: float
    current: bool
    flags: list["Flag"] = field(default_factory=list)
    dark_h: float = 0.0

    @property
    def color(self) -> int:
        return (self.n - 1) % 8


@dataclass
class Flag:
    rule: str
    severity: str                     # high | medium | info
    title: str
    lines: list[str]
    t0: int
    t1: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    vessel_level: bool = False
    hours: float = 0.0
    evidence_before: list[Position] = field(default_factory=list)
    evidence_after: list[Position] = field(default_factory=list)
    partner_imo: Optional[int] = None
    port_call: Optional[PortCall] = None
    voyage: Optional[Voyage] = None
    id: str = ""
    meta: dict = field(default_factory=dict)   # structured facts behind the text (zone, port, partner, delta…) for the verdict

    @property
    def key(self) -> str:
        """Stable across re-analysis (unlike id, which is positional): rule + start time. Notes attach to it."""
        slug = "".join(ch for ch in self.rule.lower() if ch.isalnum())[:12]
        return f"{slug}-{self.t0}"


@dataclass
class Status:
    state: str                        # underway | anchored | moored
    destination: str = ""
    eta: Optional[int] = None
    since: Optional[int] = None
    port: Optional[Port] = None
    last_port: Optional[Port] = None
    next_port: Optional[Port] = None


@dataclass
class Analysis:
    vessel: Vessel
    track: list[Position]
    port_calls: list[PortCall]
    voyages: list[Voyage]
    flags: list[Flag]
    status: Status
    stats: dict
    sev: dict
    verdict: dict = field(default_factory=dict)    # filled by app.verdict after the engine ran (not part of the pure pipeline)
