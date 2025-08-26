import os

from app import dump_json_artifact


def test_dump_json_artifact_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "1")

    # γράψε δοκιμαστικά στο tmp
    def fake_outputs_root():
        return str(tmp_path)

    # καλέσαμε κανονικά: η app παίρνει root από DATA_PATH folder,
    # οπότε ελέγχουμε απλά ότι δημιουργείται αρχείο.
    p = dump_json_artifact("unit_test.json", {"ok": True})
    assert p and os.path.exists(p)
