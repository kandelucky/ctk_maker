# CTkMaker — Window Style

Visual + behavioral conventions for floating tool windows. Three files cooperate:

| File | Role |
|---|---|
| [app/ui/managed_window.py](../../app/ui/managed_window.py) | `ManagedToplevel` base class — geometry memory, dark titlebar, modal grab, Escape-to-close |
| [app/ui/style.py](../../app/ui/style.py) | Color tokens, spacing constants, button/tree/scrollbar factories |
| [app/ui/dev_test_windows.py](../../app/ui/dev_test_windows.py) | Four diagnostic windows demonstrating the style — Ctrl+Alt+H / J / K / L |

## ManagedToplevel

Subclass `ManagedToplevel`, declare class-level attrs, override `build_content`. Geometry is clamped to the visible screen, persisted under `window_key` in `~/.ctk_visual_builder/settings.json["window_geometries"]`, and restored on next open.

### Class attributes

| Attribute | Default | Purpose |
|---|---|---|
| `window_key` | `""` | Settings key for geometry persistence. Required if you want size/position remembered. |
| `window_title` | `""` | `wm title` text. |
| `default_size` | `(400, 300)` | First-open `(w, h)`. |
| `min_size` | `(200, 150)` | `(w, h)` floor passed to `self.minsize`. |
| `fg_color` | `None` | `configure(fg_color=…)`. `None` = CTk default. |
| `panel_padding` | `(6, 6)` | `(padx, pady)` around `build_content`'s frame. Set `(0, 0)` for edge-to-edge toolbars. |
| `modal` | `False` | Apply `grab_set` after the window is visible. |
| `escape_closes` | `True` | Close on `<Escape>` from anywhere in the app — see [Escape handling](#escape-handling). |
| `window_resizable` | `(True, True)` | Tuple passed to `self.resizable`. |
| `always_on_top` | `False` | Apply `-topmost` attribute. |

### Hooks

| Method | Override to |
|---|---|
| `build_content(self) -> CTkFrame` | Return the inner content frame (packed `fill="both", expand=True`). Default returns `None` (empty window). |
| `default_offset(self, parent) -> (x, y)` | Choose first-open placement. Default centers on the screen. |
| `on_close(self)` | Run cleanup that should fire only on user-initiated close. Always followed by `destroy()`. |
| `set_on_close(callback)` | Install a one-off callback fired before `destroy()` (used to reset toggle vars on the parent). |

### Auto-cleanup

`destroy()` calls `cleanup()` on the content frame if it exists, else `_unsubscribe_bus()`. Subclasses don't override `destroy` just to tear down event-bus subscriptions.

### Open / close lifecycle

1. `_prepare` — `attributes("-alpha", 0.0)` so the window is invisible while widgets layout.
2. `build_content` runs; the frame is packed with `panel_padding`.
3. `_apply_initial_geometry` — load saved or fall back to `default_offset`, clamped to the screen.
4. `_reveal` — `update_idletasks` → `attributes("-alpha", 1.0)` → 50ms later `_kick_dark_remap`.
5. `_kick_dark_remap` (Windows only) — `withdraw + update_idletasks + deiconify` cycles the map. Needed because the DWM attribute is set but Windows defers the visual NC paint until the second map. The `ctkmaker-core` fork sets + persists the attribute itself (`CTkToplevel._windows_reapply_titlebar_color`, with a one-shot `SWP_FRAMECHANGED`), but verified 2026-05-14 that does *not* prevent the first-frame light flash here — `_kick_dark_remap` is still required.
6. `lift()` brings the window to Z-order top (no focus grab — `focus_force` is intermittently denied by Windows anti-focus-stealing).
7. If `modal`, `wait_visibility + grab_set`.

`_handle_close`: save geometry → `on_close` → `_on_close_callback` → `destroy`.

### Geometry tracking

`<Configure>` events on the toplevel debounce a 400ms save under `window_key`. Skipped while state is `zoomed` or `iconified` so the next open lands at the user's last *normal* size. Cancelled in `destroy`.

### Escape handling

Local toplevel bind (`self.bind("<Escape>", …)`) is the fast path when keyboard focus is inside the window's bindtag chain. The fallback is a single `bind_all("<Escape>", …)` registered the first time any `ManagedToplevel` opens, paired with a class-level open-window stack:

| | |
|---|---|
| **Stack** | `ManagedToplevel._open_stack` — push on `__init__` (if `escape_closes`), remove on `destroy`. |
| **Handler** | `_global_escape` walks the stack from top, closes the first still-alive window (popping stale entries). |

Without this stack, Escape only fired when the user had clicked into the floating window. Windows refuses `focus_force` intermittently, so the chord stayed broken.

## Style tokens — `app/ui/style.py`

VS Code-adjacent dark theme. Modeled after the Variables window.

### Colors

| Token | Hex | Use |
|---|---|---|
| `BG` | `#1e1e1e` | Tree / canvas / window root |
| `PANEL_BG` | `#252526` | Content frame background |
| `TOOLBAR_BG` | `#2a2a2a` | Toolbar bar |
| `HEADER_BG` | `#2d2d30` | Tree headers, card backgrounds |
| `TREE_FG` | `#cccccc` | Tree text, label text |
| `TREE_SELECTED_BG` | `#094771` | Tree selection |
| `EMPTY_FG` | `#666666` | Placeholder / muted text |
| `BORDER` | `#3a3a3a` | Card / entry border |
| `PRIMARY_BG` / `_HOVER` | `#0e639c` / `#1177bb` | Confirm-action button |
| `SECONDARY_BG` / `_HOVER` | `#3c3c3c` / `#4a4a4a` | Neutral button |
| `DANGER_BG` / `_HOVER` | `#7a2c2c` / `#9c3838` | Destructive button |
| `ENTRY_BG` / `_FG` / `_BORDER` | `#1e1e1e` / `TREE_FG` / `BORDER` | Text input |

### Spacing

| Token | Value |
|---|---|
| `TOOLBAR_HEIGHT` | `44` |
| `TOOLBAR_PADX` / `TOOLBAR_PADY` | `8` / `4` |
| `TOOLBAR_BTN_GAP` | `4` |
| `BUTTON_HEIGHT` / `BUTTON_RADIUS` / `BUTTON_FONT_SIZE` | `30` / `3` / `11` |
| `CONTENT_PADX` / `CONTENT_PADY` | `12` / `12` |
| `TREE_ROW_HEIGHT` / `TREE_FONT_SIZE` | `22` / `10` |

### Helpers

| Function | Returns |
|---|---|
| `make_toolbar(parent)` | `tk.Frame`, 44px tall, `TOOLBAR_BG`, `pack_propagate(False)`. |
| `pack_toolbar_button(btn, first=False)` | Packs `side="left"` with the spacing convention. |
| `primary_button(parent, text, command, width=70)` | Confirm-action `CTkButton` (blue). |
| `secondary_button(parent, text, command, width=64)` | Neutral `CTkButton` (gray). |
| `danger_button(parent, text, command, width=64)` | Destructive `CTkButton` (muted red). |
| `apply_tree_style(parent, name)` | Configures `ttk.Style` for a Treeview style name (call before constructing the tree). |
| `styled_entry(parent, **kw)` | Pre-styled `CTkEntry`. |
| `styled_label(parent, text, **kw)` | Pre-styled `CTkLabel`, transparent bg. |
| `styled_scrollbar(parent, command, orientation="vertical")` | Pre-styled `CTkScrollbar`. |

`ui_font` is re-exported from `app.ui.system_fonts` for convenience.

## Conventions

- New floating tool windows subclass `ManagedToplevel`. Don't recreate the alpha trick / dark titlebar / geometry persistence inline.
- Use `style.py` tokens for any new chrome. Hex literals belong only in `style.py` itself.
- Set `panel_padding=(0, 0)` whenever the content has a toolbar that should run edge-to-edge.
- Existing windows (`Variables`, `History`, `Project`, …) keep their inline constants until the bulk migration. New code uses `style`; old code stays until its turn.
- Don't bind `<Escape>` per-window — `escape_closes=True` already covers it via `bind_all` + the open stack.
- Don't call `focus_force` after open. Windows refuses it on this build often enough that it caused the user to perceive Escape as broken. `lift()` handles Z-order without the focus fight.

## Dev test windows

Four diagnostic windows are bound to Ctrl+Alt + a [vim-row letter](#dev-test-windows). Each demonstrates a different content pattern over the shared style:

| Chord | Window | Content pattern |
|---|---|---|
| Ctrl+Alt+H | `TestWindowA` | Toolbar (Add / Edit / Duplicate / Delete) + Treeview list |
| Ctrl+Alt+J | `TestWindowB` | Toolbar (Save / Reset) + label/entry form rows |
| Ctrl+Alt+K | `TestWindowC` | Toolbar (Copy / Clear / Stop) + log Text-area (Consolas) |
| Ctrl+Alt+L | `TestWindowD` | Toolbar (+Card / Refresh) + 2×3 card grid |

Bound in [app/ui/main_shortcuts.py:_bind_shortcuts](../../app/ui/main_shortcuts.py). Toggle: chord opens, chord again closes. The chord uses Ctrl+Alt+letter rather than Ctrl+Alt+digit because Ctrl+Alt acts as AltGr on some layouts (Ctrl+Alt+4 produced a currency keysym instead of `4`, leaving #4 unreachable).

These windows are diagnostic. Remove or move under a debug flag once the helper is fully validated.
