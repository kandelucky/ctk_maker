"""Minimal frame-driven tween engine used by the Transitions Demo.

Each ``Tween`` runs ``step(easing(t))`` every ~16 ms via Tk's
``widget.after`` loop until ``t`` reaches 1, then optionally fires
``on_done``. No external deps — the same ``Tween`` shape is emitted
into the "Generate code" output so users can paste it standalone.
"""

from __future__ import annotations

import time


class Tween:
    FRAME_MS = 16

    def __init__(self, widget, duration, easing, step, on_done=None):
        self.widget = widget
        self.duration = max(duration, 0.001)
        self.easing = easing
        self.step = step
        self.on_done = on_done
        self._start = None
        self._running = False

    def start(self):
        self._start = time.perf_counter()
        self._running = True
        self._tick()
        return self

    def stop(self):
        self._running = False

    def _tick(self):
        if not self._running:
            return
        try:
            t = min((time.perf_counter() - self._start) / self.duration, 1.0)
            self.step(self.easing(t))
        except Exception as e:
            print(f"[tween] step error: {e}")
            self._running = False
            return
        if t < 1.0:
            self.widget.after(self.FRAME_MS, self._tick)
        else:
            self._running = False
            if self.on_done:
                self.on_done()
