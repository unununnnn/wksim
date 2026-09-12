"""Pure behavior tests for run_e2e.py (no child process, no WSL, no /proc).

They prove the audited fix: the output directory is created atomically and any
existing directory/file/symlink or lost race is refused BEFORE Popen is ever
touched, so a rerun cannot overwrite an earlier smoke's identity chain. A
snapshot of the real e2e tree's hashes at import time is compared at the end
to show these tests leave the existing raw files/result untouched.
"""
import hashlib
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import run_e2e  # noqa: E402


def sha_tree(root):
    root = Path(root)
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


_REAL_TREE_AT_IMPORT = sha_tree(HERE)


def test_prepare_creates_fresh_dir(tmp_path):
    target = tmp_path / "fresh"
    assert run_e2e._prepare_output_dir(target) == target
    assert target.is_dir()


def test_prepare_refuses_existing_dir(tmp_path):
    target = tmp_path / "exists"
    target.mkdir()
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)


def test_prepare_refuses_existing_file(tmp_path):
    target = tmp_path / "afile"
    target.write_text("payload", encoding="utf-8")
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)
    assert target.read_text(encoding="utf-8") == "payload"


def test_prepare_refuses_symlink(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(real, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(link)
    assert link.is_symlink() and Path(os.readlink(link)) == real


def test_prepare_refuses_lost_race(tmp_path):
    target = tmp_path / "race"
    run_e2e._prepare_output_dir(target)
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)  # a concurrent winner would win


def test_prepare_refuses_missing_parent_without_side_effects(tmp_path):
    target = tmp_path / "nope" / "child"
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)
    assert not (tmp_path / "nope").exists()


def test_main_refuses_existing_dir_before_popen(tmp_path, monkeypatch):
    target = tmp_path / "old"
    target.mkdir()
    (target / "children-start.json").write_text('{"identity":"old"}', encoding="utf-8")
    before = sha_tree(target)
    calls = []
    monkeypatch.setattr(run_e2e.subprocess, "Popen",
                        lambda *args, **kwargs: calls.append(args))

    rc = run_e2e.main(["--output-dir", str(target)])

    assert rc == run_e2e.REFUSED_EXIT
    assert calls == []                      # no child spawned
    assert sha_tree(target) == before       # old tree byte-identical


def test_main_refuses_existing_file_before_popen(tmp_path, monkeypatch):
    target = tmp_path / "afile"
    target.write_text("payload", encoding="utf-8")
    calls = []
    monkeypatch.setattr(run_e2e.subprocess, "Popen",
                        lambda *args, **kwargs: calls.append(args))

    rc = run_e2e.main(["--output-dir", str(target)])

    assert rc == run_e2e.REFUSED_EXIT
    assert calls == []
    assert target.read_text(encoding="utf-8") == "payload"


def test_main_requires_output_dir():
    with pytest.raises(SystemExit) as excinfo:
        run_e2e.main([])
    assert excinfo.value.code == 2


def test_fresh_dir_is_created_before_run(tmp_path, monkeypatch):
    target = tmp_path / "fresh"
    seen = {}
    monkeypatch.setattr(run_e2e, "_run",
                        lambda output_dir: seen.setdefault("dir", output_dir) and 0)
    rc = run_e2e.main(["--output-dir", str(target)])
    assert rc == 0
    assert seen["dir"] == target
    assert target.is_dir()


def _good_result():
    thread = {"tid": 1, "start_ticks": 10,
              "delta": {"utime_ticks": 1, "stime_ticks": 1, "run_ns": 100,
                        "runqueue_ns": None, "timeslices": None,
                        "voluntary_ctxt_switches": 0,
                        "nonvoluntary_ctxt_switches": 0},
              "delta_unavailable": {
                  "runqueue_ns": "host_sched_schedstats_not_enabled(after=0)"}}
    role = {"status": "compared", "compared_threads": [thread]}
    return {"binding": {"status": "bound", "reasons": []},
            "before": {"children_sha256": "a" * 64, "boot_id": "b"},
            "after": {"children_sha256": "a" * 64, "boot_id": "b"},
            "roles": {"verifier": role, "spinner": role}}


def _docs():
    proc = {"expected": {"pid": 1, "pgid": 1, "start_ticks": 10}}
    return {"procs": {"verifier": proc, "spinner": proc}}


def test_evaluate_cleanup_is_part_of_verdict():
    result = _good_result()
    docs = _docs()
    children = {"spinner": {"identity": {"start_ticks": 10}}}
    checks, comparable, verdict, _, _ = run_e2e.evaluate(
        result, docs, docs, children, "b", "0",
        {"reaped": True, "returncode": 0}, "a" * 64)
    assert verdict == "pass"
    assert checks["cleanup_ok"] is True

    checks, comparable, verdict, _, _ = run_e2e.evaluate(
        result, docs, docs, children, "b", "0",
        {"reaped": False, "returncode": None}, "a" * 64)
    assert comparable is True
    assert checks["cleanup_ok"] is False
    assert verdict == "fail"


def test_evaluate_schedstats_enabled_missing_spinner_does_not_crash():
    result = {"binding": {"status": "unbound", "reasons": ["x"]}, "roles": {},
              "before": {"children_sha256": None, "boot_id": None},
              "after": {"children_sha256": None, "boot_id": None}}

    checks, comparable, verdict, spinner_delta, verifier_delta = run_e2e.evaluate(
        result, {"procs": {}}, {"procs": {}}, {}, None, "1",
        {"reaped": True, "returncode": 0}, None)

    assert checks["wait_effective"] is False
    assert comparable is False
    assert verdict == "not_comparable"
    assert spinner_delta is None and verifier_delta is None


def _raise(error):
    def raiser(*args, **kwargs):
        raise error
    return raiser


def test_prepare_refuses_symlink_like_existing_without_privilege(tmp_path, monkeypatch):
    # Symlink creation needs host privilege; the guard is the single atomic
    # mkdir, so any existing path (a symlink included) surfaces as
    # FileExistsError and must become Refused.
    target = tmp_path / "linklike"
    monkeypatch.setattr(run_e2e.os, "mkdir",
                        _raise(FileExistsError(17, "File exists", str(target))))
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)


def test_main_refuses_when_mkdir_reports_existing_before_popen(tmp_path, monkeypatch):
    target = tmp_path / "any"
    calls = []
    monkeypatch.setattr(run_e2e.subprocess, "Popen",
                        lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(run_e2e.os, "mkdir",
                        _raise(FileExistsError(17, "File exists", str(target))))
    rc = run_e2e.main(["--output-dir", str(target)])
    assert rc == run_e2e.REFUSED_EXIT
    assert calls == []


def test_prepare_refuses_other_oserror(tmp_path, monkeypatch):
    target = tmp_path / "denied"
    monkeypatch.setattr(run_e2e.os, "mkdir",
                        _raise(OSError(13, "Permission denied", str(target))))
    with pytest.raises(run_e2e.Refused):
        run_e2e._prepare_output_dir(target)


def test_real_e2e_tree_is_untouched_by_these_tests():
    assert sha_tree(HERE) == _REAL_TREE_AT_IMPORT
