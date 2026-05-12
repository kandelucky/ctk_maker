"""F12 preview screenshot floater — runtime template injected into
generated `.py` files when launching as a CTkMaker preview (NOT a real
export). The floater bundles a Save PNG button (F12) and a Copy PNG
button (F11), an orange ring around the window so the preview is
visually distinct from a production launch, and drag-to-reposition.

Single public entry: ``_preview_screenshot_lines(target)`` formats the
template with the variable name of the visible window and returns the
indented lines ready to splice into the ``if __name__ == "__main__"``
block.
"""

from __future__ import annotations

from app.io.code_exporter import INDENT


_PREVIEW_SCREENSHOT_TEMPLATE = '''\
# CTkMaker preview tools — title marker, orange ring, draggable F12 button.
import tkinter as _ctkmaker_tk
from tkinter.font import nametofont as _ctkmaker_nametofont

def _ctkmaker_ui_font(**kw):
    # Derive from Tk's named UI font so the floater + toast pick the
    # platform's native UI face (Segoe UI on Win, .AppleSystemUIFont
    # on Mac, DejaVu Sans on Linux) instead of a Win-only hardcode.
    f = _ctkmaker_nametofont("TkDefaultFont").copy()
    if kw:
        f.configure(**kw)
    return f

# --- Title + ring — make it obvious this is a preview, not the
# production window. 4 thin orange Frames at the edges (Tk's
# highlightthickness gets covered by CTk's full-area frame, so
# we draw the ring as real widgets and lift them above content).
_CTKMAKER_PREVIEW_ORANGE = "#ff8800"
try:
    _ctkmaker_orig_title = {target}.title()
except _ctkmaker_tk.TclError:
    _ctkmaker_orig_title = ""
{target}.title("\U0001F7E0 PREVIEW — " + (_ctkmaker_orig_title or "CTkMaker"))

_CTKMAKER_RING_THICKNESS = 2
_ctkmaker_ring = []           # [(frame, place_kwargs), ...] — kept so we
                              # can place_forget/place back during capture
                              # so the orange ring doesn't bleed into PNGs.
def _ctkmaker_build_ring():
    if _ctkmaker_ring:
        return
    sides = [
        dict(x=0, y=0, relwidth=1.0, height=_CTKMAKER_RING_THICKNESS),
        dict(x=0, rely=1.0, y=-_CTKMAKER_RING_THICKNESS,
             relwidth=1.0, height=_CTKMAKER_RING_THICKNESS),
        dict(x=0, y=0, width=_CTKMAKER_RING_THICKNESS, relheight=1.0),
        dict(relx=1.0, x=-_CTKMAKER_RING_THICKNESS, y=0,
             width=_CTKMAKER_RING_THICKNESS, relheight=1.0),
    ]
    for spec in sides:
        f = _ctkmaker_tk.Frame({target}, bg=_CTKMAKER_PREVIEW_ORANGE,
                               bd=0, highlightthickness=0)
        f.place(**spec)
        f.lift()
        _ctkmaker_ring.append((f, spec))

def _ctkmaker_hide_ring():
    for f, _ in _ctkmaker_ring:
        try:
            f.place_forget()
        except _ctkmaker_tk.TclError:
            pass

def _ctkmaker_show_ring():
    for f, spec in _ctkmaker_ring:
        try:
            f.place(**spec)
            f.lift()
        except _ctkmaker_tk.TclError:
            pass

def _ctkmaker_relift_ring(_event=None):
    for f, _ in _ctkmaker_ring:
        try:
            f.lift()
        except _ctkmaker_tk.TclError:
            pass

_ctkmaker_build_ring()
# Re-lift on every reconfigure so newly-placed children don't bury
# the ring. 150 ms gives child widgets time to settle on first paint.
{target}.after(150, _ctkmaker_relift_ring)

_ctkmaker_floater = _ctkmaker_tk.Toplevel({target})
_ctkmaker_floater.overrideredirect(True)
_ctkmaker_floater.attributes("-topmost", True)
_ctkmaker_floater.configure(bg="#1f1f1f", highlightthickness=1,
                            highlightbackground="#3a3a3a")

# Mutable single-element list holding the Toplevel the floater is
# currently anchored to. Starts as the launch target ({target}) and
# is updated on every <FocusIn> below — so opening a child dialog
# from the running preview makes the floater hop onto it. The set
# remembers which Toplevels we've already wired <Configure> for, so
# focus-in doesn't double-bind on each visit.
_ctkmaker_active_target = [{target}]
_ctkmaker_tracked_targets = set()
_ctkmaker_tracked_targets.add({target})

_ctkmaker_inner = _ctkmaker_tk.Frame(_ctkmaker_floater, bg="#1f1f1f",
                                     bd=0, highlightthickness=0)
_ctkmaker_inner.pack()
def _ctkmaker_make_btn(text):
    return _ctkmaker_tk.Button(
        _ctkmaker_inner, text=text,
        font=_ctkmaker_ui_font(size=9, weight="bold"), bg="#2d2d30", fg="#cccccc",
        activebackground="#3e3e42", activeforeground="#ffffff",
        bd=0, padx=10, pady=4,
        relief="flat",
    )

_ctkmaker_btn_save = _ctkmaker_make_btn(" Save PNG  ·  F12 ")
_ctkmaker_btn_save.pack(side="left", padx=(0, 1))
_ctkmaker_btn_copy = _ctkmaker_make_btn(" Copy PNG  ·  F11 ")
_ctkmaker_btn_copy.pack(side="left")

def _ctkmaker_toast(message):
    """Self-destroying Toplevel — bottom-centre of the active target,
    1500ms lifetime. Soft user feedback after Save / Copy actions so
    the user doesn't have to glance at the console.
    """
    try:
        target = _ctkmaker_active_target[0]
        toast = _ctkmaker_tk.Toplevel(target)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#2d2d30", highlightthickness=1,
                        highlightbackground="#3a3a3a")
        lbl = _ctkmaker_tk.Label(
            toast, text=message,
            font=_ctkmaker_ui_font(size=9, weight="bold"),
            bg="#2d2d30", fg="#cccccc",
            padx=14, pady=6,
        )
        lbl.pack()
        toast.update_idletasks()
        tw = toast.winfo_reqwidth()
        th = toast.winfo_reqheight()
        x = target.winfo_rootx() + (target.winfo_width() - tw) // 2
        y = target.winfo_rooty() + target.winfo_height() - th - 24
        toast.geometry(f"+{{x}}+{{y}}")
        toast.after(1500, toast.destroy)
    except _ctkmaker_tk.TclError:
        pass

def _ctkmaker_capture():
    """Grab the active target's client area as a PIL Image. Hides the
    floater + orange ring during the brief grab so neither bleeds
    into the saved PNG. Returns None on failure so callers degrade
    gracefully.
    """
    try:
        from PIL import ImageGrab
    except ImportError:
        print("Pillow not installed — cannot capture screen.")
        return None
    target = _ctkmaker_active_target[0]
    _ctkmaker_floater.withdraw()
    _ctkmaker_hide_ring()
    target.update_idletasks()
    target.update()
    x = target.winfo_rootx()
    y = target.winfo_rooty()
    w = target.winfo_width()
    h = target.winfo_height()
    try:
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    finally:
        _ctkmaker_show_ring()
        _ctkmaker_floater.deiconify()

def _ctkmaker_screenshot_save(_event=None):
    img = _ctkmaker_capture()
    if img is None:
        return
    from tkinter import filedialog
    path = filedialog.asksaveasfilename(
        parent=_ctkmaker_active_target[0], defaultextension=".png",
        filetypes=[("PNG image", "*.png")],
        initialfile="preview.png",
    )
    if path:
        img.save(path)
        print(f"Saved screenshot: {{path}}")
        _ctkmaker_toast("Screenshot saved")

def _ctkmaker_screenshot_copy(_event=None):
    """Copy the captured image to the system clipboard so the user can
    paste it directly into chat / docs / image editors. Windows-only —
    uses System.Windows.Forms.Clipboard via PowerShell so we don't add
    pywin32 as a dependency. On other platforms or on failure, the
    image stays at the temp path and the path is printed instead.
    """
    img = _ctkmaker_capture()
    if img is None:
        return
    import os, subprocess, sys, tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="ctkmaker_clip_")
    os.close(fd)
    img.save(tmp_path, "PNG")
    if sys.platform != "win32":
        print(f"Clipboard copy not supported on this platform — saved to: {{tmp_path}}")
        return
    ps_cmd = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{{tmp_path}}'); "
        "[System.Windows.Forms.Clipboard]::SetImage($img); "
        "$img.Dispose()"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        print("Screenshot copied to clipboard.")
        _ctkmaker_toast("Copied to clipboard")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    else:
        print(f"Clipboard copy failed: {{proc.stderr.strip()}}")
        print(f"Image saved to: {{tmp_path}}")
        _ctkmaker_toast("Clipboard copy failed — see console")

{target}.bind_all("<F12>", _ctkmaker_screenshot_save)
{target}.bind_all("<F11>", _ctkmaker_screenshot_copy)

# --- Drag — let the user reposition the button anywhere on screen.
# While unchanged, default top-right anchoring kicks in. Once dragged,
# the offset persists relative to the target window. Each button
# distinguishes click from drag via a 4-pixel threshold so a small
# wobble during click doesn't suppress the action.
_ctkmaker_user_offset = [None, None]
_ctkmaker_drag_press = [0, 0]
_ctkmaker_drag_origin = [0, 0]
_ctkmaker_was_dragged = [False]

def _ctkmaker_press(_e):
    _ctkmaker_was_dragged[0] = False
    _ctkmaker_drag_press[0] = _e.x_root
    _ctkmaker_drag_press[1] = _e.y_root
    _ctkmaker_drag_origin[0] = _ctkmaker_floater.winfo_rootx()
    _ctkmaker_drag_origin[1] = _ctkmaker_floater.winfo_rooty()

def _ctkmaker_drag(_e):
    dx = _e.x_root - _ctkmaker_drag_press[0]
    dy = _e.y_root - _ctkmaker_drag_press[1]
    if not _ctkmaker_was_dragged[0] and abs(dx) + abs(dy) > 4:
        _ctkmaker_was_dragged[0] = True
    if _ctkmaker_was_dragged[0]:
        nx = _ctkmaker_drag_origin[0] + dx
        ny = _ctkmaker_drag_origin[1] + dy
        _ctkmaker_floater.geometry(f"+{{nx}}+{{ny}}")

def _ctkmaker_release_factory(action):
    def _release(_e):
        if _ctkmaker_was_dragged[0]:
            try:
                target = _ctkmaker_active_target[0]
                _ctkmaker_user_offset[0] = (
                    _ctkmaker_floater.winfo_rootx() - target.winfo_rootx()
                )
                _ctkmaker_user_offset[1] = (
                    _ctkmaker_floater.winfo_rooty() - target.winfo_rooty()
                )
            except _ctkmaker_tk.TclError:
                pass
        else:
            action()
    return _release

for _btn, _action in (
    (_ctkmaker_btn_save, _ctkmaker_screenshot_save),
    (_ctkmaker_btn_copy, _ctkmaker_screenshot_copy),
):
    _btn.bind("<ButtonPress-1>", _ctkmaker_press, add="+")
    _btn.bind("<B1-Motion>", _ctkmaker_drag, add="+")
    _btn.bind("<ButtonRelease-1>", _ctkmaker_release_factory(_action), add="+")

def _ctkmaker_position_floater(_event=None):
    try:
        if not _ctkmaker_floater.winfo_exists():
            return
        target = _ctkmaker_active_target[0]
        if not target.winfo_exists():
            target = {target}
            _ctkmaker_active_target[0] = target
        target.update_idletasks()
        if _ctkmaker_user_offset[0] is not None:
            x = target.winfo_rootx() + _ctkmaker_user_offset[0]
            y = target.winfo_rooty() + _ctkmaker_user_offset[1]
        else:
            bw = _ctkmaker_floater.winfo_reqwidth()
            x = target.winfo_rootx() + target.winfo_width() - bw - 12
            y = target.winfo_rooty() + 8
        _ctkmaker_floater.geometry(f"+{{x}}+{{y}}")
    except _ctkmaker_tk.TclError:
        pass

{target}.bind("<Configure>", _ctkmaker_position_floater, add="+")
{target}.after(120, _ctkmaker_position_floater)

# Whenever any widget gains keyboard focus, switch the floater's
# active target to its enclosing Toplevel. New Toplevels also get a
# <Configure> bind on first visit so resizing/moving the dialog
# re-positions the floater. Skipping the floater itself keeps clicks
# on its own buttons from re-anchoring it onto itself.
def _ctkmaker_on_focus_in(_e):
    try:
        top = _e.widget.winfo_toplevel()
    except _ctkmaker_tk.TclError:
        return
    if top is _ctkmaker_floater:
        return
    if top is _ctkmaker_active_target[0]:
        return
    _ctkmaker_active_target[0] = top
    if top not in _ctkmaker_tracked_targets:
        _ctkmaker_tracked_targets.add(top)
        try:
            top.bind("<Configure>", _ctkmaker_position_floater, add="+")
        except _ctkmaker_tk.TclError:
            pass
    _ctkmaker_position_floater()

{target}.bind_all("<FocusIn>", _ctkmaker_on_focus_in, add="+")

def _ctkmaker_close_floater(_event=None):
    try:
        _ctkmaker_floater.destroy()
    except _ctkmaker_tk.TclError:
        pass

{target}.bind("<Destroy>", _ctkmaker_close_floater, add="+")
print("[CTkMaker preview] F12 / Save → file. F11 / Copy → clipboard. "
      "Drag a button to reposition.")
'''


def _preview_screenshot_lines(target: str) -> list[str]:
    """Inject the floating screenshot button + F12 hotkey into the
    __main__ block when the file is being run as a CTkMaker preview
    (NOT a real export). ``target`` is the variable name of the
    visible window — ``app`` for the main-window preview, the dialog
    instance for dialog previews. The floater hides itself during
    capture so it doesn't appear in the saved PNG.
    """
    body = _PREVIEW_SCREENSHOT_TEMPLATE.format(target=target)
    return [INDENT + line for line in body.splitlines()]
