"""Runs every Raid Table browser test and prints PASS or FAIL for each.

    python tests/run_all.py

Works with pytest too: `pytest tests`.
"""
import importlib
import pathlib
import sys
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    failed = 0
    for path in sorted(HERE.glob("test_*.py")):
        mod = importlib.import_module(path.stem)
        for name in sorted(n for n in dir(mod) if n.startswith("test_")):
            t = time.time()
            try:
                getattr(mod, name)()
                print(f"PASS  {path.stem}.{name}  ({time.time() - t:.0f}s)")
            except Exception:
                failed += 1
                print(f"FAIL  {path.stem}.{name}")
                traceback.print_exc()
    print("\nAll tests passed." if not failed else f"\n{failed} test(s) failed.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
