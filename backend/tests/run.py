"""Minimal test runner for environments without pytest: python -m tests.run"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from pathlib import Path


def main() -> int:
    here = Path(__file__).parent
    failed = passed = 0
    for m in pkgutil.iter_modules([str(here)]):
        if not m.name.startswith("test_"):
            continue
        mod = importlib.import_module(f"tests.{m.name}")
        for name in dir(mod):
            if name.startswith("test_") and callable(getattr(mod, name)):
                try:
                    getattr(mod, name)()
                    passed += 1
                    print(f"  ok   {m.name}.{name}")
                except Exception:
                    failed += 1
                    print(f"  FAIL {m.name}.{name}")
                    traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
