# Creating a Project

The startup dialog opens when you launch the builder. Two panels: **Recent**
(left) and **New Project** (right).

**Source:** [`app/ui/startup_dialog.py`](../../app/ui/startup_dialog.py)

## Recent

Scrollable list of previously opened projects with name, parent folder,
and relative time. Click to select, double-click to open. Right-click a
row for **Remove from Recent**. **Browse…** picks any `.ctkproj` file.

## New Project

| Field | Default | Notes |
|---|---|---|
| Name | `Untitled` | Windows-forbidden characters rejected: `\ / : * ? " < > \|` |
| Save to | `~/Desktop` | Writes `<name>.ctkproj` here; refuses to overwrite |
| Device | `Desktop` | Filters the Screen Size dropdown |
| Screen Size | `Medium (1024×768)` | Writes dimensions into Width/Height |
| Width / Height | `1024 × 768` | Clamped to 100–4000 |

`Enter` = Create, `Escape` = Cancel.

## Screen size presets

**Desktop** — Small 800×600, Medium 1024×768, Large 1280×800, HD 720p
1280×720, WXGA+ 1440×900, HD+ 1600×900, Full HD 1080p 1920×1080, WUXGA
1920×1200, QHD 2560×1440, 4K UHD 3840×2160.

**Mobile** — iPhone 15 393×852, iPhone 15 Pro Max 430×932, Pixel 8
412×915, Pixel 8 Pro 448×998, Galaxy S24 360×780, Galaxy S24 Ultra
412×915.

**Tablet** — iPad Mini 744×1133, iPad 10.9 820×1180, iPad Air 11 820×1180,
iPad Pro 11 834×1210, iPad Pro 13 1032×1376, Galaxy Tab S9+ 800×1280,
Galaxy Tab S9 Ultra 960×1520.

Choose **Device: Custom** to skip presets and enter any size.
