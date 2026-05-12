"""Floating / docked auxiliary window handlers for ``MainWindow``.

Covers the View menu + function-key shortcuts that toggle every
floating window the builder ships with:

* Object Tree (F8), History (F9), Project (F10), Variables (F11),
  Console (F12 — dock and pop-out form)
* Inspect Widget, Transitions Demo, Color Palette singletons
* Console capture pipeline — ``_attach_console_capture`` spawns the
  stdout / stderr reader threads when a preview subprocess is
  launched in inapp mode, and ``_drain_console_queue`` runs on the Tk
  main loop pulling captured lines into the persistent buffer +
  forwarding them to whichever console form is alive.

All "toggle var" + "on-close" pairs follow the same dance: the View
menu / Fn key flips the Tk BooleanVar; this mixin reads that var,
opens or destroys the matching window, and the window's on-close
callback flips the var back to False so the menubar stays in sync.
"""
from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from datetime import datetime

from app.core.settings import load_settings, save_setting
from app.ui._main_window_host import _MainWindowHost
from app.ui.console_window import ConsolePanel, ConsoleWindow
from app.ui.history_window import HistoryWindow
from app.ui.object_tree_window import ObjectTreeWindow
from app.ui.project_window import ProjectWindow
from app.ui.variables_window import VariablesWindow


def _console_reader(
    stream_name: str, fp, q: queue.Queue,
) -> None:
    """Thread body: read lines from ``fp`` until EOF, push each onto
    the shared queue tagged with the stream name. Lives in this module
    because ``_attach_console_capture`` is the only caller — keeping
    the function next to its consumer trims the dispatch path.
    """
    try:
        for line in iter(fp.readline, ""):
            if not line:
                break
            q.put((stream_name, line.rstrip("\r\n")))
    except (OSError, ValueError):
        pass
    finally:
        try:
            fp.close()
        except OSError:
            pass


class WindowsMixin(_MainWindowHost):
    """Toggle handlers + console capture loop. See module docstring."""

    # ------------------------------------------------------------------
    # Singletons (Inspect / Transitions / Color Palette)
    # ------------------------------------------------------------------
    def _on_inspect_widget(self) -> None:
        # Reuse a single Toplevel — clicking the menu while it's open
        # raises it instead of stacking duplicate windows.
        win = getattr(self, "_widget_inspector_win", None)
        if win is not None and win.winfo_exists():
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
            except tk.TclError:
                self._widget_inspector_win = None
            else:
                return
        from app.ui.widget_inspector_window import WidgetInspectorWindow
        self._widget_inspector_win = WidgetInspectorWindow(self)

    def _on_open_transitions_demo(self) -> None:
        win = getattr(self, "_transitions_demo_win", None)
        if win is not None and win.winfo_exists():
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
            except tk.TclError:
                self._transitions_demo_win = None
            else:
                return
        from app.ui.transitions_demo import TransitionsDemoWindow
        self._transitions_demo_win = TransitionsDemoWindow(self)

    def _on_open_color_palette(self) -> None:
        win = getattr(self, "_color_palette_win", None)
        if win is not None and win.winfo_exists():
            try:
                win.deiconify()
                win.lift()
                win.focus_set()
            except tk.TclError:
                self._color_palette_win = None
            else:
                return
        from app.ui.color_palette_window import ColorPaletteWindow
        self._color_palette_win = ColorPaletteWindow(self)

    # ------------------------------------------------------------------
    # Object Tree
    # ------------------------------------------------------------------
    def _on_toggle_object_tree(self) -> None:
        """Open/close Object Tree window in sync with its View-menu check.

        Driven by `self._object_tree_var`. When the var is toggled by
        the menu item or F8 shortcut, we open or close the window to
        match. When the user closes the window manually, the window's
        on-close callback flips the var back to False.
        """
        want_open = bool(self._object_tree_var.get())
        alive = (
            self._object_tree_window is not None
            and self._object_tree_window.winfo_exists()
        )
        if want_open and not alive:
            self._object_tree_window = ObjectTreeWindow(
                self, self.project,
                on_close=self._on_object_tree_closed,
                tool_setter=lambda t: self.workspace.controls.set_tool(t),
            )
        elif not want_open and alive:
            if self._object_tree_window is not None:
                try:
                    self._object_tree_window.destroy()
                except tk.TclError:
                    pass
            self._object_tree_window = None

    def _on_object_tree_closed(self) -> None:
        self._object_tree_window = None
        self._object_tree_var.set(False)

    def _on_f8_object_tree(self) -> None:
        self._object_tree_var.set(not self._object_tree_var.get())
        self._on_toggle_object_tree()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _on_toggle_history_window(self) -> None:
        want_open = bool(self._history_var.get())
        alive = (
            self._history_window is not None
            and self._history_window.winfo_exists()
        )
        if want_open and not alive:
            self._history_window = HistoryWindow(
                self, self.project,
                on_close=self._on_history_window_closed,
            )
        elif not want_open and alive:
            if self._history_window is not None:
                try:
                    self._history_window.destroy()
                except tk.TclError:
                    pass
            self._history_window = None

    def _on_history_window_closed(self) -> None:
        self._history_window = None
        self._history_var.set(False)

    def _on_f9_history_window(self) -> None:
        self._history_var.set(not self._history_var.get())
        self._on_toggle_history_window()

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------
    def _on_toggle_variables_window(
        self, scope: str = "global",
        variable_id: str | None = None,
    ) -> None:
        want_open = bool(self._variables_var.get())
        alive = (
            self._variables_window is not None
            and self._variables_window.winfo_exists()
        )
        if want_open and not alive:
            self._variables_window = VariablesWindow(
                self, self.project,
                on_close=self._on_variables_window_closed,
                initial_scope=scope,
                initial_variable_id=variable_id,
            )
        elif want_open and alive:
            if self._variables_window is not None:
                self._variables_window.show_scope(scope, variable_id)
        elif not want_open and alive:
            if self._variables_window is not None:
                try:
                    self._variables_window.destroy()
                except tk.TclError:
                    pass
            self._variables_window = None

    def _on_request_open_variables_window(
        self, scope: str = "global", _doc_id: str | None = None,
        variable_id: str | None = None,
    ) -> None:
        """Bus-routed open. Sets the toggle var so menubar / F11 stay
        in sync, then switches to the requested scope tab. Optional
        ``variable_id`` pre-selects the matching row — used by the
        properties panel's double-click on a bound row."""
        self._variables_var.set(True)
        self._on_toggle_variables_window(scope, variable_id)

    def _on_variables_window_closed(self) -> None:
        self._variables_window = None
        self._variables_var.set(False)

    def _on_local_variables_migrated(self, count: int) -> None:
        """Surface the cross-document variable copy as a status toast.

        Fires from ``Project.migrate_local_var_bindings`` after a
        widget paste / reparent that brought local-variable bindings
        into a new document. The user otherwise wouldn't know that
        their variables list grew, so we tell them.
        """
        if count <= 0:
            return
        word = "variable" if count == 1 else "variables"
        self._show_toast(f"{count} local {word} copied")

    def _on_f11_variables_window(self) -> None:
        self._variables_var.set(not self._variables_var.get())
        self._on_toggle_variables_window()

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------
    def _on_toggle_project_window(self) -> None:
        want_open = bool(self._project_var.get())
        alive = (
            self._project_window is not None
            and self._project_window.winfo_exists()
        )
        if want_open and not alive:
            self._project_window = ProjectWindow(
                self, self.project,
                path_provider=lambda: self._current_path,
                on_close=self._on_project_window_closed,
                on_switch_page=self._switch_to_page,
                on_active_page_path_changed=self._on_active_page_renamed,
            )
        elif not want_open and alive:
            if self._project_window is not None:
                try:
                    self._project_window.destroy()
                except tk.TclError:
                    pass
            self._project_window = None

    def _on_project_window_closed(self) -> None:
        self._project_window = None
        self._project_var.set(False)

    def _on_f10_project_window(self) -> None:
        self._project_var.set(not self._project_var.get())
        self._on_toggle_project_window()

    # ------------------------------------------------------------------
    # In-app preview console
    # ------------------------------------------------------------------
    def _on_toggle_console_dock(self) -> None:
        """Add or remove the bottom-docked ConsolePanel from
        ``paned_outer``. Each show recreates the panel and replays the
        current buffer; each hide destroys it. The buffer itself
        outlives both — same lifecycle as the floating window. State
        is persisted to settings so the docked panel reappears in the
        same position on the next launch.
        """
        want_open = bool(self._console_dock_var.get())
        alive = (
            self._console_panel is not None
            and self._console_panel.winfo_exists()
        )
        if want_open and not alive:
            self._console_panel = ConsolePanel(
                self.paned_outer,
                on_clear=self._on_console_clear,
                on_stop=self._on_console_stop,
                on_close=self._on_console_dock_close,
                clear_on_preview_var=self._console_clear_on_preview_var,
            )
            self.paned_outer.add(
                self._console_panel,
                stretch="never", minsize=80, height=200,
            )
            if self._console_buffer:
                self._console_panel.replay(self._console_buffer)
        elif not want_open and alive:
            if self._console_panel is not None:
                try:
                    self.paned_outer.forget(self._console_panel)
                except tk.TclError:
                    pass
                try:
                    self._console_panel.destroy()
                except tk.TclError:
                    pass
            self._console_panel = None
        save_setting("console_dock_open", want_open)

    def _on_console_dock_close(self) -> None:
        """Wired to the docked panel's ``×`` toolbar button. Same end
        state as F12 / View → Console: var off + panel destroyed +
        setting saved."""
        self._console_dock_var.set(False)
        self._on_toggle_console_dock()

    def _restore_console_dock_state(self) -> None:
        """Re-open the docked Console panel on launch when the user
        had it open at last shutdown. Toggle-time persistence in
        ``_on_toggle_console_dock`` writes the boolean; this reads it
        back at startup. Floating window state is intentionally not
        persisted — it's a pop-out, not a default surface.
        """
        try:
            if bool(load_settings().get("console_dock_open", False)):
                self._console_dock_var.set(True)
                self._on_toggle_console_dock()
        except Exception:
            pass

    def _on_f12_console_dock(self) -> None:
        self._console_dock_var.set(not self._console_dock_var.get())
        self._on_toggle_console_dock()

    def _on_toggle_console_window(self) -> None:
        want_open = bool(self._console_window_var.get())
        alive = (
            self._console_window is not None
            and self._console_window.winfo_exists()
        )
        if want_open and not alive:
            self._console_window = ConsoleWindow(
                self,
                on_close=self._on_console_window_closed,
                on_clear=self._on_console_clear,
                on_stop=self._on_console_stop,
                clear_on_preview_var=self._console_clear_on_preview_var,
            )
            if self._console_buffer:
                self._console_window.replay(self._console_buffer)
        elif not want_open and alive:
            if self._console_window is not None:
                try:
                    self._console_window.destroy()
                except tk.TclError:
                    pass
            self._console_window = None

    def _on_console_window_closed(self) -> None:
        self._console_window = None
        self._console_window_var.set(False)

    def _on_console_clear(self) -> None:
        # User pressed Clear inside one of the console forms — also
        # drop the main-window-side buffer so a later reopen doesn't
        # replay everything they just cleared, and clear the OTHER
        # form so the two views stay in sync (otherwise clearing the
        # docked panel would leave the floating window with stale
        # output, or vice versa).
        self._console_buffer.clear()
        for console in (self._console_panel, self._console_window):
            if console is not None:
                try:
                    console.clear()
                except tk.TclError:
                    pass

    def _on_console_stop(self) -> None:
        """User pressed Stop in the Console window. Terminate every
        alive preview subprocess (main + per-dialog). Reader threads
        notice EOF on the closed pipes and exit on their own.
        """
        procs: list[subprocess.Popen] = []
        if self._main_preview_proc is not None:
            procs.append(self._main_preview_proc)
        procs.extend(self._dialog_preview_procs.values())
        stopped = 0
        for proc in procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    stopped += 1
                except OSError:
                    pass
        if stopped:
            plural = "s" if stopped != 1 else ""
            self._console_queue.put((
                "separator",
                f"─── stop requested ({stopped} preview{plural}) ───",
            ))

    def _attach_console_capture(self, proc: subprocess.Popen) -> None:
        """Spawn reader threads for ``proc.stdout`` / ``proc.stderr`` if
        the preview was launched in inapp mode (the only mode where
        ``Popen`` exposes pipes). Threads are daemons — they die with
        the app and end naturally on EOF when the preview exits.

        Pushes a ``separator`` line into the queue first so the buffer
        and live window both show a visual divider between successive
        preview runs (the buffer is shared across runs and would
        otherwise blur them together). The timestamp comes from the
        poller's ``HH:MM:SS`` prefix — no need to repeat it inline.
        """
        if proc.stdout is None and proc.stderr is None:
            return  # not inapp mode (devnull or new-console path)
        if bool(self._console_clear_on_preview_var.get()):
            self._on_console_clear()
        self._console_queue.put(("separator", "─── preview started ───"))
        for stream_name, fp in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            if fp is None:
                continue
            t = threading.Thread(
                target=_console_reader,
                args=(stream_name, fp, self._console_queue),
                daemon=True,
            )
            t.start()

    def _drain_console_queue(self) -> None:
        """Main-thread poller: pull (stream, line) tuples out of the
        thread-safe queue, stamp an HH:MM:SS timestamp, append a
        (stream, ts, line) entry to the persistent buffer, and forward
        to the live console window if one is open. Capped at 200 lines
        per tick so a flood doesn't stall the Tk event loop.
        """
        drained = 0
        try:
            while drained < 200:
                stream, line = self._console_queue.get_nowait()
                # ``%f`` is 6-digit microseconds; trimming the last 4
                # leaves centiseconds (00-99) — enough precision to
                # order a flood arriving in the same second without
                # bloating every line by 4 extra characters.
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-4]
                entry = (stream, ts, line)
                self._console_buffer.append(entry)
                # Cap the persistent buffer so a long-running preview
                # with chatty print() doesn't eat unbounded memory.
                if len(self._console_buffer) > 5000:
                    del self._console_buffer[:500]
                for console in (self._console_panel, self._console_window):
                    if console is not None:
                        try:
                            console.append_line(*entry)
                        except tk.TclError:
                            pass
                drained += 1
        except queue.Empty:
            pass
        try:
            self._console_poller_id = self.after(
                50, self._drain_console_queue,
            )
        except tk.TclError:
            self._console_poller_id = None
