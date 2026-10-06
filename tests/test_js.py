"""The page's own tests, run from pytest so one command covers both halves.

`node --test tests/js/*.test.mjs` is the JS suite: the category-slide rules, the
year badges, the key↔name decoder and the formatting helpers. They are pure
functions against made-up squads, so they need no browser — but they do need
node, and a suite that silently did not run would be worse than no suite. So the
pass count is asserted, not just the exit code.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
node = shutil.which("node")

pytestmark = pytest.mark.skipif(node is None, reason="node not installed")

# The suite is this large on purpose: a runner that reports "0 failures" over 0
# tests is the failure mode this wrapper exists to catch.
EXPECTED_FILES = {"badges", "categories", "format", "people"}
MIN_TESTS = 40


def _run() -> subprocess.CompletedProcess:
    files = sorted((ROOT / "tests" / "js").glob("*.test.mjs"))
    stems = {f.stem.split(".")[0] for f in files}
    assert stems == EXPECTED_FILES, (
        f"expected the JS suite to hold {sorted(EXPECTED_FILES)}, found "
        f"{[f.name for f in files]}"
    )
    return subprocess.run(
        [node, "--test", *[str(f) for f in files]],
        cwd=ROOT, capture_output=True, text=True, timeout=300,
    )


def _counts(out: str) -> dict[str, int]:
    # node writes an information-source character (U+2139) before each count.
    pattern = "^[i\u2139]\\s+(tests|pass|fail|cancelled)\\s+(\\d+)$"
    return {k: int(v) for k, v in re.findall(pattern, out, re.M)}


def test_the_page_tests_pass():
    proc = _run()
    counts = _counts(proc.stdout)
    assert counts, f"the runner reported no counts:\n{proc.stdout}\n{proc.stderr}"
    assert counts.get("fail", -1) == 0, proc.stdout[-6000:]
    assert counts.get("cancelled", 0) == 0, proc.stdout[-6000:]
    assert counts["pass"] >= MIN_TESTS, (
        f"only {counts['pass']} tests ran; the suite is expected to hold at least "
        f"{MIN_TESTS} — a shrunk or misnamed file is a failure, not a pass"
    )
    assert counts["pass"] == counts["tests"], proc.stdout[-3000:]


def test_a_failing_page_test_is_reported_as_one():
    """The wrapper is only worth having if it fails. A file that asserts the
    opposite of what the code does must come back as a failure, with the name of
    the test that broke."""
    bad = """
import test from 'node:test';
import assert from 'node:assert/strict';
import { canonicalKey } from '../../js/people.js';
test('a deliberate contradiction', () => {
    assert.equal(canonicalKey('Roni Hotari'), 'roni hotari');
});
"""
    # Written under tests/js/ so its relative import resolves, then removed.
    path = ROOT / "tests" / "js" / "_wrapper_probe.test.mjs"
    try:
        path.write_text(bad, encoding="utf-8")
        proc = subprocess.run(
            [node, "--test", str(path)], cwd=ROOT, capture_output=True, text=True, timeout=120,
        )
    finally:
        path.unlink(missing_ok=True)
    counts = _counts(proc.stdout)
    assert proc.returncode != 0, "a contradicting test must make the runner exit non-zero"
    assert counts.get("fail") == 1, proc.stdout[-2000:]
    assert "a deliberate contradiction" in proc.stdout
