"""Collect every failed physical predicate from retained evidence; diagnostic only.

Runs the unchanged physical() traversal with a local failure collector. Timeline
validation remains fail-fast. A failed predicate is counted, never made passing.
No raw input is modified, and the output grants no acceptance.
"""
import collections, hashlib, inspect, json, pathlib, sys
ROOT = pathlib.Path("/mnt/c/Users/PC/Documents/odid编译/wksim")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import audit_pv_trajectory as audit
raw = pathlib.Path("/root/wksim-release-acceptance-fe3/validation/joint-public-flight-xtj8wk8i")
result = json.loads((raw / "result.json").read_text())
tasks = {stack: value["task"] for stack, value in result["tasks"].items()}
phases = {stack: {p["phase"]: p for p in value["phases"]} for stack, value in result["tasks"].items()}
counts = collections.Counter()
examples = []
tick_maps = {}
def collect(condition, message):
    if condition:
        return
    frame = inspect.currentframe().f_back
    call = frame
    while call and call.f_code.co_name != "physical":
        call = call.f_back
    context = call.f_locals if call else {}
    stack = context.get("stack")
    counts[(stack, message)] += 1
    rows, state = context.get("rows"), context.get("state")
    if isinstance(rows, list) and stack not in tick_maps:
        tick_maps[stack] = {id(value): i + 1 for i, value in enumerate(rows)}
    tick = tick_maps.get(stack, {}).get(id(state))
    if len(examples) < 30:
        metrics = frame.f_locals.get("metrics")
        if message.startswith("Baseline") and state is not None:
            p, v, yaw = audit.enu(state)
            metrics = [audit.math.dist(p, [2,3,3]), audit.math.hypot(*v), abs(yaw)]
        examples.append(dict(stack=stack, message=message, tick=tick, leg=context.get("leg"),
                             phase=context.get("start"), metrics=metrics))
    del frame, call
original = audit.require
audit.require = collect
try:
    traversal = audit.physical(raw, result, tasks, phases)
finally:
    audit.require = original
report = dict(scope="All original physical predicates collected; no threshold or window change; no acceptance",
              run_id=result["run_id"], epoch=result["scene_epoch"], accepted=False,
              failed_predicates=sum(counts.values()),
              counts=[dict(stack=k[0], message=k[1], count=v) for k,v in counts.items()],
              examples=examples, traversal=traversal,
              auditor_sha256=hashlib.sha256(pathlib.Path(audit.__file__).read_bytes()).hexdigest(),
              collector_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest())
out = ROOT / "validation/coordination/current-control-contract-20260913/all-physical-gates.json"
with out.open("x") as f:
    json.dump(report,f,indent=2)
print(json.dumps({k: report[k] for k in ("run_id","accepted","failed_predicates","counts","examples")},indent=2))

