"""Pytest wrapper around ``tools/check_cross_platform.py``.

Runs the cross-platform lint as a regular test so ``pytest`` picks
up regressions automatically. Failure means a hardcoded
Windows-only pattern (font family, modifier key, etc.) was added
without going through the platform-aware helpers.

See ``docs/architecture/CROSS_PLATFORM.md`` for what to use instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import check_cross_platform as lint  # noqa: E402


def test_no_cross_platform_regression():
    current = lint.scan()
    baseline = lint.load_baseline()
    regressions, _ = lint.diff(current, baseline)
    assert not regressions, (
        "Cross-platform lint regression — hardcoded Windows patterns "
        "added since baseline:\n"
        + "\n".join(regressions)
        + "\n\nSee docs/architecture/CROSS_PLATFORM.md for replacements. "
        "If the new hits are intentional (rare), capture them with:\n"
        "  python tools/check_cross_platform.py --update-baseline"
    )


def test_baseline_not_stale_from_improvements():
    """Counts dropped without baseline being updated — capture the win.

    This guards against the migration-without-baseline-bump case: a
    contributor migrates a file but forgets to run --update-baseline,
    so future regressions in that same file go unnoticed (the baseline
    still allows the old, higher count). Forcing an update keeps the
    baseline tight.
    """
    current = lint.scan()
    baseline = lint.load_baseline()
    _, improvements = lint.diff(current, baseline)
    assert not improvements, (
        "Cross-platform lint baseline is stale — counts dropped "
        "but baseline wasn't refreshed:\n"
        + "\n".join(improvements)
        + "\n\nRun:\n"
        "  python tools/check_cross_platform.py --update-baseline"
    )
