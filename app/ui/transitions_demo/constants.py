"""Stage / target sizes shared across demo tabs.

Kept module-level so both the live UI builders and the
``code_generators`` (which need the same numeric defaults baked into
generated snippets) can pull from a single source of truth.
"""

from __future__ import annotations


CARD_COLOR = "#1f6aa5"
CARD_DEFAULT_W = 140
CARD_DEFAULT_H = 110
SAMPLE_BTN_W = 150
SAMPLE_BTN_H = 36
POPUP_TARGET = (320, 180, 920, 320)
