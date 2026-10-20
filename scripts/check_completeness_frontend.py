"""Compatibility entry point for the independent coverage catalogue acceptance check."""

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("check_coverage_frontend.py")), run_name="__main__")
