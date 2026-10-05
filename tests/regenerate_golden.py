"""Regenerate the golden parse outputs from the committed fixtures.

Run this only when a parser change is intentional, and read the diff before
committing it: `git diff tests/golden`.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import CASES, to_jsonable  # noqa: E402
from conftest import GOLDEN, read_fixture  # noqa: E402


def main() -> int:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name, fn, fixture, extra in CASES:
        result = to_jsonable(fn(read_fixture(fixture), *extra))
        path = GOLDEN / f"{name}.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        size = path.stat().st_size
        count = len(result) if isinstance(result, list) else "dict"
        print(f"  {name:18s} {count!s:>5s} rows  {size:7d} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
