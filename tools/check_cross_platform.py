"""Cross-platform regression guard.

Scans ``app/`` for hardcoded patterns that defeat platform-aware
behavior (currently: hardcoded Windows font families). Each pattern
has a baseline count per file in ``tools/cross_platform_baseline.json``.
The lint fails when:

* a file's count goes UP vs. baseline (regression — new violations
  introduced)
* a file appears with violations but isn't listed in the baseline
  (a brand-new file with platform-locked code)

Migration is the only way down: when a file's hits drop, edit the
baseline to the new (lower) count. Deletion from the baseline only
happens when a file reaches zero hits.

Usage
-----
* Manual: ``python tools/check_cross_platform.py``  (exit 0 = clean,
  1 = regression, 2 = baseline-stale-by-improvement)
* Pytest: see ``tests/test_cross_platform_baseline.py`` — same logic
  as a test so ``pytest`` catches regressions in CI/local runs.

Adding a new pattern
--------------------
Edit ``PATTERNS`` below + run the script with ``--update-baseline``
to capture the new counts. Document the pattern in
``docs/architecture/CROSS_PLATFORM.md`` (what's wrong with it, what
to use instead).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = ROOT / "app"
BASELINE_PATH = ROOT / "tools" / "cross_platform_baseline.json"

# Each pattern is a regex. Matches anywhere in a file count toward
# the per-file budget — comments / docstrings included, since the
# baseline absorbs whatever is currently in the tree.
PATTERNS: dict[str, str] = {
    "segoe_ui": r'"Segoe UI"',
    "consolas": r'"Consolas"',
    # Tk bind strings of the form "<Control-x>" — Win/Linux only.
    # Use ``f"<{MOD_KEY}-x>"`` so Mac users get ``<Command-x>`` too.
    "control_bind": r'"<Control-',
    # Accelerator labels of the form "Ctrl+S" — Win/Linux convention.
    # Use ``f"{MOD_LABEL_PLUS}S"`` so Mac users see ``"⌘S"`` instead.
    "ctrl_label": r'"Ctrl\+',
}


def scan() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for py in sorted(APP_ROOT.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        text = py.read_text(encoding="utf-8")
        per_file: dict[str, int] = {}
        for key, pat in PATTERNS.items():
            n = len(re.findall(pat, text))
            if n > 0:
                per_file[key] = n
        if per_file:
            out[rel] = per_file
    return out


def load_baseline() -> dict[str, dict[str, int]]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(data: dict[str, dict[str, int]]) -> None:
    BASELINE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def diff(current: dict[str, dict[str, int]],
         baseline: dict[str, dict[str, int]]) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) as human-readable strings."""
    regressions: list[str] = []
    improvements: list[str] = []
    files = set(current) | set(baseline)
    for f in sorted(files):
        cur = current.get(f, {})
        base = baseline.get(f, {})
        keys = set(cur) | set(base)
        for k in sorted(keys):
            cn = cur.get(k, 0)
            bn = base.get(k, 0)
            if cn > bn:
                regressions.append(
                    f"  {f}  [{k}]  {bn} → {cn}  (+{cn - bn})"
                )
            elif cn < bn:
                improvements.append(
                    f"  {f}  [{k}]  {bn} → {cn}  (-{bn - cn})"
                )
    return regressions, improvements


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite the baseline file with the current scan. "
             "Use after a verified migration that reduces hits.",
    )
    args = ap.parse_args()

    current = scan()

    if args.update_baseline:
        write_baseline(current)
        print(f"Wrote baseline: {BASELINE_PATH}")
        print(f"Files: {len(current)}")
        return 0

    baseline = load_baseline()
    regressions, improvements = diff(current, baseline)

    if regressions:
        print("REGRESSION — counts went up vs. baseline:")
        for r in regressions:
            print(r)
        print()
        print(
            "If this was intentional (e.g. you removed an entire "
            "file's content), update the baseline:\n"
            "  python tools/check_cross_platform.py --update-baseline"
        )
        print(
            "Otherwise, fix the new hits before committing. See "
            "docs/architecture/CROSS_PLATFORM.md for replacements."
        )
        return 1

    if improvements:
        print("IMPROVEMENT — counts went down vs. baseline:")
        for i in improvements:
            print(i)
        print()
        print(
            "Run the following to capture the win:\n"
            "  python tools/check_cross_platform.py --update-baseline"
        )
        return 2

    print("Cross-platform lint clean — no drift vs. baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
