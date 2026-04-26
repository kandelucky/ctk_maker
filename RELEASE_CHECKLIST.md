# Release Checklist — Public Publication

> Personal worklist for cleaning up the repo before public release.
> Generated 2026-04-26.

---

## ✅ აუცილებელი (პროგრამის სამუშაოდ)

### Root files
```
main.py
run.bat
pyproject.toml
requirements.txt
.gitignore
LICENSE                  ✓ შექმნილია (MIT)
README.md
PYPI_README.md
ctkmaker/__init__.py
```

### Source code
```
app/                     ← მთლიანი ფოლდერი (core, io, ui, widgets, assets)
```

### Tools (მხოლოდ ის რასაც app იყენებს)
```
tools/segment_values_dialog.py    ← imported by panel_commit.py
tools/text_editor_dialog.py       ← imported by panel_commit.py
```

---

## 📌 რეკომენდებული (Public რელიზისთვის)

### GitHub-სპეციფიური
```
.github/                 ← FUNDING.yml + workflows
```

### ვერსიების ისტორია
```
docs/history/v0.0.6.png
docs/history/v0.0.7.png
docs/history/v0.0.8.png
docs/history/v0.0.9.png
docs/history/v0.0.14.png
docs/history/v0.0.18.png
docs/history/README.md
```

### Wiki (ცალკე GitHub Wiki repo-ში — არა მთავარ repo-ში)
```
ctk_maker.wiki/          ← ცალკე ფოლდერი Desktop-ზე
                            push: kandelucky/ctk_maker.wiki.git
```

---

## ❌ წაშალე (track-დან მოაცილე)

### TODO და internal docs
```
docs/todo/                       ← მთლიანი ფოლდერი (7 ფაილი)
docs/architecture/               ← 5 ფაილი dev-internal
docs/contributing.md
docs/getting-started.md
docs/README.md
docs/widgets/                    ← duplicate of wiki
docs/user-guide/                 ← duplicate of wiki
docs/testing/                    ← მთლიანი (8 ფაილი)
docs/tests/                      ← მთლიანი
docs/ARCHITECTURE.md             ← უკვე ignored
docs/module_descriptions.ka.json ← უკვე ignored
docs/architecture_dashboard.html ← უკვე ignored
docs/New folder/                 ← უკვე ignored
```

### Throwaway / exploration tools
```
tools/color_swatches.py              ← throwaway (Indigo selection demo)
tools/test_picker_buttons.py         ← throwaway debug
tools/ctk_button_treeview_mock.py    ← exploration mock
tools/build_lucide_categories.py     ← maintainer-only (Lucide rebuild)
tools/inspect_ctk_widget.py          ← dev-only CLI
```

### სხვადასხვა
```
test_grid_drag.py                ← უკვე ignored
TODO.md                          ← უკვე ignored
.obsidian/                       ← უკვე ignored
open_debug.log                   ← უკვე ignored (matches *.log)
reference/ctk_official/          ← უკვე ignored
```

---

## 🎯 სამოქმედო ნაბიჯები

### 1. `.gitignore`-ში დაამატე
```
# Throwaway / dev-only tools
tools/color_swatches.py
tools/test_picker_buttons.py
tools/ctk_button_treeview_mock.py
tools/build_lucide_categories.py
tools/inspect_ctk_widget.py

# Internal docs (replaced by GitHub Wiki)
docs/todo/
docs/architecture/
docs/contributing.md
docs/getting-started.md
docs/README.md
docs/widgets/
docs/user-guide/
docs/testing/
docs/tests/
```

### 2. `git rm --cached` (track-დან მოშორება, ფაილი ლოკალურად დარჩება)
```bash
git rm -r --cached docs/todo docs/architecture docs/widgets docs/user-guide docs/testing docs/tests
git rm --cached docs/contributing.md docs/getting-started.md docs/README.md
git rm --cached tools/color_swatches.py tools/test_picker_buttons.py tools/ctk_button_treeview_mock.py
git rm --cached tools/build_lucide_categories.py tools/inspect_ctk_widget.py
```

### 3. ახალი ცვლილებები commit-დება
- `app/ui/settings_dialog.py` (untracked, ახალი feature)
- 4 modified ფაილი (`paths.py`, `main_menu.py`, `main_shortcuts.py`, `startup_dialog.py`)
- `LICENSE` (ახალი)
- `.gitignore` (განახლება)

### 4. Wiki-ის push
```bash
cd C:/Users/likak/Desktop/ctk_maker.wiki
git init
git remote add origin https://github.com/kandelucky/ctk_maker.wiki.git
git add .
git commit -m "Initial wiki skeleton"
git push -u origin master
```

---

## 📊 საბოლოო სტრუქტურა

### მთავარი repo (`ctk_visual_builder/`)
```
ctk_visual_builder/
├── .github/
├── .gitignore
├── LICENSE                      ← ✅ შექმნილია
├── README.md
├── PYPI_README.md
├── main.py
├── pyproject.toml
├── requirements.txt
├── run.bat
├── ctkmaker/
│   └── __init__.py
├── app/                         ← მთლიანი source
├── tools/
│   ├── segment_values_dialog.py
│   └── text_editor_dialog.py
└── docs/
    └── history/                 ← მხოლოდ ეს დარჩება
        ├── README.md
        └── v0.0.*.png (6 სურათი)
```

### Wiki repo (ცალკე — `ctk_maker.wiki/`)
```
ctk_maker.wiki/                  ← 45 ფაილი
├── _Sidebar.md
├── Home.md
├── Getting-Started.md
├── User-Guide.md (hub, 19 ბმული)
├── Widgets.md (catalog hub, 19 ვიჯეტი)
├── 18 user-guide გვერდი
├── 19 widget გვერდი
├── Adding-a-New-Widget.md
└── Contributing.md
```

---

## ⚠️ არ დაგავიწყდეს

- [ ] commit `app/ui/settings_dialog.py`
- [ ] commit modified ფაილები
- [ ] `.gitignore` განახლება (იხ. ნაბიჯი 1)
- [ ] `git rm --cached` ბრძანებების გაშვება (იხ. ნაბიჯი 2)
- [ ] wiki repo-ის push (იხ. ნაბიჯი 4)
- [ ] `pyproject.toml` version bump (ეხლა `0.0.1`)
- [ ] README-ში გადამოწმება — გატეხილი ბმულები (`../TODO.md`)
- [ ] `app/assets/` შეცვლა — Lucide LICENSE.txt სრულად ჩართულია?
