"""Verify this diagnostic's immutable inputs and output equivalence, after execution."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = HERE.parents[3]
sha = lambda data: hashlib.sha256(data).hexdigest()

before = json.loads((HERE / "input-checks.json").read_bytes())
post = []
for row in before:
    actual = sha(Path(row["path"]).read_bytes())
    post.append({"path": row["path"], "before": row["actual"], "after": actual,
                 "unchanged": actual == row["actual"], "used": row["used"]})
probe_before = sha((HERE / "probe-source.m.txt").read_bytes())
probe_after = sha((ROOT / "tools/probe_reference_first_step.m").read_bytes())
resolver_before = sha((HERE / "resolver-source.m.txt").read_bytes())
resolver_after = sha((ROOT / "tools/resolve_probe_solver_input.m").read_bytes())
old_bytes = (BASE / "run-03/reference-first-step.json").read_bytes()
new_bytes = (BASE / "run-05/reference-first-step.json").read_bytes()
old = json.loads(old_bytes)
new = json.loads(new_bytes)
mode = new.get("pqr_input_probe", {})
result = {
    "scope": "First-step reference diagnostic; not full R1 or G6 acceptance",
    "reference_report_sha256": sha(new_bytes),
    "previous_reference_report_sha256": sha(old_bytes),
    "probe_before_sha256": probe_before,
    "probe_after_sha256": probe_after,
    "probe_unchanged": probe_before == probe_after,
    "resolver_before_sha256": resolver_before,
    "resolver_after_sha256": resolver_after,
    "resolver_unchanged": resolver_before == resolver_after,
    "input_post_checks": post,
    "major_times_identical": new.get("major_times") == old["major_times"],
    "major_outputs_identical": new.get("major_outputs") == old["major_outputs"],
    "integrator_events_identical": new.get("events") == old["events"],
    "dropped_events": new.get("dropped_events"),
    "pqr_input_probe": mode,
    "reference_status": new.get("status"),
}
with (HERE / "analysis.json").open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
assert all(row["unchanged"] for row in post if row["used"])
assert result["probe_unchanged"]
assert result["resolver_unchanged"]
assert result["major_times_identical"] and result["major_outputs_identical"]
assert result["integrator_events_identical"] and result["dropped_events"] == 0
print(json.dumps({key: value for key, value in result.items()
                  if key not in ("input_post_checks", "pqr_input_probe")}))
print(json.dumps({"pqr_status": mode.get("status"), "pqr_reason": mode.get("reason"),
                  "event_count": mode.get("event_count"),
                  "dropped_events": mode.get("dropped_events"),
                  "upstream": mode.get("upstream")}))
