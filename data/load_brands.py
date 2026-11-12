"""Compatibility entry point for the strict brand-sheet loader."""
import sys
from pathlib import Path

if __name__ == "__main__":
    import runpy

    pipeline_dir = Path(__file__).with_name("pipeline")
    sys.path.insert(0, str(pipeline_dir))
    runpy.run_path(str(pipeline_dir / "load_brands.py"), run_name="__main__")
