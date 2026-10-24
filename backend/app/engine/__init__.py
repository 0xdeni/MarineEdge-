"""MarineEdge rule engine: clean → port calls → voyages → red flags.
Pure Python, no database or web dependency."""
from .pipeline import analyze  # noqa: F401
from .refdata import load_refdata  # noqa: F401
from .rules_config import load_rules  # noqa: F401
from .types import Analysis, Flag, Port, PortCall, Position, Status, Vessel, Voyage, Zone  # noqa: F401

# Bump when a change to the rules, the meaning of a threshold, the reference data or the verdict alters what a ship's
# check says: stored verdicts from an older version are then treated as not checked, and the background sweep
# re-checks them.
ENGINE_VERSION = "2026-10-24.2"
