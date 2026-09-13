"""Read-only, schema-bound check of one retained PX4 duplicate-status event."""
import hashlib, json, pathlib, sys
ROOT = pathlib.Path("/mnt/c/Users/PC/Documents/odid编译/wksim")
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from px4_msgs.msg import VehicleStatus
from prometheus_msgs.msg import TextInfo
from audit_pv_trajectory import decoder_message_packages
from audit_mixed_control import identical_status_duplicate
from Simulator.wksim_runtime.joint_profile import package_digest
raw = pathlib.Path("/root/wksim-release-acceptance-fe3/validation/joint-public-flight-1w6dru32")
result = json.loads((raw / "result.json").read_text())
for name, pin in decoder_message_packages(result, "mixed_admission").items():
    if package_digest(pin["prefix"], complete=pin.get("complete_snapshot",False)) != pin["sha256"]:
        raise ValueError("Decoder package identity differs: " + name)
statuses, events = [], []
h = hashlib.sha256()
with (raw / "pv-dds.jsonl").open("rb") as stream:
    for line in stream:
        h.update(line)
        row = json.loads(line)
        if "/out/vehicle_status" in row["topic"]:
            message = message_to_ordereddict(deserialize_message(bytes.fromhex(row["cdr_hex"]), VehicleStatus))
            if message["timestamp"] == 107296000:
                statuses.append((row,message))
        elif row["topic"] == "/uav2/prometheus/text_info":
            message = message_to_ordereddict(deserialize_message(bytes.fromhex(row["cdr_hex"]), TextInfo))
            event = json.loads(message["message"])
            if event.get("reason") == "duplicate_source" and event.get("source_stamp") == 107296000:
                events.append((row,event))
if len(events) != 1:
    raise ValueError("Expected one exact retained rejection event")
row,event = events[0]
report = dict(run_id=result["run_id"], epoch=result["scene_epoch"], event=event,
              event_row=row, statuses=statuses, status_count=len(statuses),
              corroborated_by_existing_mixed_rule=identical_status_duplicate(event,row,
                  {"/out/vehicle_status":statuses},"px4"),
              raw_cdr_equal=len({r["cdr_hex"] for r,_ in statuses}) == 1,
              evidence_sha256=h.hexdigest(),
              helper_sha256=hashlib.sha256((ROOT/"tools/audit_mixed_control.py").read_bytes()).hexdigest(),
              checker_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
              full_acceptance=False)
out = ROOT / "validation/coordination/current-control-contract-20260913/status-duplicate-check.json"
with out.open("x") as f:
    json.dump(report,f,indent=2)
print(json.dumps({k:report[k] for k in ("status_count","corroborated_by_existing_mixed_rule","raw_cdr_equal","evidence_sha256")}))

