from __future__ import annotations

"""Stable entry point for rebuilding the W25-W28 dashboard artifacts."""

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts" / "build_public_opinion_mixed_test.py"), run_name="__main__")
