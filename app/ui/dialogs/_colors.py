"""Shared dark-theme palette for the dialog package.

A handful of dialogs (About / Confirm / RenamePage / Choice /
AmbiguousProjectPicker) were authored before ``app.ui.style`` existed
and reach into this private palette. Kept stable to avoid visual
churn; new dialogs should use ``app.ui.style`` tokens instead.
"""

from __future__ import annotations


_ABT_BG = "#1e1e1e"
_ABT_FG = "#cccccc"
_ABT_DIM = "#888888"
_ABT_LINK = "#5bc0f8"
_ABT_SEP = "#3a3a3a"
