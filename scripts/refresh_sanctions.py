#!/usr/bin/env python3
"""Daily sanctions refresh. Usage: DATABASE_URL=... python scripts/refresh_sanctions.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.sanctions.loader import refresh_all
print(refresh_all(os.environ["DATABASE_URL"]))
