"""A blind copy of Deskhand for tools that read code: the app, none of the harness."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("export_blind_copy", ROOT / "scripts" / "export_blind_copy.py")
exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exporter)


def test_deskhand_export_ships_the_app_and_scans_clean(tmp_path):
    dest = tmp_path / "blind"
    exporter.export(dest, "deskhand")  # raises SystemExit on any leak

    shipped = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert shipped == [
        "README.md",
        "deskhand/__init__.py",
        "deskhand/agent.py",
        "deskhand/app.py",
        "deskhand/store.py",
        "deskhand/tools.py",
    ]


def test_harness_words_count_as_leaks_in_a_deskhand_export(tmp_path):
    (tmp_path / "deskhand").mkdir()
    (tmp_path / "deskhand" / "tools.py").write_text("# the G03 canary for the grader\n")
    assert len(exporter.scan_for_leaks(tmp_path, "deskhand")) == 1
