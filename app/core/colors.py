"""Document accent-color palette.

Each Document on the canvas gets its own theme colour — the title
bar text, the Object Tree border, and the Object Tree doc-header
all use it, so the user can see at a glance which form the
sidebar is bound to. The palette cycles: doc #1 → cyan, #2 →
purple, and so on; once a user picks a custom colour via Window
Settings, ``Document.color`` overrides the auto assignment.
"""

from __future__ import annotations


DOCUMENT_PALETTE: tuple[str, ...] = (
    "#4fc3d5",  # cyan
    "#b06ab3",  # purple
    "#f29f3a",  # amber
    "#4db6ac",  # teal
    "#e57373",  # coral
    "#9ccc65",  # lime
    "#7986cb",  # indigo
    "#ff8a65",  # pink
)
