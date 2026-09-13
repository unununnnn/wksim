"""C2 readiness-path microbenchmark: real old/new readiness blocks via AST.

Old: runner at git HEAD 7cb7e84 (SHA fd0b7ee6...) built go/ready Path objects
inside the per-tick while body.  New: current runner (SHA c208b1d0...) moved
that construction before the loop.  This script extracts the ACTUAL code
blocks from both sources with ast (no algorithm rewriting), executes them per
tick against a fixed tempdir fixture (go.json + pv-go-1/2.json pre-exist, so
the save/read branches never fire), and measures wall + thread CPU.

Protocol: same warmup for both arms (2 full passes each), then 5 alternating
measured passes of 20000 ticks per arm.  A separate counting round (untimed)
records pathlib exists()/is_file() call counts, which MUST be identical
between arms: C2 changes Path construction frequency, not FS check frequency.

Output: result.json + extracted block snapshots next to this script.
Pure Python; no native/ROS/model/build.
"""
import ast
import hashlib
import json
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

HERE = pathlib.Path(__file__).resolve().parent
LINUX_REPO = pathlib.Path("/root/wksim-release-acceptance-fe3")
NEW_RUNNER = LINUX_REPO / "tools/run_joint_flight.py"
TICKS = 20000
PASSES = 5
WARMUP_PASSES = 2


def source_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def old_source():
    return subprocess.run(
        ["git", "-C", str(LINUX_REPO), "show", "7cb7e84:tools/run_joint_flight.py"],
        check=True, capture_output=True, text=True).stdout


def find_while(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and "MAX_TICKS" in ast.unparse(node.test):
            return node
    raise RuntimeError("readiness while loop not found")


def extract_new(text):
    """Current runner: 4 pre-loop Assign constructions + 2 in-loop If blocks."""
    tree = ast.parse(text)
    loop = find_while(tree)
    pre = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.col_offset == loop.col_offset
                and node.end_lineno < loop.lineno):
            target = ast.unparse(node.targets[0])
            if target in ("go_path_initial", "ready_paths_initial",
                          "pv_go_paths", "pv_ready_paths"):
                pre.append(ast.get_source_segment(text, node))
    ifs = []
    for node in loop.body:
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(text, node)
            if "go_path_initial" in segment or "pv_go_paths" in segment:
                ifs.append(segment)
    assert len(pre) == 4 and len(ifs) == 2, (len(pre), len(ifs))
    return pre, ifs


def extract_old(text):
    """7cb7e84 runner: the two in-loop If blocks construct paths inline."""
    tree = ast.parse(text)
    loop = find_while(tree)
    ifs = []
    for node in loop.body:
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(text, node)
            if "live/'go.json'" in segment or "pv-go-{leg}" in segment:
                ifs.append(segment)
    assert len(ifs) == 2, len(ifs)
    return [], ifs


def compile_block(segment):
    return compile(ast.parse(segment), "<readiness>", "exec")


def make_namespace(live, workers):
    calls = {"save": 0, "loads": 0}
    clock = SimpleNamespace(tick=0, epoch="e" * 32, STEP_NS=1_000_000,
                            snapshot=lambda: {"tick": clock.tick})

    def save(path, value):
        calls["save"] += 1

    class CountingJson:
        @staticmethod
        def loads(raw):
            calls["loads"] += 1
            return json.loads(raw)

    namespace = {
        "live": live, "workers": workers, "pv": True, "clock": clock,
        "save": save, "result": {"run_id": "run-microbench"},
        "PV_PROFILE": "full_xyz_pv_yaw_v1", "json": CountingJson,
    }
    return namespace, calls, clock


def make_fixture(root):
    live = pathlib.Path(root)
    for name in ("go.json", "pv-go-1.json", "pv-go-2.json"):
        (live / name).write_text("{}")
    for stack in ("arducopter", "px4"):
        (live / stack).mkdir()
        (live / stack / "ready.json").write_text("{}")
        for leg in (1, 2):
            (live / stack / f"pv-ready-{leg}.json").write_text("{}")
    return live, {"arducopter": object(), "px4": object()}


def run_pass(pre_codes, if_codes, live, workers, count_fs=False):
    """One pass: optional pre-block once, then both If blocks per tick."""
    fs_calls = {"exists": 0, "is_file": 0}
    real_exists, real_is_file = pathlib.Path.exists, pathlib.Path.is_file
    if count_fs:
        def counting_exists(self):
            fs_calls["exists"] += 1
            return real_exists(self)

        def counting_is_file(self):
            fs_calls["is_file"] += 1
            return real_is_file(self)
        pathlib.Path.exists = counting_exists
        pathlib.Path.is_file = counting_is_file
    try:
        namespace, calls, clock = make_namespace(live, workers)
        for code in pre_codes:
            exec(code, namespace)
        wall_start, cpu_start = time.monotonic_ns(), time.thread_time_ns()
        for tick in range(TICKS):
            clock.tick = tick
            for code in if_codes:
                exec(code, namespace)
        wall_ns = time.monotonic_ns() - wall_start
        cpu_ns = time.thread_time_ns() - cpu_start
    finally:
        if count_fs:
            pathlib.Path.exists = real_exists
            pathlib.Path.is_file = real_is_file
    assert calls["save"] == 0 and calls["loads"] == 0, calls
    return wall_ns, cpu_ns, fs_calls


def main():
    new_text = NEW_RUNNER.read_text(encoding="utf-8")
    old_text = old_source()
    shas = {
        "new_runner": source_sha(NEW_RUNNER),
        "old_runner": hashlib.sha256(old_text.encode()).hexdigest(),
        "old_runner_git": "7cb7e84",
    }
    new_pre, new_ifs = extract_new(new_text)
    old_pre, old_ifs = extract_old(old_text)
    (HERE / "block-new-pre.py").write_text("\n".join(new_pre) + "\n", encoding="utf-8")
    (HERE / "block-new-inloop.py").write_text("\n\n".join(new_ifs) + "\n", encoding="utf-8")
    (HERE / "block-old-inloop.py").write_text("\n\n".join(old_ifs) + "\n", encoding="utf-8")

    new_codes = ([compile_block(s) for s in new_pre],
                 [compile_block(s) for s in new_ifs])
    old_codes = ([], [compile_block(s) for s in old_ifs])

    with tempfile.TemporaryDirectory(prefix="c2-readiness-") as tmp:
        live, workers = make_fixture(tmp)
        # Counting round (untimed): FS check frequency must be identical.
        _, _, fs_new = run_pass(*new_codes, live, workers, count_fs=True)
        _, _, fs_old = run_pass(*old_codes, live, workers, count_fs=True)
        assert fs_new == fs_old, (fs_new, fs_old)
        # Equal warmup for both arms before any measurement.
        for _ in range(WARMUP_PASSES):
            run_pass(*new_codes, live, workers)
            run_pass(*old_codes, live, workers)
        # Alternating measured passes, failures kept (no discarding).
        samples = {"new": [], "old": []}
        for round_index in range(PASSES):
            for arm, codes in (("new", new_codes), ("old", old_codes)):
                wall_ns, cpu_ns, _ = run_pass(*codes, live, workers)
                samples[arm].append({"round": round_index, "wall_ns": wall_ns,
                                     "thread_cpu_ns": cpu_ns})

    def medians(arm):
        rows = samples[arm]
        return {
            "wall_ns_median": statistics.median(r["wall_ns"] for r in rows),
            "thread_cpu_ns_median": statistics.median(r["thread_cpu_ns"] for r in rows),
            "wall_ns_per_tick_median": statistics.median(r["wall_ns"] for r in rows) / TICKS,
            "thread_cpu_ns_per_tick_median": statistics.median(r["thread_cpu_ns"] for r in rows) / TICKS,
        }

    result = {
        "kind": "c2-readiness-microbench",
        "schema": "wksim.c2-readiness-microbench.v1",
        "scope": ("readiness go/ready path handling only: the reduction is in "
                  "Path construction frequency at identical FS-check frequency; "
                  "nothing about PV/0.5x/100ms acceptance is claimed"),
        "shas": shas,
        "extraction": {
            "method": ("ast.parse of each runner source; while loop located by "
                       "MAX_TICKS test; new arm = 4 pre-loop Assign blocks "
                       "(go_path_initial/ready_paths_initial/pv_go_paths/"
                       "pv_ready_paths, col_offset == loop-4) + 2 in-loop If "
                       "blocks matched by 'go_path_initial'/'pv_go_paths'; "
                       "old arm = 2 in-loop If blocks matched by "
                       "\"live/'go.json'\"/\"pv-go-{leg}\"; blocks compiled "
                       "verbatim and exec'd per tick"),
        },
        "fixture": {
            "ticks_per_pass": TICKS, "passes_per_arm": PASSES,
            "warmup_passes_per_arm": WARMUP_PASSES,
            "preexisting": ["go.json", "pv-go-1.json", "pv-go-2.json",
                            "<stack>/ready.json", "<stack>/pv-ready-<leg>.json"],
            "workers": ["arducopter", "px4"], "pv": True,
            "save_calls": 0, "json_loads_calls": 0,
        },
        "fs_check_frequency": {"new": fs_new, "old": fs_old,
                               "identical": fs_new == fs_old},
        "samples": samples,
        "medians": {"new": medians("new"), "old": medians("old"),
                    "wall_ns_per_tick_delta":
                        medians("new")["wall_ns_per_tick_median"]
                        - medians("old")["wall_ns_per_tick_median"],
                    "thread_cpu_ns_per_tick_delta":
                        medians("new")["thread_cpu_ns_per_tick_median"]
                        - medians("old")["thread_cpu_ns_per_tick_median"]},
        "limits": [
            "exec-per-tick harness overhead is identical in both arms; only the delta is meaningful",
            "one host, one process, no interleaving with other load; cold/hot mixing is not extrapolated",
            "the fired branches (save/read content) never ran: fixture keeps go/pv-go files present",
        ],
    }
    out = HERE / "result.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"result": str(out),
                      "wall_per_tick_ns": {a: medians(a)["wall_ns_per_tick_median"]
                                           for a in ("new", "old")},
                      "cpu_per_tick_ns": {a: medians(a)["thread_cpu_ns_per_tick_median"]
                                          for a in ("new", "old")},
                      "fs_identical": fs_new == fs_old}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
