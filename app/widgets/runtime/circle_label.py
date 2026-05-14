"""CircleLabel — CTkLabel subclass for full-circle / pill labels.

It does two things:

1. Full-corner-radius layout — passes the fork's native
   ``full_circle=True`` kwarg (ctkmaker-core >= 5.4.12) so the outer
   Frame doesn't grow past its configured size when
   ``2 * corner_radius >= width``. The inner ``tk.Label``'s
   ``min(corner_radius, height/2)`` padx would otherwise squeeze the
   text and push the Frame wider, silently breaking ``place``-layout
   neighbour spacing. This used to be a ``_create_grid`` override;
   it is now a one-line kwarg.
2. Unified event routing — public ``bind()`` behaves as if the
   widget were a single Tk widget, not a (canvas + inner tk.Label)
   composite. Without this, ``<Enter>`` / ``<Leave>`` /
   ``<Configure>`` / ``<Map>`` fire 2-3 times per logical
   transition and ``cursor="hand2"`` only takes effect on the
   inner text/icon area.

Note: the event routing is the first instance of a generic problem
that affects every CTk composite widget (CTkButton, CTkSwitch,
CTkSlider, CTkProgressBar, ...). Upstream customtkinter routes
``bind()`` to every sub-widget unconditionally, which is the root
cause. The fix here is scoped to CTkLabel only; if/when more
composite widgets need the same treatment, the routing dispatcher
should be extracted into a shared mixin (e.g. ``UnifiedBindMixin``).
Once that lands in the fork, this class can go away entirely — the
``full_circle`` kwarg is already native.

Pure standalone Python — no CTkMaker dependency — so the exporter
can inline this module's source verbatim into generated ``.py``
files.

Why unified event routing exists
--------------------------------
``CTkLabel.bind`` calls ``self._canvas.bind`` and
``self._label.bind`` unconditionally. Practical consequences:

- ``<Enter>`` / ``<Leave>`` fire when the cursor crosses the bbox
  of *either* sub-widget — moving from canvas's rounded corner
  into the inner Label's text bbox emits Leave (canvas) + Enter
  (label).
- ``<Configure>`` / ``<Map>`` fire once for the canvas (outer DPI
  pixels) and once for the inner Label (text bbox), neither of
  which is the outer Frame's logical size.
- ``cursor="hand2"`` set via ``configure`` lands only on the inner
  ``tk.Label`` — the rounded-corner area keeps the default cursor.

The override below dispatches by event class:

- Hover (``<Enter>`` / ``<Leave>``) → state-tracked router with
  ``after_idle`` leave debounce so sub-widget transitions are
  invisible to the user handler.
- ``<Motion>`` → dual-bind, deduped by ``event.time``.
- Geometry (``<Configure>`` / ``<Map>`` / ``<Unmap>``) → outer
  Frame only, via ``tkinter.Misc.bind`` to skip the dual-bind
  override.
- Focus + Key → inner ``tk.Label`` (focus receiver per Tk).
- Click + MouseWheel → dual-bind, deduped by ``event.time``.

Internal handlers register lazily on first user ``bind()`` call so
projects that never call ``bind()`` pay no runtime cost.

Caveat: ``unbind()`` is not overridden — upstream ``CTkLabel.unbind``
already removes *all* callbacks for a sequence (passes
``funcid=None`` to native unbind). Fixing that is deferred.
"""
import customtkinter as ctk


class CircleLabel(ctk.CTkLabel):
    """CTkLabel override — full-radius support + unified event routing."""

    _HOVER_EVENTS = frozenset({"<enter>", "<leave>"})
    _GEOMETRY_EVENTS = frozenset({"<configure>", "<map>", "<unmap>"})
    _FOCUS_EVENTS = frozenset({"<focusin>", "<focusout>"})
    _KEY_EVENTS = frozenset({"<keypress>", "<keyrelease>"})
    _DEDUP_EVENTS = frozenset({
        "<button-1>", "<button-2>", "<button-3>",
        "<buttonrelease-1>", "<buttonrelease-2>", "<buttonrelease-3>",
        "<double-button-1>", "<double-button-2>", "<double-button-3>",
        "<mousewheel>",
    })

    def __init__(self, *args, **kwargs):
        # Full-circle / pill layout fix — the fork's native kwarg
        # (ctkmaker-core >= 5.4.12), replacing the old _create_grid
        # override. setdefault so an explicit full_circle still wins.
        kwargs.setdefault("full_circle", True)
        super().__init__(*args, **kwargs)
        # Take the inner CTkCanvas out of Tab traversal. Canvas's
        # default ``takefocus=""`` defers to Tk's heuristic, which
        # includes any widget that has class-level key bindings —
        # and Canvas does, so ``takefocus=True`` labels need 2 Tab
        # presses per move. Forcing 0 keeps focus on inner tk.Label.
        self._canvas.configure(takefocus=0)

        self._unified_inside = False
        self._unified_hover_handlers = []
        self._unified_motion_handlers = []
        self._unified_internal_hover_bound = False
        self._unified_internal_motion_bound = False
        self._mirror_cursor_to_canvas()

    # --- Cursor unification -------------------------------------------

    def _mirror_cursor_to_canvas(self):
        try:
            cur = self._label.cget("cursor")
        except Exception:
            return
        try:
            self._canvas.configure(cursor=cur)
        except Exception:
            pass

    def configure(self, *args, **kwargs):
        super().configure(*args, **kwargs)
        if "cursor" in kwargs:
            self._mirror_cursor_to_canvas()

    # --- bind() override ----------------------------------------------

    def bind(self, sequence=None, command=None, add="+"):
        # Match upstream CTkLabel contract: only additive binds allowed.
        if not (add == "+" or add is True):
            raise ValueError(
                "'add' argument can only be '+' or True to preserve "
                "internal callbacks"
            )
        if sequence is None or command is None:
            return super().bind(sequence, command, add)
        seq = sequence.lower()
        if seq in self._HOVER_EVENTS:
            self._register_unified_hover(seq, command)
            return
        if seq.startswith("<motion"):
            self._register_unified_motion(command)
            return
        if seq in self._GEOMETRY_EVENTS:
            self._bind_outer_only(sequence, command)
            return
        if seq in self._FOCUS_EVENTS or seq in self._KEY_EVENTS:
            self._label.bind(sequence, command, add=True)
            return
        if seq in self._DEDUP_EVENTS:
            self._dedup_dual_bind(sequence, command)
            return
        # Fallback: preserve upstream dual-bind for sequences we don't
        # explicitly classify (Visibility, Activate, Deactivate, etc.).
        super().bind(sequence, command, add=add)

    # --- Hover routing ------------------------------------------------

    def _register_unified_hover(self, seq, command):
        self._unified_hover_handlers.append((seq, command))
        if self._unified_internal_hover_bound:
            return
        self._unified_internal_hover_bound = True
        self._canvas.bind("<Enter>", self._on_internal_enter, add=True)
        self._label.bind("<Enter>", self._on_internal_enter, add=True)
        self._canvas.bind("<Leave>", self._on_internal_leave, add=True)
        self._label.bind("<Leave>", self._on_internal_leave, add=True)

    def _on_internal_enter(self, event):
        if self._unified_inside:
            return
        self._unified_inside = True
        self._fire_hover("<enter>", event)

    def _on_internal_leave(self, event):
        # Cursor may be moving canvas <-> label. Defer one idle tick
        # and re-check the actual top widget under the pointer.
        self.after_idle(self._check_truly_left)

    def _check_truly_left(self):
        if not self._unified_inside:
            return
        try:
            x, y = self.winfo_pointerxy()
            under = self.winfo_containing(x, y)
        except Exception:
            return
        if under is self or under is self._canvas or under is self._label:
            return
        self._unified_inside = False
        self._fire_hover("<leave>", None)

    def _fire_hover(self, seq, event):
        for s, cmd in tuple(self._unified_hover_handlers):
            if s == seq:
                cmd(event)

    # --- Motion routing -----------------------------------------------

    def _register_unified_motion(self, command):
        self._unified_motion_handlers.append(command)
        if self._unified_internal_motion_bound:
            return
        self._unified_internal_motion_bound = True
        last_time = [0]

        def relay(event):
            t = getattr(event, "time", 0)
            if t == last_time[0]:
                return
            last_time[0] = t
            for cmd in tuple(self._unified_motion_handlers):
                cmd(event)

        self._canvas.bind("<Motion>", relay, add=True)
        self._label.bind("<Motion>", relay, add=True)

    # --- Click / wheel dedup ------------------------------------------

    def _dedup_dual_bind(self, sequence, command):
        last_time = [0]

        def wrapped(event):
            t = getattr(event, "time", 0)
            if t == last_time[0]:
                return
            last_time[0] = t
            command(event)

        self._canvas.bind(sequence, wrapped, add=True)
        self._label.bind(sequence, wrapped, add=True)

    # --- Outer-frame-only bind (geometry) -----------------------------

    def _bind_outer_only(self, sequence, command):
        # Bypass ``CTkLabel.bind`` (dual-binds canvas+label) by going
        # through ``tkinter.Misc.bind`` on ``self`` directly, so the
        # event fires once for the outer Frame's real geometry.
        # ``tkinter`` is imported function-scope so the export-side
        # ``needs_tk_import`` gating doesn't have to special-case
        # CTkLabel just to provide ``tk`` at module top.
        import tkinter
        tkinter.Misc.bind(self, sequence, command, add=True)
