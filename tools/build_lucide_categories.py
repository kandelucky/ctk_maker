"""Build the aggregated Lucide categories metadata bundled with
CTkMaker so the future Icon Picker can group ~1700 icons by
category without making the user wait on per-icon HTTP fetches.

Reads:
- ``<lucide-main>/icons/<name>.json`` — per-icon ``tags`` +
  ``categories`` arrays.
- ``<lucide-main>/categories/<key>.json`` — category title +
  representative icon glyph.

Writes:
    app/assets/lucide/categories.json

Re-run this script whenever Lucide ships a new release that adds /
removes / re-classifies icons. The output JSON is checked in.

Usage (from project root):
    python tools/build_lucide_categories.py \\
        C:/Users/likak/Desktop/lucide-main-extracted/lucide-main
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(lucide_root: Path) -> None:
    icons_dir = lucide_root / "icons"
    categories_dir = lucide_root / "categories"
    if not icons_dir.exists():
        raise SystemExit(f"icons dir missing: {icons_dir}")
    if not categories_dir.exists():
        raise SystemExit(f"categories dir missing: {categories_dir}")

    # 1. Load category metadata. ``key`` is the category JSON's
    #    filename stem (e.g. ``food-beverage``); the title is the
    #    user-facing label rendered on the picker tab.
    categories: dict[str, dict] = {}
    for cat_file in sorted(categories_dir.glob("*.json")):
        try:
            data = json.loads(cat_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        categories[cat_file.stem] = {
            "title": data.get("title", cat_file.stem),
            "icon": data.get("icon", ""),
            "icons": [],
        }

    # 2. Walk per-icon JSONs. Push the icon name into every
    #    referenced category bucket; also build a flat tags map
    #    for fuzzy search across all icons.
    icons_meta: dict[str, dict] = {}
    for icon_file in sorted(icons_dir.glob("*.json")):
        try:
            data = json.loads(icon_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        name = icon_file.stem
        tags = list(data.get("tags") or [])
        cats = list(data.get("categories") or [])
        icons_meta[name] = {"tags": tags, "categories": cats}
        for cat_key in cats:
            bucket = categories.get(cat_key)
            if bucket is not None:
                bucket["icons"].append(name)

    # 3. Sort each category's icon list deterministically. JSON
    #    diffs stay stable when we re-run the build on a future
    #    Lucide release that just added a few icons.
    for bucket in categories.values():
        bucket["icons"] = sorted(set(bucket["icons"]))

    out = {
        "categories": categories,
        "icons": icons_meta,
    }

    out_path = (
        Path(__file__).resolve().parent.parent
        / "app" / "assets" / "lucide" / "categories.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    total_icons = len(icons_meta)
    total_cats = len(categories)
    print(f"wrote {out_path}")
    print(f"  {total_icons} icons across {total_cats} categories")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            "Usage: python tools/build_lucide_categories.py <lucide-main path>",
            file=sys.stderr,
        )
        sys.exit(2)
    main(Path(sys.argv[1]))
