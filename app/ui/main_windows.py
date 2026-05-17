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
import re
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

# Matches the ``logging.basicConfig`` default-ish ``LEVEL | name |
# message`` prefix the in-app preview runner installs, plus common
# variants users might emit themselves (bare ``ERROR:`` / ``WARN -``).
# Case-insensitive; alternation handles short forms (WARN, CRIT, FATAL).
_LEVEL_RE = re.compile(
    r"^\s*(DEBUG|INFO|WARN(?:ING)?|ERROR|CRIT(?:ICAL)?|FATAL)\b",
    re.IGNORECASE,
)


def _classify_stream(stream: str, line: str) -> str:
    """Rewrite a preview ``stdout`` / ``stderr`` stream into a
    ``preview-<level>`` form if the line starts with a recognised
    ``logging`` level prefix. Editor and separator streams pass through
    unchanged (``_push_editor_line`` already tags them).
    """
    if stream.startswith("editor-") or stream == "separator":
        return stream
    m = _LEVEL_RE.match(line)
    if m is None:
        return stream
    raw = m.group(1).lower()
    if raw == "warn":
        raw = "warning"
    elif raw in ("crit", "fatal"):
        raw = "critical"
    return f"preview-{raw}"


def _stream_level(stream: str) -> str:
    """Extract the severity word from a classified stream — ``info``,
    ``warning``, ``error``, ``critical``, ``debug``, or ``""`` for
    streams that don't carry an explicit severity. Critical folds
    into ``error`` for the counter dimension; debug has no counter.

    Plain ``stderr`` returns ``""`` deliberately: a multi-line
    traceback would otherwise count each frame as a separate error
    (a 13-line traceback inflates the badge to 13). Only lines that
    arrived with an explicit logger-level prefix — i.e. real
    ``logging.error(...)`` calls — bump the error counter. The red
    stderr colour still applies via the tag layer.
    """
    if "-" not in stream:
        return ""
    level = stream.rsplit("-", 1)[1]
    if level == "critical":
        return "error"
    if level in ("info", "warning", "error", "debug"):
        return level
    return ""


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
                filter_vars=self._console_filter_vars,
            )
            self.paned_outer.add(
                self._console_panel,
                stretch="never", minsize=80, height=200,
            )
            merged = self._merged_console_buffer()
            if merged:
                self._console_panel.replay(merged)
            self._console_panel.refresh_counters(self._console_counts)
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
                filter_vars=self._console_filter_vars,
            )
            merged = self._merged_console_buffer()
            if merged:
                self._console_window.replay(merged)
            self._console_window.refresh_counters(self._console_counts)
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
        # drop the main-window-side buffers so a later reopen doesn't
        # replay everything they just cleared, and clear the OTHER
        # form so the two views stay in sync (otherwise clearing the
        # docked panel would leave the floating window with stale
        # output, or vice versa). Explicit Clear wipes both preview
        # and editor; the auto-clear-on-preview path is narrower.
        self._preview_buffer.clear()
        self._editor_buffer.clear()
        self._console_counts = {"info": 0, "warning": 0, "error": 0}
        for console in (self._console_panel, self._console_window):
            if console is not None:
                try:
                    console.clear()
                except tk.TclError:
                    pass

    def _on_console_auto_clear_preview(self) -> None:
        """Narrow clear: wipe only the preview half of the buffer (so
        an Editor warning that pre-dates the preview run survives).
        Called from ``_attach_console_capture`` when the user has
        Auto-clear on preview enabled. The visible Text widget gets a
        full clear + replay of the surviving editor lines.
        """
        self._preview_buffer.clear()
        # Counters are split between sources but tracked as a single
        # severity total. Recompute from the editor deque so the badges
        # show only the surviving (editor-side) entries.
        self._console_counts = {"info": 0, "warning": 0, "error": 0}
        for stream, _ts, _line in self._editor_buffer:
            level = _stream_level(stream)
            if level in self._console_counts:
                self._console_counts[level] += 1
        for console in (self._console_panel, self._console_window):
            if console is not None:
                try:
                    console.clear()
                    if self._editor_buffer:
                        console.replay(list(self._editor_buffer))
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
            self._on_console_auto_clear_preview()
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
        thread-safe queue, classify by severity, append to the matching
        persistent deque, and forward to every live console form.

        Severity classification:
        - ``editor-*`` streams arrive pre-tagged from ``_push_editor_line``
          and keep their level.
        - ``stdout`` / ``stderr`` from a preview subprocess get the first
          token sniffed against the ``logging``-default format
          (``LEVEL | name | message``) — recognised ``DEBUG / INFO /
          WARN(ING) / ERROR / CRIT(ICAL) / FATAL`` rewrites the stream to
          ``preview-<level>`` so the console can colour and filter it.
          Raw ``stdout`` / ``stderr`` survives as the fallback when no
          level prefix matches (plain ``print()``).

        Capped at 200 entries per tick. If the queue still has work
        when the cap is hit, reschedule **immediately** (1ms) instead
        of waiting the full 50ms poll — keeps the UI responsive under
        burst (e.g. an exception storm) without single-threaded
        starvation.
        """
        drained = 0
        backlog = False
        try:
            while drained < 200:
                stream, line = self._console_queue.get_nowait()
                # ``%f`` is 6-digit microseconds; trimming the last 4
                # leaves centiseconds (00-99) — enough precision to
                # order a flood arriving in the same second without
                # bloating every line by 4 extra characters.
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-4]
                stream = _classify_stream(stream, line)
                entry = (stream, ts, line)
                if stream.startswith("editor-"):
                    self._editor_buffer.append(entry)
                else:
                    self._preview_buffer.append(entry)
                level = _stream_level(stream)
                if level in self._console_counts:
                    self._console_counts[level] += 1
                for console in (self._console_panel, self._console_window):
                    if console is not None:
                        try:
                            console.append_line(*entry)
                            console.refresh_counters(self._console_counts)
                        except tk.TclError:
                            pass
                drained += 1
        except queue.Empty:
            pass
        else:
            backlog = not self._console_queue.empty()
        try:
            self._console_poller_id = self.after(
                1 if backlog else 50, self._drain_console_queue,
            )
        except tk.TclError:
            self._console_poller_id = None

    # ------------------------------------------------------------------
    # Buffer merge for replay (two-pointer; both deques are ts-sorted)

    def _merged_console_buffer(
        self,
    ) -> list[tuple[str, str, str]]:
        """Yield the union of preview + editor buffers, ordered by the
        ts string. ts is ``HH:MM:SS.cc`` — lexicographic compare is the
        same as chronological compare within a day, so a plain string
        compare drives the merge without parsing.
        """
        pv = list(self._preview_buffer)
        ed = list(self._editor_buffer)
        if not pv:
            return ed
        if not ed:
            return pv
        out: list[tuple[str, str, str]] = []
        i = j = 0
        while i < len(pv) and j < len(ed):
            if pv[i][1] <= ed[j][1]:
                out.append(pv[i])
                i += 1
            else:
                out.append(ed[j])
                j += 1
        if i < len(pv):
            out.extend(pv[i:])
        if j < len(ed):
            out.extend(ed[j:])
        return out

    # ------------------------------------------------------------------
    # Editor-side log entry point (thread-safe — queue routed)

    def _push_editor_line(self, level: str, message: str) -> None:
        """Append an editor-side log line to the same console pipeline
        the preview subprocess uses.

        This is the **only** function module-level code should call to
        feed the console from the editor process (`logging` handlers,
        `log_error`, autosave threads, etc.). Routing goes through the
        thread-safe ``_console_queue`` so callers can fire from any
        thread without touching Tk state directly — the main-thread
        drainer turns the entry into a buffer append + widget update.
        """
        normalized = (level or "info").lower()
        if normalized == "warn":
            normalized = "warning"
        elif normalized in ("crit", "fatal"):
            normalized = "critical"
        try:
            self._console_queue.put_nowait(
                (f"editor-{normalized}", message),
            )
        except (queue.Full, AttributeError):
            # ``queue.Full`` is impossible for an unbounded Queue but
            # guard anyway. ``AttributeError`` covers very-early boot
            # where the attribute may not be wired yet.
            pass

    # ------------------------------------------------------------------
    # Filter change → toggle elide on the live text widgets

    def _on_console_filter_changed(self, key: str) -> None:
        """Persist the new filter state and push it into every live
        console form so the matching tag's ``elide`` flips immediately
        without re-rendering the buffer.
        """
        try:
            save_setting(
                "console_filters",
                {
                    k: bool(v.get())
                    for k, v in self._console_filter_vars.items()
                },
            )
        except Exception:
            pass
        show = bool(self._console_filter_vars[key].get())
        for console in (self._console_panel, self._console_window):
            if console is not None:
                try:
                    console.apply_filter(key, show)
                except tk.TclError:
                    pass
