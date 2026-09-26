"""Run the whole Track A test suite with an isolated temp DB.

  python3 backend/tests/run_all.py

Exits non-zero on any failure so CI / a reviewer can trust the result
(master prompt section 66: prove it runs, don't just assert it).
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
for p in (str(BACKEND), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _util import bootstrap  # noqa: E402
bootstrap()


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(HERE), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
