"""Replacement dropdown popup for CTkComboBox and CTkOptionMenu.

CTk's built-in dropdown grows the popup vertically with every added
value (no scroll), and its width is fixed regardless of the parent
widget's width. This class fixes both:

- Scrollbar appears when value count exceeds ``max_visible``
- Popup width matches the parent's pixel width
- Frame border width / colour / corner radius are configurable

Attach by passing the parent widget; the constructor monkey-patches
``parent._open_dropdown_menu`` so CTk's normal click flow opens this
popup instead of its own.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk


class ScrollableDropdown:
    _ALIGN_TO_ANCHOR = {"left": "w", "center": "center", "right": "e"}

    def __init__(
        self,
        attach,
        *,
        max_visible: int = 8,
        button_height: int = 24,
        button_align: str = "center",
        offset: int = 4,
        fg_color: str = "#2b2b2b",
        text_color: str = "#dce4ee",
        hover_color: str = "#3a3a3a",
        border_width: int = 1,
        border_color: str = "#3c3c3c",
        corner_radius: int = 6,
        font=None,
    ) -> None:
        self.attach = attach
        self.max_visible = max_visible
        self.button_height = button_height
        self.button_align = button_align
        self.offset = offset
        self.fg_color = fg_color
        self.text_color = text_color
        self.hover_color = hover_color
        self.border_width = border_width
        self.border_color = border_color
        self.corner_radius = corner_radius
        # Item font — the dropdown buttons share the parent's font so
        # cascade family selections land on popup items too. ``None``
        # falls back to CTkButton's theme default.
        self.font = font

        self._buttons: list[ctk.CTkButton] = []
        self._inner: tk.Misc | None = None
        self._buttons_dirty = False

        self.top = tk.Toplevel(attach.winfo_toplevel())
        self.top.withdraw()
        self.top.overrideredirect(True)
        try:
            self.top.attributes("-topmost", True)
        except tk.TclError:
            pass
        # Match Toplevel bg to the popup fg so rounded corners on the
        # CTkFrame inside don't reveal the system gray underneath as a
        # ghostly "second popup" behind ours.
        self._sync_top_bg()

        self.container = ctk.CTkFrame(
            self.top,
            border_width=border_width,
            border_color=border_color,
            corner_radius=corner_radius,
            fg_color=fg_color,
        )
        self.container.pack(fill="both", expand=True)

        self._build_buttons()

        # Replace CTk's dropdown opener with ours.
        attach._open_dropdown_menu = self.show

        # Close on Escape / outside click. FocusOut on the popup is
        # unreliable for overrideredirect Toplevels on Windows — they
        # often never receive focus, so the binding fires immediately
        # after deiconify and the popup never gets seen.
        self.top.bind("<Escape>", lambda _e: self.hide())
        root = attach.winfo_toplevel()
        root.bind("<Button-1>", self._on_root_click, add="+")
        root.bind("<Configure>", self._on_root_configure, add="+")
        # Hide on app deactivate — without this, the topmost popup
        # bleeds across the user's whole desktop (visible above other
        # apps after they Alt+Tab away).
        root.bind("<FocusOut>", self._on_root_focus_out, add="+")
        attach.bind("<Destroy>", lambda _e: self._destroy_top(), add="+")

    # ------- public API -------

    def show(self) -> None:
        # Click on the attach widget while the popup is already open —
        # treat as "close". The root <Button-1> handler ignores clicks
        # on the attach (so the show wins the race), so we mirror that
        # branch here for the toggle behaviour.
        if str(self.top.state()) != "withdrawn":
            self.hide()
            return
        # Render off-screen first so reqheight calls are meaningful.
        self.top.geometry("+10000+10000")
        self.top.deiconify()
        # Now that the Toplevel is mapped, do any deferred rebuild.
        # Pulling latest values also goes here so a configure(values=)
        # since the previous show is reflected.
        if self._buttons_dirty:
            self._build_buttons()
            self._buttons_dirty = False
        else:
            self._sync_from_attach()
        self.top.update_idletasks()
        self._reposition()
        self.top.lift()

    def hide(self) -> None:
        try:
            self.top.withdraw()
        except tk.TclError:
            pass

    def _on_root_focus_out(self, _event=None) -> None:
        """Root toplevel just lost focus. FocusOut also fires for
        intra-app focus changes (clicking a different widget),
        so defer the check by one tick and use ``focus_get()`` to
        distinguish "focus left this Tk app entirely" from "focus
        moved to another widget in the app". The former hides;
        the latter keeps the popup open so e.g. typing into a
        sibling Entry while the dropdown is up isn't disrupted.
        """
        try:
            if str(self.top.state()) == "withdrawn":
                return
        except tk.TclError:
            return
        self.top.after(50, self._maybe_hide_after_focus_loss)

    def _maybe_hide_after_focus_loss(self) -> None:
        try:
            if str(self.top.state()) == "withdrawn":
                return
            # ``focus_get`` returns None when no Tk widget in this
            # interpreter holds the keyboard focus — i.e. the user
            # has switched to a different app or the desktop.
            if self.top.focus_get() is None:
                self.hide()
        except (KeyError, tk.TclError):
            # Defensive: focus_get can throw on torn-down widgets.
            pass

    def configure_style(self, **kwargs) -> None:
        """Re-apply colours / border / layout. Called from the descriptor
        when the user edits dropdown_* / border_* properties so the
        popup reflects them without rebuilding from scratch.
        """
        for key in (
            "fg_color", "text_color", "hover_color",
            "border_width", "border_color", "corner_radius",
            "max_visible", "button_align", "offset", "font",
        ):
            if key in kwargs:
                setattr(self, key, kwargs[key])
        try:
            self.container.configure(
                border_width=self.border_width,
                border_color=self.border_color,
                corner_radius=self.corner_radius,
                fg_color=self.fg_color,
            )
        except Exception:
            pass
        self._sync_top_bg()
        # Building children inside a withdrawn Toplevel leaves
        # CTkScrollableFrame in a bad layout state — children appear
        # but their text doesn't render until the frame has been
        # mapped at least once. Defer the rebuild to next show() so
        # we always rebuild against a visible Toplevel.
        if str(self.top.state()) == "withdrawn":
            self._buttons_dirty = True
        else:
            self._build_buttons()

    # ------- internals -------

    def _sync_from_attach(self) -> None:
        try:
            new_values = list(self.attach.cget("values") or [])
        except Exception:
            return
        old = [b.cget("text") for b in self._buttons]
        if new_values != old:
            self._build_buttons(new_values)

    def _build_buttons(self, values: list[str] | None = None) -> None:
        if values is None:
            try:
                values = list(self.attach.cget("values") or [])
            except Exception:
                values = []
        for b in self._buttons:
            b.destroy()
        self._buttons = []
        if self._inner is not None:
            try:
                self._inner.destroy()
            except tk.TclError:
                pass
            self._inner = None

        if len(values) > self.max_visible:
            inner = ctk.CTkScrollableFrame(
                self.container,
                fg_color=self.fg_color,
                corner_radius=0,
            )
        else:
            inner = ctk.CTkFrame(
                self.container,
                fg_color=self.fg_color,
                corner_radius=0,
            )
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        self._inner = inner

        anchor = self._ALIGN_TO_ANCHOR.get(self.button_align, "center")
        # Pre-compute button width from attach so freshly built buttons
        # don't render at CTk's default 140 (which clips text inside a
        # wider popup until the next _reposition pass).
        try:
            attach_w = max(self.attach.winfo_width(), 60)
        except tk.TclError:
            attach_w = 200
        scrollbar_w = 16 if len(values) > self.max_visible else 0
        btn_w = max(attach_w - 2 * self.border_width - 8 - scrollbar_w, 40)
        for v in values:
            kwargs = dict(
                text=v, height=self.button_height,
                width=btn_w,
                fg_color="transparent",
                text_color=self.text_color,
                hover_color=self.hover_color,
                anchor=anchor, corner_radius=0,
                command=lambda val=v: self._on_select(val),
            )
            if self.font is not None:
                kwargs["font"] = self.font
            btn = ctk.CTkButton(inner, **kwargs)
            btn.pack(fill="x", padx=2, pady=1)
            self._buttons.append(btn)
        # If popup is visible during a rebuild (e.g. user changed
        # max_visible in the properties panel), reposition so the new
        # button widths and inner frame size land correctly.
        if str(self.top.state()) != "withdrawn":
            try:
                self._reposition()
            except tk.TclError:
                pass

    def _on_select(self, value: str) -> None:
        try:
            self.attach.set(value)
        except Exception:
            pass
        # Fire user command if the parent widget has one wired.
        cb = getattr(self.attach, "_command", None)
        if callable(cb):
            try:
                cb(value)
            except Exception:
                pass
        self.hide()

    def _sync_top_bg(self) -> None:
        # CTk colors can be (light, dark) tuples; Toplevel needs a
        # plain string. Pick the dark variant — appearance mode is
        # handled by CTk itself, the Toplevel just needs a fallback.
        bg = self.fg_color
        if isinstance(bg, (tuple, list)) and bg:
            bg = bg[-1]
        try:
            self.top.configure(bg=bg)
        except tk.TclError:
            pass

    def _on_root_configure(self, _event) -> None:
        if str(self.top.state()) != "withdrawn":
            self._reposition()

    def _on_root_click(self, event) -> None:
        if str(self.top.state()) == "withdrawn":
            return
        # Click inside our popup → ignore (button command handles it).
        try:
            tx = self.top.winfo_rootx()
            ty = self.top.winfo_rooty()
            tw = self.top.winfo_width()
            th = self.top.winfo_height()
        except tk.TclError:
            return
        if tx <= event.x_root <= tx + tw and ty <= event.y_root <= ty + th:
            return
        # Click on the attach widget — let CTk's _clicked toggle. If
        # we hide here we'll race the show that follows; let attach
        # win that race by ignoring the outside click.
        try:
            ax = self.attach.winfo_rootx()
            ay = self.attach.winfo_rooty()
            aw = self.attach.winfo_width()
            ah = self.attach.winfo_height()
        except tk.TclError:
            self.hide()
            return
        if ax <= event.x_root <= ax + aw and ay <= event.y_root <= ay + ah:
            return
        self.hide()

    def _reposition(self) -> None:
        try:
            x = self.attach.winfo_rootx()
            y = (
                self.attach.winfo_rooty()
                + self.attach.winfo_height()
                + self.offset
            )
            w = max(self.attach.winfo_width(), 60)
        except tk.TclError:
            return
        count = len(self._buttons)
        visible = max(1, min(count, self.max_visible))

        # Force layout pass so reqheight is current.
        try:
            if self._inner is not None:
                self._inner.update_idletasks()
        except tk.TclError:
            pass

        # Per-button rendered height incl. pack pady (1px each side).
        if self._buttons:
            try:
                btn_h = self._buttons[0].winfo_reqheight() + 2
            except tk.TclError:
                btn_h = self.button_height + 4
        else:
            btn_h = self.button_height + 4

        if count <= self.max_visible:
            # No scrollbar — let the inner frame's required height drive
            # the popup height so we never clip the last row.
            try:
                inner_h = self._inner.winfo_reqheight()
            except tk.TclError:
                inner_h = visible * btn_h
            chrome = 4 + 2 * self.border_width
            h = inner_h + chrome
        else:
            # Scrollable — show exactly `max_visible` rows. Add CTkScrollableFrame
            # chrome (label gap + canvas border + scrollbar pad) plus container.
            chrome = 4 + 2 * self.border_width + 16
            h = visible * btn_h + chrome

        # Stretch each button to popup width minus chrome so wide
        # popups don't render with a 140-px button + empty space (which
        # CTkButton's text_label centers into and visually loses text).
        scrollbar_w = 16 if count > self.max_visible else 0
        btn_w = max(w - 2 * self.border_width - 8 - scrollbar_w, 40)
        for b in self._buttons:
            try:
                b.configure(width=btn_w)
            except tk.TclError:
                pass

        self.top.geometry(f"{w}x{h}+{x}+{y}")

    def _destroy_top(self) -> None:
        try:
            self.top.destroy()
        except tk.TclError:
            pass
