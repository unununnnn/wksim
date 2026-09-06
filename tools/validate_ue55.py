"""Windows live UE5.5 boundary gate; called by validate-ue55.ps1 after UE ready.

Starts a fresh private-network WSL DDS flight, coalesces its live truth to UE,
withholds visual packets for 3 wall seconds while airborne, checks Actor readback
and real engine screenshots. All thresholds precede the run. No vendor numerical
equivalence or completed Prometheus migration is claimed by this test.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from Simulator.ue55.bridge import LatestTruth, actor_errors, packet_from_truth


def wsl_path(path):
    path = path.resolve().as_posix()
    if not re.match(r"^[A-Za-z]:/", path):
        raise ValueError("Expected a drive-qualified Windows path")
    return "/mnt/" + path[0].lower() + path[2:]


def invalid_probes(packet):
    base = dict(packet, sequence=packet["sequence"]+1, sim_time_s=packet["sim_time_s"]+0.001)
    probes = [dict(base, run_id="f"*32), dict(base, vehicle_id="foreign"), packet,
              dict(base, sim_time_s=packet["sim_time_s"]), dict(base, version=2),
              dict(base, quaternion_wxyz=[0, 0, 0, 0]), dict(base, position_ned_m=[0, 0]),
              dict(base, rotor_rpm=[-1, 0, 0, 0]), dict(base, position_ned_m=[math.nan, 0, 0])]
    return [json.dumps(p).encode() for p in probes]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", choices=("px4", "arducopter"), required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--port", type=int, default=19060)
    parser.add_argument("--dds-workspace", default="/root/wksim-dds-VxM6Ni")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    result = dict(status="failed", stack=args.stack, run_id=args.run_id,
                  scope="Live independent physics to native UE5.5 Actor + screenshots; not full-product acceptance",
                  # UE SceneComponent compares locations with 1e-4 cm per axis
                  # and rotators with 1e-4 degrees. Budgets bound their 3D norms,
                  # rather than treating transform update suppression as drift.
                  thresholds=dict(position_cm=2e-4, quaternion_l2=2e-6, sim_time_s=1e-8,
                                  minimum_acks=30, minimum_rendered_live_frames=1,
                                  visual_pause_wall_s=3.0, stale_after_wall_s=0.75,
                                  outage_sim_progress_s=1.0, overall_wall_s=160),
                  sent=0, acknowledged=0, max_error=dict(position_cm=0., quaternion_l2=0., sim_time_s=0.))
    result["source_sha256"] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [Path(__file__), REPO/"Simulator/ue55/bridge.py"]}
    (evidence/"thresholds.json").write_text(json.dumps(result["thresholds"], indent=2), encoding="utf-8")
    argv = ["wsl.exe", "-d", "Ubuntu-22.04", "--exec", "bash",
            wsl_path(REPO/"tools/run-dds-validation.sh"), args.stack, args.dds_workspace]
    result["flight_argv"] = argv
    started = time.monotonic()
    child = None
    try:
        with (evidence/"flight.log").open("x", encoding="utf-8") as log, \
                (evidence/"actor-readback.jsonl").open("x", encoding="utf-8", buffering=1) as readbacks, \
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as link:
            link.bind(("127.0.0.1", 0))
            link.setblocking(False)
            child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            result["wsl_launcher_pid"] = child.pid
            pending, heights, tail, latest = {}, {}, None, None
            paused_at = None
            outage = None
            probes_sent = False
            rejected_max = 0
            last_sent = -1
            final_seen_at = None
            while time.monotonic() - started < 160:
                now = time.monotonic()
                if tail is None:
                    lines = (evidence/"flight.log").read_text(encoding="utf-8", errors="replace").splitlines()
                    for line in lines:
                        if line.startswith('{"result_dir":'):
                            linux = json.loads(line)["result_dir"]
                            name = linux.rsplit("/", 1)[-1]
                            if not re.fullmatch(args.stack + r"-dds-[a-z0-9_]+", name):
                                raise ValueError("Unexpected flight evidence path")
                            flight_dir = REPO/"validation"/name
                            result["flight_result"] = str(flight_dir/"result.json")
                            tail = LatestTruth(flight_dir/"truth.jsonl")
                            print(json.dumps(dict(flight_result=result["flight_result"])), flush=True)
                            break
                record = tail.poll() if tail else None
                if record:
                    latest = record
                if latest and paused_at is None and -latest["vehicle"][8] >= 2.5 and result["acknowledged"] >= 30:
                    paused_at = now
                    outage = dict(start_wall_s=now-started, start_sim_s=latest["time"], start_height_m=-latest["vehicle"][8],
                                  paused_sequence=last_sent)
                    result["outage"] = outage
                    print("Visual packets paused for 3 wall seconds; physics/control remain active", flush=True)
                paused = paused_at is not None and now - paused_at < 3
                if outage and "end_wall_s" not in outage and not paused:
                    outage.update(end_wall_s=now-started, end_sim_s=latest["time"],
                                  sim_progress_s=latest["time"]-outage["start_sim_s"])
                    print("Visual packets resumed at latest live state", flush=True)
                if latest and latest["frame"] > last_sent and not paused:
                    packet = packet_from_truth(latest, args.run_id, args.stack)
                    link.sendto(json.dumps(packet, allow_nan=False).encode(), ("127.0.0.1", args.port))
                    pending[packet["sequence"]] = (packet, now)
                    heights[packet["sequence"]] = -packet["position_ned_m"][2]
                    last_sent = packet["sequence"]
                    result["sent"] += 1
                while True:
                    try:
                        raw, sender = link.recvfrom(4096)
                    except BlockingIOError:
                        break
                    if sender != ("127.0.0.1", args.port):
                        raise ValueError("Foreign Actor readback")
                    ack = json.loads(raw)
                    if ack.get("sequence") not in pending:
                        raise ValueError("Unrequested or duplicate Actor state change")
                    packet, sent_at = pending.pop(ack["sequence"])
                    errors = actor_errors(packet, ack)
                    readbacks.write(json.dumps(dict(wall_s=now-started, packet=packet, ack=ack,
                                                   errors=errors, ack_latency_wall_s=now-sent_at)) + "\n")
                    for key, value in errors.items():
                        result["max_error"][key] = max(result["max_error"][key], value)
                        if value > result["thresholds"][key]:
                            raise ValueError(f"Actor {key} exceeds declared tolerance: {value}")
                    rejected_max = max(rejected_max, ack["rejected"])
                    result["acknowledged"] += 1
                    if not probes_sent:
                        probes = invalid_probes(packet)
                        for probe in probes:
                            link.sendto(probe, ("127.0.0.1", args.port))
                        probes_sent = True
                        result["rejection_probes"] = len(probes)
                if child.poll() is not None:
                    if final_seen_at is None:
                        final_seen_at = now
                    # Leave time for final live frame then stale HUD capture.
                    if now - final_seen_at > 4:
                        break
                time.sleep(0.02)
            if child.poll() is None:
                raise TimeoutError("Live UE diagnostic watchdog expired")
            result["flight_launcher_exit"] = child.returncode
            flight = json.loads(Path(result["flight_result"]).read_text(encoding="utf-8"))
            result["flight_result_sha256"] = hashlib.sha256(Path(result["flight_result"]).read_bytes()).hexdigest()
            result["flight_status"] = flight["status"]
            result["outage"] = outage
            result["rejected"] = rejected_max
            result["unacknowledged"] = len(pending)
            ue_log = (evidence/"ue.log").read_text(encoding="utf-8", errors="replace")
            captures = []
            for line in ue_log.splitlines():
                match = re.search(r"WKSIM_CAPTURE .*?(frame-\d+\.png) sequence=(-?\d+) sim=([\d.]+) stale=(\d) rejected=(\d+)", line)
                if match:
                    path = evidence/"frames"/match[1]
                    if path.is_file() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n":
                        captures.append(dict(file=str(path), sequence=int(match[2]), sim_time_s=float(match[3]),
                                             height_m=heights.get(int(match[2])),
                                             stale=bool(int(match[4])), rejected=int(match[5]),
                                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            result["captures"] = captures
            result["live_captures"] = sum(not c["stale"] and c["sequence"] >= 0 for c in captures)
            result["stale_with_state_captures"] = sum(c["stale"] and c["sequence"] >= 0 for c in captures)
            result["checks"] = dict(flight_passed=flight["status"] == "pass" and child.returncode == 0,
                                    sufficient_readbacks=result["acknowledged"] >= 30,
                                    invalid_packets_rejected=rejected_max == result.get("rejection_probes"),
                                    live_frame=result["live_captures"] >= 1,
                                    airborne_live_frame=any(not c["stale"] and (c["height_m"] or 0) > .5 for c in captures),
                                    stale_frame=result["stale_with_state_captures"] >= 1,
                                    stale_frame_during_outage=bool(outage and any(c["stale"] and c["sequence"] == outage["paused_sequence"] for c in captures)),
                                    live_frame_after_outage=bool(outage and any(not c["stale"] and c["sequence"] > outage["paused_sequence"] for c in captures)),
                                    physics_progress_during_visual_loss=bool(outage and outage.get("sim_progress_s", 0) >= 1))
            result["status"] = "pass" if all(result["checks"].values()) else "failed"
    except Exception as error:
        result["error"] = str(error)
    finally:
        # A normal flight validator has its own 150 s watchdog and scoped child
        # cleanup. Let it finish that cleanup if this view-only diagnostic fails.
        if child and child.poll() is None:
            print("Viewer gate stopped; allowing the bounded SITL validator to clean up its children", flush=True)
            try:
                child.wait(timeout=max(1, 170 - (time.monotonic()-started)))
            except subprocess.TimeoutExpired:
                result["cleanup_warning"] = "WSL validator exceeded its cleanup budget; launcher left untouched"
        result["wall_s"] = time.monotonic()-started
        (evidence/"result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k:v for k,v in result.items() if k not in ("captures", "source_sha256")}, indent=2), flush=True)
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
