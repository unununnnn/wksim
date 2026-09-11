"""Fail-closed audit for issue #29 terrain evidence.

Verifies all retained evidence for issue #29:
- Strict JSON parsing (rejection of duplicate keys, NaN, Infinity, extra fields).
- Canonical repository-relative paths and step-by-step symlink/path-escape rejection.
- Two distinct scene identities pinned without conflation:
    * 60ae5097...: static plane/box fixture (#80) & display-manifest (#81)
    * 4889e2ea...: real generated model probe scene with tick-0 ENU origin
- Cross-check of run/epoch/stack, 50x120 truth trace rows, Terrain15D inputs,
  model/wrapper/archive SHA-256 hashes, cold reset under a new epoch with exact
  state replay, and clean worker exit/reaping.
- Verification of existing #80 static contact and #81 live contact audit outputs.
- Enforces honest verdict: status=partial_open, acceptance=false, blocking_issue=9,
  recording remaining gaps (no real UE colocation, no FC closed-loop, no slope/
  contact-force/side/dynamic collision dynamics).

Usage:
    python3 -B tools/audit_29_terrain_evidence.py [--manifest PATH] [--output REPORT]
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/plan/29-terrain-evidence-manifest.json"
MANIFEST_SCHEMA = "wksim.29-terrain-evidence.v1"
REPORT_SCHEMA = "wksim.29-terrain-evidence-audit.v1"

SCENE_VISUAL_STATIC = "60ae50970e23d35e0a28b22694d61ca85c4e10af1f574a6ca9f07c79f7e03514"
SCENE_REAL_TERRAIN = "4889e2ea32146b734a816281915842da1da27c0df78c588d688cd2656f2bb300"
EXPECTED_STATE_DIM = 120
EXPECTED_TERRAIN_DIM = 15
EXPECTED_TICKS = 50
EXPECTED_WORKER_COUNT = 6
EXPECTED_TOTAL_PINS = 24


def digest(path_or_bytes):
    """Compute SHA-256 hex digest of file or bytes."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return hashlib.sha256(path_or_bytes).hexdigest()
    return hashlib.sha256(Path(path_or_bytes).read_bytes()).hexdigest()


def load_strict_json(path_or_text):
    """Load JSON refusing duplicate keys, NaN, and Infinity."""
    if isinstance(path_or_text, Path):
        text = path_or_text.read_text(encoding="utf-8")
    elif isinstance(path_or_text, str):
        trimmed = path_or_text.strip()
        if trimmed.startswith(("{", "[")) or "\n" in path_or_text:
            text = path_or_text
        else:
            try:
                p = Path(path_or_text)
                if p.is_file():
                    text = p.read_text(encoding="utf-8")
                else:
                    text = path_or_text
            except OSError:
                text = path_or_text
    else:
        text = str(path_or_text)

    def _object_pairs_hook(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError(f"duplicate key in JSON: {k!r}")
            obj[k] = v
        return obj

    def _constant_handler(const):
        raise ValueError(f"illegal constant in JSON: {const!r}")

    return json.loads(text, object_pairs_hook=_object_pairs_hook, parse_constant=_constant_handler)


def verify_secure_path(root, relative_str):
    """Verify relative_str is a canonical relative path within root; refuse links."""
    p_rel = Path(relative_str)
    if p_rel.is_absolute():
        raise ValueError(f"path must be relative: {relative_str}")
    if any(part in ("..", ".", "") for part in p_rel.parts):
        raise ValueError(f"path must be normalized relative without '..' or '.': {relative_str}")

    root_resolved = Path(root).resolve()
    full_path = root_resolved / p_rel

    is_junction = getattr(os.path, "isjunction", None)
    current = root_resolved
    for part in p_rel.parts:
        current = current / part
        if current.is_symlink() or (is_junction is not None and is_junction(current)):
            raise ValueError(f"symlink/reparse point detected in path: {relative_str}")

    if not full_path.is_file():
        raise ValueError(f"path is not a regular file: {relative_str}")

    try:
        full_path.resolve().relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path escapes repository root: {relative_str}") from exc

    return full_path


def _check_manifest_invariants(manifest, report):
    """Verify top-level manifest fields and reject pass/closure attempts."""
    if manifest.get("schema") != MANIFEST_SCHEMA:
        report["violations"].append(f"manifest schema mismatch: {manifest.get('schema')}")
    if manifest.get("kind") != "terrain_evidence_manifest":
        report["violations"].append(f"manifest kind mismatch: {manifest.get('kind')}")
    if manifest.get("issue") != 29:
        report["violations"].append(f"manifest issue mismatch: {manifest.get('issue')}")
    if manifest.get("status") != "partial_open":
        report["violations"].append(
            f"manifest status must be 'partial_open', got: {manifest.get('status')}"
        )
    if manifest.get("acceptance") is not False:
        report["violations"].append(
            f"manifest acceptance must be false, got: {manifest.get('acceptance')}"
        )
    if manifest.get("blocking_issue") != 9:
        report["violations"].append(
            f"manifest blocking_issue must be 9, got: {manifest.get('blocking_issue')}"
        )

    scenes = manifest.get("scene_identities") or {}
    vis = scenes.get("visual_static_scene") or {}
    real = scenes.get("real_terrain_scene") or {}
    if vis.get("scene_sha256") != SCENE_VISUAL_STATIC:
        report["violations"].append(f"visual_static_scene hash mismatch: {vis.get('scene_sha256')}")
    if real.get("scene_sha256") != SCENE_REAL_TERRAIN:
        report["violations"].append(f"real_terrain_scene hash mismatch: {real.get('scene_sha256')}")
    if vis.get("scene_sha256") == real.get("scene_sha256"):
        report["violations"].append("visual_static_scene and real_terrain_scene must not be identical")

    boundaries = manifest.get("unproven_boundaries") or {}
    required_boundaries = (
        "missing_real_ue_physics_colocation",
        "missing_fc_closed_loop",
        "missing_slope_contact_force_dynamics",
    )
    for req in required_boundaries:
        if req not in boundaries:
            report["violations"].append(f"missing required unproven boundary declaration: {req}")


def _check_pins(manifest, root, report):
    """Verify all evidence pins exist securely and match their pinned SHA-256."""
    pins_checked = 0
    evidence_pins = manifest.get("evidence_pins") or {}

    def _verify_pin(pin_entry, context):
        nonlocal pins_checked
        rel = pin_entry.get("path")
        expected_sha = pin_entry.get("sha256")
        expected_size = pin_entry.get("size_bytes")
        if not rel or not expected_sha:
            report["violations"].append(f"{context}: pin missing path or sha256: {pin_entry}")
            return
        if expected_size is not None and (isinstance(expected_size, bool)
                                          or not isinstance(expected_size, int)
                                          or expected_size < 0):
            report["violations"].append(f"{context}: pin size_bytes must be a nonnegative integer: {rel}")
            return
        try:
            secure_path = verify_secure_path(root, rel)
            actual_sha = digest(secure_path)
            if actual_sha != expected_sha:
                report["violations"].append(
                    f"{context}: pinned file SHA-256 mismatch / drifted: {rel} (expected {expected_sha}, got {actual_sha})"
                )
            if expected_size is not None and secure_path.stat().st_size != expected_size:
                report["violations"].append(
                    f"{context}: pinned file size mismatch: {rel} (expected {expected_size})"
                )
            pins_checked += 1
        except Exception as exc:
            report["violations"].append(f"{context}: secure path verification failed for {rel}: {exc}")

    # Top-level report pin
    report_pin = evidence_pins.get("report")
    if report_pin:
        _verify_pin(report_pin, "report")
    else:
        report["violations"].append("missing report pin in evidence_pins")

    # Grouped pins
    for group_name in ("static_contact_80", "live_contact_81", "terrain_reset_probe", "real_terrain_initial_probe"):
        group = evidence_pins.get(group_name)
        if not group:
            report["violations"].append(f"missing evidence group: {group_name}")
            continue
        for pin in group.get("pins", []):
            _verify_pin(pin, group_name)

    report["verified_counts"]["pins"] = pins_checked
    if pins_checked != EXPECTED_TOTAL_PINS:
        report["violations"].append(
            f"expected {EXPECTED_TOTAL_PINS} total pins in manifest, checked {pins_checked}"
        )


def _check_scene_identity_isolation(manifest, root, report):
    """Verify that visual/static (60ae...) and real terrain (4889...) scenes are never conflated."""
    try:
        # 1. Base static scene config
        static_scene_file = verify_secure_path(root, "Simulator/wksim_runtime/static-scene-v1.json")
        static_cfg = load_strict_json(static_scene_file)
        if static_cfg.get("scene_sha256") != SCENE_VISUAL_STATIC:
            report["violations"].append(f"static-scene-v1.json scene_sha256 is not 60ae...: {static_cfg.get('scene_sha256')}")
        if static_cfg.get("scene_sha256") == SCENE_REAL_TERRAIN:
            report["violations"].append("static-scene-v1.json conflated with real terrain scene 4889...")

        # 2. Visual/static contact results in #80 results.jsonl
        results_file = verify_secure_path(root, "validation/lunar-29-static-contact/results.jsonl")
        for line in results_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = load_strict_json(line)
            env = rec.get("envelope")
            if env:
                c_hash = env.get("scene_hash")
                if c_hash != SCENE_VISUAL_STATIC:
                    report["violations"].append(f"#80 result envelope scene_hash is not 60ae...: {c_hash}")
                if c_hash == SCENE_REAL_TERRAIN:
                    report["violations"].append("#80 result envelope conflated with real terrain scene 4889...")

        # 3. Visual/static contact display manifest in #81
        disp_file = verify_secure_path(root, "validation/lunar-29-live-contact/display-manifest.json")
        disp_data = load_strict_json(disp_file)
        d_hash = disp_data.get("scene_hash")
        if d_hash != SCENE_VISUAL_STATIC:
            report["violations"].append(f"#81 display-manifest scene_hash is not 60ae...: {d_hash}")
        if d_hash == SCENE_REAL_TERRAIN:
            report["violations"].append("#81 display-manifest scene_hash conflated with real terrain scene 4889...")

        # 4. Real terrain scene files in c8f05c6e and 9d3a7c21
        for rel_scene in (
            "validation/lunar-29-terrain-reset-c8f05c6e/elevated-scene.json",
            "validation/lunar-29-terrain-reset-c8f05c6e/elevated_reset-scene.json",
            "validation/lunar-29-real-terrain-9d3a7c21/elevated-scene.json",
        ):
            scene_file = verify_secure_path(root, rel_scene)
            scene_data = load_strict_json(scene_file)
            s_hash = scene_data.get("scene_sha256")
            if s_hash != SCENE_REAL_TERRAIN:
                report["violations"].append(f"{rel_scene} scene_sha256 is not 4889...: {s_hash}")
            if s_hash == SCENE_VISUAL_STATIC:
                report["violations"].append(f"{rel_scene} scene_sha256 conflated with visual static scene 60ae...")

        # 5. Result.json scene manifest & scene config checks
        result_file = verify_secure_path(root, "validation/lunar-29-terrain-reset-c8f05c6e/result.json")
        result_data = load_strict_json(result_file)
        for s_key in ("elevated", "elevated_reset"):
            sc = result_data.get("scenarios", {}).get(s_key, {}) or {}
            sm_hash = sc.get("scene_hash") or (sc.get("scene_manifest", {}) or {}).get("scene_hash")
            sc_hash = (sc.get("scene_config", {}) or {}).get("scene_sha256")
            for h in (sm_hash, sc_hash):
                if h != SCENE_REAL_TERRAIN:
                    report["violations"].append(f"result.json {s_key} scene hash is not 4889...: {h}")
                if h == SCENE_VISUAL_STATIC:
                    report["violations"].append(f"result.json {s_key} conflated with visual static scene 60ae...")

    except Exception as exc:
        report["violations"].append(f"scene identity isolation check failed: {exc}")


def _check_truth_traces_and_cold_reset(root, report):
    """Verify 50x120 truth traces, Terrain15D ingress, cold reset equality under distinct epochs."""
    reset_dir = "validation/lunar-29-terrain-reset-c8f05c6e"
    trace_files = [
        "baseline-arducopter-truth.jsonl",
        "baseline-px4-truth.jsonl",
        "elevated-arducopter-truth.jsonl",
        "elevated-px4-truth.jsonl",
        "elevated_reset-arducopter-truth.jsonl",
        "elevated_reset-px4-truth.jsonl",
    ]

    total_rows = 0
    traces = {}

    for name in trace_files:
        rel = f"{reset_dir}/{name}"
        try:
            path = verify_secure_path(root, rel)
            raw_lines = path.read_text(encoding="utf-8").strip().splitlines()
            if len(raw_lines) != EXPECTED_TICKS:
                report["violations"].append(f"{rel}: expected {EXPECTED_TICKS} rows, got {len(raw_lines)}")
                continue

            parsed_rows = []
            trace_epoch = None
            for idx, line in enumerate(raw_lines, 1):
                row = load_strict_json(line)
                state = row.get("state")
                terrain = row.get("terrain")
                if not isinstance(state, list) or len(state) != EXPECTED_STATE_DIM:
                    report["violations"].append(f"{rel} row {idx}: state length is not {EXPECTED_STATE_DIM}")
                if not isinstance(terrain, list) or len(terrain) != EXPECTED_TERRAIN_DIM:
                    report["violations"].append(f"{rel} row {idx}: terrain length is not {EXPECTED_TERRAIN_DIM}")
                epoch = row.get("epoch")
                if not epoch or not isinstance(epoch, str):
                    report["violations"].append(f"{rel} row {idx}: missing epoch")
                elif trace_epoch is None:
                    trace_epoch = epoch
                elif epoch != trace_epoch:
                    report["violations"].append(f"{rel} row {idx}: mixed epochs inside one trace")
                if row.get("tick") != idx:
                    report["violations"].append(f"{rel} row {idx}: tick is not the 1-based row index")
                # Strict time-axis alignment: the frozen axis is the 1 ms fixed
                # step (result.json fixed_step_ns), so tick N is exactly time
                # (N-1)*1ms after the epoch start; every embedded copy of the
                # tick must agree.  No separate sim_time field exists in this
                # evidence; there is no 0.004 s cadence anywhere in it.
                if row.get("version") != 1:
                    report["violations"].append(f"{rel} row {idx}: version is not 1")
                request = row.get("request")
                if not isinstance(request, dict) or request.get("tick") != idx \
                        or request.get("epoch") != epoch:
                    report["violations"].append(f"{rel} row {idx}: request tick/epoch disagrees with the row")
                raw_input = row.get("input")
                if not isinstance(raw_input, str):
                    report["violations"].append(f"{rel} row {idx}: input is not an embedded JSON string")
                else:
                    embedded = load_strict_json(raw_input)
                    if embedded.get("tick") != idx or embedded.get("epoch") != epoch:
                        report["violations"].append(f"{rel} row {idx}: embedded input tick/epoch disagrees with the row")
                parsed_rows.append(row)
                total_rows += 1

            traces[name] = parsed_rows
        except Exception as exc:
            report["violations"].append(f"failed reading truth trace {rel}: {exc}")

    report["verified_counts"]["truth_trace_files_checked"] = len(traces)
    report["verified_counts"]["truth_trace_rows_checked"] = total_rows

    # Verify Terrain15D input expectations
    for stack in ("arducopter", "px4"):
        b_name = f"baseline-{stack}-truth.jsonl"
        e_name = f"elevated-{stack}-truth.jsonl"
        r_name = f"elevated_reset-{stack}-truth.jsonl"

        if b_name in traces:
            for row in traces[b_name]:
                if any(v != 0.0 for v in row["terrain"]):
                    report["violations"].append(f"{b_name} terrain contains non-zero in baseline")
                    break

        for target_name in (e_name, r_name):
            if target_name in traces:
                for row in traces[target_name]:
                    t = row["terrain"]
                    if t[0] != -1.0 or any(v != 0.0 for v in t[1:]):
                        report["violations"].append(f"{target_name} terrain does not match [-1.0, 0.0 x14]")
                        break

    # Cold reset exact replay check: elevated vs elevated_reset
    for stack in ("arducopter", "px4"):
        e_name = f"elevated-{stack}-truth.jsonl"
        r_name = f"elevated_reset-{stack}-truth.jsonl"
        if e_name in traces and r_name in traces:
            e_rows = traces[e_name]
            r_rows = traces[r_name]
            # Epochs must be distinct
            e_epoch = e_rows[0].get("epoch")
            r_epoch = r_rows[0].get("epoch")
            if not e_epoch or not r_epoch:
                report["violations"].append(f"{stack}: missing epoch in trace rows")
            elif e_epoch == r_epoch:
                report["violations"].append(f"{stack}: cold reset epoch must differ from elevated epoch")

            # States must be identical across all 50 ticks
            for tick in range(EXPECTED_TICKS):
                if e_rows[tick]["state"] != r_rows[tick]["state"]:
                    report["violations"].append(f"{stack} tick {tick+1}: state drift between elevated and cold reset")
                    break


def _check_result_json_metadata(root, report):
    """Verify result.json execution metadata, worker exit codes, library/wrapper hashes."""
    rel = "validation/lunar-29-terrain-reset-c8f05c6e/result.json"
    try:
        path = verify_secure_path(root, rel)
        res = load_strict_json(path)

        if res.get("status") != "passed":
            report["violations"].append(f"result.json status is not 'passed': {res.get('status')}")
        if res.get("ticks") != EXPECTED_TICKS:
            report["violations"].append(f"result.json ticks is not {EXPECTED_TICKS}: {res.get('ticks')}")
        if res.get("fixed_step_ns") != 1_000_000:
            report["violations"].append(f"result.json fixed_step_ns is not 1ms: {res.get('fixed_step_ns')}")

        comp = res.get("elevated_reset_comparison") or {}
        if comp.get("epoch_changed") is not True:
            report["violations"].append("result.json elevated_reset_comparison.epoch_changed is not True")
        if comp.get("reason_code") != "cold_reset_elevated_exact_replay":
            report["violations"].append(
                f"result.json elevated_reset_comparison.reason_code mismatch: {comp.get('reason_code')}"
            )
        if comp.get("scene_hash_equal") is not True:
            report["violations"].append("result.json elevated_reset_comparison.scene_hash_equal is not True")

        # Worker children check
        scenarios = res.get("scenarios") or {}
        reaped_workers = 0
        pids = set()
        for sc_name, sc_data in scenarios.items():
            children = sc_data.get("children", [])
            for child in children:
                reaped_workers += 1
                pid = child.get("pid")
                if pid in pids:
                    report["violations"].append(f"duplicate worker PID detected: {pid}")
                pids.add(pid)
                if child.get("returncode") != 0:
                    report["violations"].append(
                        f"worker {sc_name} pid {pid} returned non-zero code {child.get('returncode')}"
                    )
                if child.get("reaped") is not True:
                    report["violations"].append(f"worker {sc_name} pid {pid} was not reaped")

        report["verified_counts"]["workers_reaped"] = reaped_workers
        if reaped_workers != EXPECTED_WORKER_COUNT:
            report["violations"].append(
                f"expected {EXPECTED_WORKER_COUNT} reaped workers across scenarios, found {reaped_workers}"
            )

        # Model build cross-check
        mb_file = verify_secure_path(root, "validation/lunar-29-terrain-reset-c8f05c6e/model-build.json")
        mb = load_strict_json(mb_file)
        if mb.get("library_sha256") != res.get("library", {}).get("sha256"):
            report["violations"].append("model-build library_sha256 does not match result.json library.sha256")
        if mb.get("wrapper_sha256") != res.get("source_sha256", {}).get("Simulator/wksim_core/model.cpp"):
            report["violations"].append("model-build wrapper_sha256 does not match result.json model.cpp sha256")

    except Exception as exc:
        report["violations"].append(f"result.json metadata check failed: {exc}")


def _check_existing_audits(root, report):
    """Cross-check upstream #80/#81 report structure and row counts only.

    The upstream assertion totals (85 / 30895) are self-reported by the #80/#81
    reports and are recorded under ``upstream_declared`` — never recomputed here.
    """
    # This audit independently checks ONLY their report structure and row counts;
    # it never recomputes upstream assertions and never claims to.
    # #80: 85 assertions, 13 cases (upstream-declared)
    try:
        sc_cases = load_strict_json(verify_secure_path(root, "validation/lunar-29-static-contact/cases.json"))
        sc_results = verify_secure_path(root, "validation/lunar-29-static-contact/results.jsonl").read_text(
            encoding="utf-8"
        ).strip().splitlines()
        if len(sc_cases) != 13 or len(sc_results) != 13:
            report["violations"].append(
                f"#80 static contact cases/results count mismatch: {len(sc_cases)} cases, {len(sc_results)} results"
            )
        report["upstream_declared"]["static_assertions_80"] = 85
    except Exception as exc:
        report["violations"].append(f"#80 static contact data check failed: {exc}")

    # #81: 30895 assertions, 3253 rows (upstream-declared)
    try:
        live_cfg = load_strict_json(verify_secure_path(root, "validation/lunar-29-live-contact/run-config.json"))
        live_truth = verify_secure_path(root, live_cfg["truth_source"]).read_text(encoding="utf-8").strip().splitlines()
        live_records = verify_secure_path(root, "validation/lunar-29-live-contact/records.jsonl").read_text(
            encoding="utf-8"
        ).strip().splitlines()
        if len(live_truth) != 3253 or len(live_records) != 3253:
            report["violations"].append(
                f"#81 live contact rows mismatch: {len(live_truth)} truth, {len(live_records)} records"
            )
        report["upstream_declared"]["live_assertions_81"] = 30895
    except Exception as exc:
        report["violations"].append(f"#81 live contact data check failed: {exc}")


def audit(manifest_path=DEFAULT_MANIFEST, root=ROOT):
    """Perform fail-closed audit of #29 terrain evidence."""
    report = {
        "schema": REPORT_SCHEMA,
        "status": "partial_open",
        "acceptance": False,
        "blocking_issue": 9,
        "claim": (
            "Provenance and partial verification boundary of #29 terrain evidence; "
            "traces, workers and hashes are recomputed here, while result.json status "
            "and upstream #80/#81 assertion totals remain self-reported; "
            "parent ticket #29 remains OPEN blocked by #9, #17, #23"
        ),
        "non_claims": [
            "no independent recomputation of upstream #80/#81 assertion logic",
            "result.json status field is self-reported metadata, not independent proof",
            "no real UE physics colocation, no FC closed loop, no slope contact force dynamics",
            "not a pass or closure of #29; acceptance stays false",
        ],
        "scene_identities": {
            "visual_static_scene": SCENE_VISUAL_STATIC,
            "real_terrain_scene": SCENE_REAL_TERRAIN,
            "distinct": True,
        },
        "unproven_boundaries": {},
        "verified_counts": {
            "pins": 0,
            "truth_trace_files_checked": 0,
            "truth_trace_rows_checked": 0,
            "state_dimension": EXPECTED_STATE_DIM,
            "terrain_dimension": EXPECTED_TERRAIN_DIM,
            "workers_reaped": 0,
        },
        "upstream_declared": {},
        "violations": [],
    }

    # The manifest itself must live inside the audit root: absolute paths are
    # rejected unless they resolve under root; every component is checked for
    # symlinks/reparse points and the resolved file must not escape root.
    try:
        rel = Path(manifest_path)
        if rel.is_absolute():
            rel = rel.resolve().relative_to(Path(root).resolve())
        manifest_file = verify_secure_path(root, rel.as_posix())
    except Exception:
        report["status"] = "audit_failed"
        report["violations"].append(
            f"manifest path must be inside the audit root without symlink/escape: {manifest_path}")
        return report

    try:
        manifest = load_strict_json(manifest_file)
    except Exception as exc:
        report["status"] = "audit_failed"
        report["violations"].append(f"manifest strict JSON parse error: {exc}")
        return report

    report["unproven_boundaries"] = manifest.get("unproven_boundaries", {})

    _check_manifest_invariants(manifest, report)
    _check_pins(manifest, root, report)
    _check_scene_identity_isolation(manifest, root, report)
    _check_truth_traces_and_cold_reset(root, report)
    _check_result_json_metadata(root, report)
    _check_existing_audits(root, report)

    if report["violations"]:
        report["status"] = "audit_failed"
        report["acceptance"] = False
    else:
        # Honest invariant: must remain partial_open and acceptance=False
        report["status"] = "partial_open"
        report["acceptance"] = False

    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = audit(args.manifest, root=args.root)
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"

    if args.output:
        args.output.write_text(raw, encoding="utf-8", newline="\n")

    sys.stdout.buffer.write(raw.encode("utf-8"))
    return 0 if report["status"] == "partial_open" and not report["violations"] else 2


if __name__ == "__main__":
    sys.exit(main())
