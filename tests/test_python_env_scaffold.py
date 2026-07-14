"""Tests for ``write_python_env_scaffold`` — the project-root env
scaffold (requirements/pyrightconfig/.gitignore/ctkmaker.py) and the
``pyrightconfig.json`` staleness refresh. Pure-Python, no Tk.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.project_folder import write_python_env_scaffold


def _sidecar_source():
    from app.io.scripts import ctk_script
    return Path(ctk_script.__file__).read_text(encoding="utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _generated_config(extra_path=None):
    config = {"venvPath": ".", "venv": ".venv"}
    if extra_path is not None:
        config["extraPaths"] = [str(extra_path)]
    config["reportMissingImports"] = "warning"
    return json.dumps(config, indent=4) + "\n"


def test_fresh_folder_gets_full_scaffold(tmp_path):
    written = write_python_env_scaffold(tmp_path)
    assert "requirements.txt" in written
    assert "pyrightconfig.json" in written
    assert ".gitignore" in written
    config = _read_json(tmp_path / "pyrightconfig.json")
    assert config["venv"] == ".venv"


def test_gitignore_excludes_pyrightconfig(tmp_path):
    write_python_env_scaffold(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "pyrightconfig.json" in lines


def test_existing_files_left_alone(tmp_path):
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("my-own-pin==1.0\n", encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "requirements.txt" not in written
    assert reqs.read_text(encoding="utf-8") == "my-own-pin==1.0\n"


def test_dead_extra_path_is_refreshed(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    dead = tmp_path / "gone"
    target.write_text(_generated_config(dead), encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "pyrightconfig.json" in written
    config = _read_json(target)
    # Either re-detected to a live install or dropped — never the corpse.
    for entry in config.get("extraPaths", []):
        assert entry != str(dead)


def test_live_extra_path_is_kept(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    original = _generated_config(tmp_path.as_posix())
    target.write_text(original, encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "pyrightconfig.json" not in written
    assert target.read_text(encoding="utf-8") == original


def test_customised_config_never_touched(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    config = json.loads(_generated_config(tmp_path / "gone"))
    config["typeCheckingMode"] = "strict"
    original = json.dumps(config, indent=4)
    target.write_text(original, encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "pyrightconfig.json" not in written
    assert target.read_text(encoding="utf-8") == original


def test_multi_entry_extra_paths_never_touched(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    config = json.loads(_generated_config(tmp_path / "gone"))
    config["extraPaths"].append("second/path")
    original = json.dumps(config, indent=4)
    target.write_text(original, encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "pyrightconfig.json" not in written
    assert target.read_text(encoding="utf-8") == original


def test_unparseable_config_never_touched(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    target.write_text("{not json", encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "pyrightconfig.json" not in written
    assert target.read_text(encoding="utf-8") == "{not json"


def test_scripts_folder_created(tmp_path):
    written = write_python_env_scaffold(tmp_path)
    assert "scripts/" in written
    assert (tmp_path / "scripts").is_dir()


def test_existing_scripts_folder_untouched(tmp_path):
    script = tmp_path / "scripts" / "my_logic.py"
    script.parent.mkdir()
    script.write_text("class X: pass\n", encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "scripts/" not in written
    assert script.read_text(encoding="utf-8") == "class X: pass\n"


def test_stale_sidecar_is_refreshed(tmp_path):
    target = tmp_path / "ctkmaker.py"
    target.write_text("# old sidecar\n", encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "ctkmaker.py" in written
    assert target.read_text(encoding="utf-8") == _sidecar_source()


def test_current_sidecar_untouched(tmp_path):
    target = tmp_path / "ctkmaker.py"
    target.write_text(_sidecar_source(), encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    assert "ctkmaker.py" not in written


def test_gitignore_excludes_bak(tmp_path):
    write_python_env_scaffold(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "*.bak" in lines


def test_missing_extra_paths_heals_when_detectable(tmp_path):
    target = tmp_path / "pyrightconfig.json"
    target.write_text(_generated_config(), encoding="utf-8")
    written = write_python_env_scaffold(tmp_path)
    # customtkinter is importable in the test env, so detection succeeds
    # and the healed config gains an extraPaths entry.
    assert "pyrightconfig.json" in written
    assert "extraPaths" in _read_json(target)
