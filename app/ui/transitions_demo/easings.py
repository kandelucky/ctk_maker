"""Easing functions + their source-string mirrors.

The runtime easings (`linear`, `ease_in`, …) drive on-screen demos.
The matching ``EASING_SOURCE`` entries are emitted verbatim into
"Generate code" output so the produced snippet is self-contained
(no import from CTkMaker).
"""

from __future__ import annotations

import math


def linear(t): return t
def ease_in(t): return t * t * t
def ease_out(t): return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_quint(t):
    return 1 - (1 - t) ** 5


def back_out(t):
    if t >= 1:
        return 1.0
    s = 1.70158
    u = t - 1
    return 1 + (s + 1) * u ** 3 + s * u ** 2


def elastic_out(t):
    if t == 0 or t == 1:
        return t
    p = 0.35
    return math.pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p) + 1


def spring(t):
    if t == 0 or t == 1:
        return t
    return 1 - math.exp(-6 * t) * math.cos(4.5 * t)


def bounce_out(t):
    n1 = 7.5625
    d1 = 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        u = t - 1.5 / d1
        return n1 * u * u + 0.75
    if t < 2.5 / d1:
        u = t - 2.25 / d1
        return n1 * u * u + 0.9375
    u = t - 2.625 / d1
    return n1 * u * u + 0.984375


EASINGS = {
    "linear": linear,
    "ease_in": ease_in,
    "ease_out": ease_out,
    "ease_in_out": ease_in_out,
    "ease_out_quint": ease_out_quint,
    "back_out": back_out,
    "elastic_out": elastic_out,
    "spring": spring,
    "bounce_out": bounce_out,
}


EASING_SOURCE = {
    "linear": "def linear(t):\n    return t",
    "ease_in": "def ease_in(t):\n    return t * t * t",
    "ease_out": "def ease_out(t):\n    return 1 - (1 - t) ** 3",
    "ease_in_out": (
        "def ease_in_out(t):\n"
        "    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2"
    ),
    "ease_out_quint": "def ease_out_quint(t):\n    return 1 - (1 - t) ** 5",
    "back_out": (
        "def back_out(t):\n"
        "    if t >= 1:\n"
        "        return 1.0\n"
        "    s = 1.70158\n"
        "    u = t - 1\n"
        "    return 1 + (s + 1) * u ** 3 + s * u ** 2"
    ),
    "elastic_out": (
        "def elastic_out(t):\n"
        "    if t == 0 or t == 1:\n"
        "        return t\n"
        "    p = 0.35\n"
        "    return (\n"
        "        math.pow(2, -10 * t) * math.sin((t - p / 4) * (2 * math.pi) / p)\n"
        "        + 1\n"
        "    )"
    ),
    "spring": (
        "def spring(t):\n"
        "    if t == 0 or t == 1:\n"
        "        return t\n"
        "    return 1 - math.exp(-6 * t) * math.cos(4.5 * t)"
    ),
    "bounce_out": (
        "def bounce_out(t):\n"
        "    n1 = 7.5625\n"
        "    d1 = 2.75\n"
        "    if t < 1 / d1:\n"
        "        return n1 * t * t\n"
        "    if t < 2 / d1:\n"
        "        u = t - 1.5 / d1\n"
        "        return n1 * u * u + 0.75\n"
        "    if t < 2.5 / d1:\n"
        "        u = t - 2.25 / d1\n"
        "        return n1 * u * u + 0.9375\n"
        "    u = t - 2.625 / d1\n"
        "    return n1 * u * u + 0.984375"
    ),
}
