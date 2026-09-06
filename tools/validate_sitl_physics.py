"""Bounded, loopback-only PX4/ArduCopter independent-model flight diagnostic in WSL.

Runs a real FC: normal prearm checks, takeoff, hold, waypoint, and LAND. This is a
physics integration gate; --dds-workspace additionally uses native ROS2 commands
and observes DDS state. Neither mode is Prometheus/UE/full CopterSim acceptance.
Only child processes created by this run are terminated; no global taskkill.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from Simulator.wksim_core.model import build_model  # noqa: E402
from pymavlink import mavutil  # noqa: E402

AP_ROOT = Path("/root/wksim-dependencies/ardupilot-1511f271")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", choices=("arducopter", "px4"), default="arducopter")
    parser.add_argument("--ap-root", type=Path, default=AP_ROOT)
    parser.add_argument("--px4-root", type=Path, default=Path("/root/wksim-dependencies/px4-d6f12ad1"))
    parser.add_argument("--physics-port", type=int)
    parser.add_argument("--telemetry-port", type=int)
    parser.add_argument("--dds-workspace", type=Path)
    parser.add_argument("--ap-dds-candidate", type=Path, help="Isolated /root/wksim-ap-dds-yaw-* source/build workspace")
    parser.add_argument("--ap-build-manifest", help="Explicit clock/stop candidate manifest; does not change production pins")
    parser.add_argument("--ap-build-sha256")
    parser.add_argument("--prometheus-workspace", type=Path, help="Installed ROS2 Prometheus node; commands only through its public interface")
    parser.add_argument("--control-protocol", choices=('legacy_v1', 'session_v1'), default='legacy_v1')
    parser.add_argument("--yaw-gate", action="store_true", help="ArduCopter native DDS position+yaw validation; default flight gate is unchanged")
    parser.add_argument("--ready-barrier", type=Path, help="Private coordinator directory for the dual-DDS gate")
    args = parser.parse_args()
    is_ap = args.stack == "arducopter"
    experimental_admission = None
    if args.ap_build_manifest or args.ap_build_sha256:
        if (not is_ap or not args.dds_workspace or not args.prometheus_workspace
                or args.control_protocol != 'session_v1' or args.ap_dds_candidate):
            parser.error('Experimental build requires AP session_v1 public Prometheus regression, without --ap-dds-candidate')
        from ap_clock_candidate import admit
        from Simulator.wksim_runtime.config import load_config
        config = load_config(REPO / 'Simulator/wksim_runtime/examples/arducopter-session.json')
        config.update(dds_workspace=str(args.dds_workspace), prometheus_workspace=str(args.prometheus_workspace),
                      px4_root=str(args.px4_root), model_library='/tmp/wksim-model-5swsjm5f/libwksim_model.so')
        config, experimental_admission = admit(config, args.ap_build_manifest, args.ap_build_sha256)
        if not experimental_admission['ok']:
            parser.error('Experimental AP admission rejected: ' + repr(experimental_admission['reasons']))
        args.ap_dds_candidate = Path(config['ap_candidate'])
    if args.dds_workspace:
        if os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net"):
            parser.error("Run DDS validation through run-dds-validation.sh in a private network namespace")
        if os.environ.get("ROS_DOMAIN_ID") != "77":
            parser.error("DDS validation requires private domain 77")
        if is_ap:
            args.ap_root = args.dds_workspace / "src/ardupilot"
    if args.ap_dds_candidate:
        args.ap_dds_candidate = args.ap_dds_candidate.resolve(strict=True)
        if (not is_ap or not args.dds_workspace or args.ap_dds_candidate.parent != Path("/root")
                or (not experimental_admission and not args.ap_dds_candidate.name.startswith("wksim-ap-dds-yaw-"))):
            parser.error("Candidate firmware requires ArduCopter DDS and an isolated /root/wksim-ap-dds-yaw-* workspace")
        args.ap_root = args.ap_dds_candidate / "src"
    if args.yaw_gate and (not is_ap or not args.dds_workspace or args.ready_barrier):
        parser.error("Yaw gate requires a single ArduCopter DDS mission")
    if args.prometheus_workspace and (not args.dds_workspace or args.yaw_gate or args.ready_barrier):
        parser.error("Product-node gate requires single-stack DDS; use its dedicated launcher")
    source_root = args.ap_root if is_ap else args.px4_root
    executable = source_root / ("build/sitl/bin/arducopter" if is_ap else "build/px4_sitl_default/bin/px4")
    if is_ap and args.dds_workspace:
        executable = args.dds_workspace / "ap-dds-build/sitl/bin/arducopter"
    if args.ap_dds_candidate:
        executable = args.ap_dds_candidate / "build/sitl/bin/arducopter"
    args.physics_port = args.physics_port or (19002 if is_ap else 4581)
    args.telemetry_port = args.telemetry_port or (14660 if is_ap else 14661)
    system_id = 241 if is_ap else 22
    if sys.platform != "linux" or not executable.is_file():
        parser.error("Requires the selected existing SITL build in Ubuntu-22.04")
    # Bind checks reject occupied ports. The actual sockets are created immediately below.
    ports = [(socket.SOCK_DGRAM, args.telemetry_port)]
    if args.dds_workspace:
        ports.append((socket.SOCK_DGRAM, 12019 if is_ap else 18888))
    ports += [(socket.SOCK_DGRAM, p) for p in (args.physics_port, 19003, 19004)] if is_ap else [(socket.SOCK_STREAM, args.physics_port), (socket.SOCK_DGRAM, 18591)]
    if not is_ap and args.physics_port != 4581:
        parser.error("PX4 instance 21's startup script requires physics TCP port 4581")
    for kind, port in ports:
        with socket.socket(socket.AF_INET, kind) as probe:
            probe.bind(("127.0.0.1", port))
    result_dir = Path(tempfile.mkdtemp(prefix=f"{args.stack}-{'dds' if args.dds_workspace else 'physics'}-", dir=REPO / "validation"))
    run_dir = Path(tempfile.mkdtemp(prefix=f"wksim-{args.stack}-"))
    result = {"status": "failed", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "scope": "One quad-X physical FC loop; MAVLink test commands; no DDS/Prometheus/UE/full-product acceptance",
              "result_dir": str(result_dir), "run_dir": str(run_dir), "events": [],
              "thresholds": {"target_height_m": 3.0, "takeoff_min_height_m": 2.5,
                             "hold_seconds_sim": 5.0, "hold_height_error_m": 0.6,
                             "hold_max_tilt_rad": 0.35, "land_height_abs_m": 0.3,
                             "waypoint_ned_m": [3.0, 2.0, -3.0], "waypoint_position_error_m": 0.5,
                             "waypoint_max_speed_m_s": 0.5, "waypoint_hold_seconds_sim": 2.0},
              "stack": args.stack, "fc_binary": str(executable), "fc_binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}
    if experimental_admission:
        result['experimental_admission'] = experimental_admission
        result['ap_build_manifest_sha256'] = args.ap_build_sha256
        (result_dir / 'ap-build-manifest.json').write_bytes(Path(args.ap_build_manifest).read_bytes())
    if args.dds_workspace:
        result["scope"] = "Native DDS flight commands and state + independent-model physics; MAVLink heartbeat/telemetry requests only; no Prometheus/UE/full-product acceptance"
        result["network_namespace"] = os.readlink("/proc/self/ns/net")
        result["dds_workspace"] = str(args.dds_workspace)
        result["thresholds"]["dds_state_stale_wall_seconds"] = 2.0
    if args.yaw_gate:
        result["scope"] += "; position+yaw diagnostic, not a product adapter or universal upstream capability"
        result["thresholds"].update(yaw_targets_enu_rad=[0.0, -math.pi / 2, math.pi / 3],
                                     yaw_error_rad=0.15, yaw_dwell_seconds_sim=2.0,
                                     yaw_convergence_rate_rad_s=0.15,
                                     yaw_convergence_wall_seconds=15.0,
                                     yaw_position_error_m=0.5, yaw_truth_min_dwell_samples=50)
        result["yaw_checks"] = []
    if args.ap_dds_candidate:
        result["ap_dds_candidate"] = str(args.ap_dds_candidate)
        result["candidate_diff_sha256"] = hashlib.sha256(subprocess.check_output(
            ["git", "-C", str(source_root), "diff", "--no-ext-diff", "--binary"])).hexdigest()
        changed = subprocess.check_output(["git", "-C", str(source_root), "diff", "--name-only"], text=True).splitlines()
        changed += subprocess.check_output(["git", "-C", str(source_root), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
        result["candidate_source_sha256"] = {path: hashlib.sha256((source_root/path).read_bytes()).hexdigest() for path in sorted(set(changed))}
    sources = [Path(__file__), REPO / "Simulator/wksim_core/model.py",
               REPO / "Simulator/wksim_core" / ("ap_json.py" if is_ap else "px4_mavlink.py"),
               REPO / "Simulator/wksim_core" / ("arducopter-quad-x.parm" if is_ap else "px4-rc.mavlink")]
    if args.dds_workspace:
        sources += [REPO / "tools/sitl_dds.py", REPO / "tools/run-dds-validation.sh", REPO / "tools/validate_dds_schemas.py"]
    if args.prometheus_workspace:
        sources += [REPO / "tools/prometheus_mission.py", REPO / "tools/run-prometheus-validation.sh"]
    if experimental_admission:
        sources += [REPO / 'tools/ap_clock_candidate.py']
    result["implementation_sha256"] = {str(path.relative_to(REPO)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    result['source_snapshots'] = {str(path.relative_to(REPO)): 'source__' + str(path.relative_to(REPO)).replace('/', '__') + '.txt'
                                  for path in sources}
    for source, snapshot in result['source_snapshots'].items():
        (result_dir / snapshot).write_bytes((REPO / source).read_bytes())
    print(json.dumps({"result_dir": str(result_dir)}), flush=True)
    children, logfiles = [], []
    expected_exits = set()
    link, dds = None, None
    mission = None
    dds_ready = False
    latest, statuses = {}, []
    started = time.monotonic()
    telemetry = None

    def interrupted(signum, frame):
        raise RuntimeError(f"Validation interrupted by signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        library = build_model()
        result["model_build"] = json.loads(library.with_name("build.json").read_text())
        result["fc_commit"] = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
        link = mavutil.mavlink_connection(f"udpin:127.0.0.1:{args.telemetry_port}", source_system=245)
        telemetry = (result_dir / "telemetry.jsonl").open("x", encoding="utf-8", buffering=1)

        def launch(argv, name, cwd, env=None):
            log = (result_dir / f"{name}.log").open("x", encoding="utf-8")
            logfiles.append(log)
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            children.append(child)
            from probe_joint_clock import json_identity
            result[name] = {"argv": argv, "pid": child.pid, 'identity': json_identity(child.pid)}
            return child

        if args.dds_workspace:
            from sitl_dds import NativeDDS
            from validate_dds_schemas import check
            result["px4_dds_schemas"] = check(args.px4_root, args.dds_workspace / "src/px4_msgs")
            if result["px4_dds_schemas"]["status"] != "pass":
                raise RuntimeError("PX4 DDS source schemas do not match the ROS package")
            agent = args.dds_workspace / ("ros-install/micro_ros_agent/lib/micro_ros_agent/micro_ros_agent" if is_ap else "agent-install/bin/MicroXRCEAgent")
            result["agent_sha256"] = hashlib.sha256(agent.read_bytes()).hexdigest()
            agent_argv = [str(agent), "udp4", "-p", "12019" if is_ap else "18888", "-v", "4"]
            agent_process = launch(agent_argv, "agent", run_dir)
            dds = NativeDDS(args.stack, result_dir, state_extension=bool(args.prometheus_workspace and is_ap))
            if args.prometheus_workspace:
                from prometheus_mission import PrometheusMission
                mission = PrometheusMission(dds.node, result_dir, args.prometheus_workspace, args.control_protocol)
                result["scope"] = "Prometheus public setup/command mission via installed native DDS control node; independent-model physics and native/MAVLink state observers; no UE/joint-scene/full-product acceptance"
                result["prometheus_workspace"] = str(args.prometheus_workspace)
                launch([sys.executable, "-m", "prometheus_control.node", "--ros-args",
                    "-p", f"flight_stack:={args.stack}", "-p", "uav_id:=1",
                    "-p", "native_prefix:=" + ("/ap" if is_ap else "/wksim_px4_21"),
                    "-p", "native_system_id:=22", "-p", "arducopter_position_yaw:=true",
                    "-p", "run_id:=" + result_dir.name], "prometheus-node", run_dir)

        launch([sys.executable, "-m", "Simulator.wksim_core." + ("ap_json" if is_ap else "px4_mavlink"), "--library", str(library),
                "--port", str(args.physics_port), "--trace", str(result_dir / "truth.jsonl"),
                "--duration", "180"], "physics", REPO)
        if is_ap:
            defaults = f"{args.ap_root}/Tools/autotest/default_params/copter.parm,{REPO}/Simulator/wksim_core/arducopter-quad-x.parm"
            if dds:
                dds_parameters = run_dir / "dds.parm"
                dds_parameters.write_text("DDS_ENABLE 1\nDDS_UDP_PORT 12019\nDDS_DOMAIN_ID 77\n", encoding="utf-8")
                defaults += f",{dds_parameters}"
                result["dds_parameters"] = dds_parameters.read_text()
            launch([str(executable), "--model", "JSON:127.0.0.1", "--rate", "1000", "--speedup", "3",
                "--base-port", "16600", "--instance", "11", "--sysid", "241",
                "--sim-address", "127.0.0.1", "--sim-port-out", str(args.physics_port),
                "--sim-port-in", "19003", "--rc-in-port", "19004",
                "--serial0", f"udpclient:127.0.0.1:{args.telemetry_port}",
                "--serial1", "none", "--serial2", "none", "--defaults", defaults,
                    "--home", "40.1540302,116.2593683,50,0"], "arducopter", run_dir)
        else:
            overrides = {"PX4_SYS_AUTOSTART": "10016", "PX4_SIM_MODEL": "none_iris",
                         "PX4_SIM_HOST_ADDR": "127.0.0.1", "PX4_SIM_SPEED_FACTOR": "3",
                         "PX4_UXRCE_DDS_PORT": "18888", "PX4_UXRCE_DDS_NS": "wksim_px4_21", "ROS_DOMAIN_ID": "77",
                         "WKSIM_MAVLINK_LOCAL_PORT": "18591", "WKSIM_MAVLINK_REMOTE_PORT": str(args.telemetry_port),
                         "PX4_PARAM_SIM_GZ_EN": "0", "PX4_PARAM_SIM_BAT_ENABLE": "1"}
            if dds:
                overrides["PX4_PARAM_UXRCE_DDS_SYNCT"] = "0"
                result["dds_clock_policy"] = "PX4 simulation microseconds from fresh native state; Agent wall-clock synchronization disabled for accelerated SITL"
            arm = 0.225 / math.sqrt(2)
            for rotor, (x, y) in enumerate(((arm, arm), (-arm, -arm), (arm, -arm), (-arm, arm))):
                overrides[f"PX4_PARAM_CA_ROTOR{rotor}_PX"] = str(x)
                overrides[f"PX4_PARAM_CA_ROTOR{rotor}_PY"] = str(y)
                overrides[f"PX4_PARAM_CA_ROTOR{rotor}_KM"] = str((1 if rotor < 2 else -1) * 2.783e-7 / 1.681e-5)
            environment = dict(os.environ, **overrides)
            environment["PATH"] = str(REPO / "Simulator/wksim_core") + os.pathsep + environment["PATH"]
            result["environment_overrides"] = overrides
            launch([str(executable), "-d", str(args.px4_root / "build/px4_sitl_default/etc"),
                    "-i", "21", "-w", str(run_dir)], "px4", run_dir, environment)
        last_heartbeat = 0.0
        last_setpoint_ms = -1000
        setpoint_ned = None

        def pump():
            nonlocal last_heartbeat, last_setpoint_ms
            now = time.monotonic()
            if now - started > 150:
                raise TimeoutError("Overall 150 second wall-clock watchdog")
            for child in children:
                if child.poll() is not None and child.pid not in expected_exits:
                    raise RuntimeError(f"Child {child.pid} exited with {child.returncode}; inspect logs")
            if dds:
                dds.pump()
                if mission:
                    mission.check_failure()
                if dds_ready:
                    dds.assert_fresh()
            if now - last_heartbeat >= 1:
                link.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                last_heartbeat = now
            message = link.recv_match(blocking=True, timeout=0.05)
            if message is None or message.get_srcSystem() != system_id:
                return
            kind = message.get_type()
            if kind == "BAD_DATA":
                return
            latest[kind] = message
            if not dds and setpoint_ned is not None and kind == "LOCAL_POSITION_NED" and message.time_boot_ms - last_setpoint_ms >= 100:
                link.mav.set_position_target_local_ned_send(message.time_boot_ms, system_id, 1,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED, 0xDF8, *setpoint_ned, 0, 0, 0, 0, 0, 0, 0, 0)
                last_setpoint_ms = message.time_boot_ms
            if kind in ("HEARTBEAT", "LOCAL_POSITION_NED", "GLOBAL_POSITION_INT", "ATTITUDE", "COMMAND_ACK",
                        "STATUSTEXT", "GPS_RAW_INT", "HOME_POSITION", "EKF_STATUS_REPORT", "SERVO_OUTPUT_RAW",
                        "SYS_STATUS", "EXTENDED_SYS_STATE", "ESTIMATOR_STATUS"):
                telemetry.write(json.dumps({"wall": now - started, **message.to_dict()}) + "\n")
            if kind == "STATUSTEXT":
                statuses.append(message.text)
                print(message.text, flush=True)

        def wait_for(label, predicate, timeout=20):
            end = time.monotonic() + timeout
            while not predicate():
                if time.monotonic() > end:
                    raise TimeoutError(f"{label}; recent FC status: {statuses[-8:]}")
                pump()
            result["events"].append({"event": label, "wall": time.monotonic() - started,
                                      "local_position": latest["LOCAL_POSITION_NED"].to_dict() if "LOCAL_POSITION_NED" in latest else None})
            if dds and dds_ready:
                result["events"][-1]["dds"] = dds.snapshot()
            print(label, flush=True)

        def command(command_id, parameters):
            if mission:
                if command_id == 400:
                    mission.setup(cmd=UAVSetup.ARMING, arming=bool(parameters[0]))
                elif command_id == 21:
                    mission.land()
                else:
                    raise ValueError("Unsupported test mapping: all product input must use public Prometheus messages")
                wait_for(f"Prometheus response {command_id}", mission.done, 10)
                return
            if dds:
                dds.command(command_id, parameters)
                wait_for(f"DDS ACK {command_id}", dds.command_done, 5)
                dds.check_command()
                return
            latest.pop("COMMAND_ACK", None)
            link.mav.command_long_send(system_id, 1, command_id, 0, *parameters)
            wait_for(f"ACK {command_id}", lambda: "COMMAND_ACK" in latest and latest["COMMAND_ACK"].command == command_id, 5)
            ack = latest["COMMAND_ACK"]
            if ack.result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
                raise RuntimeError(f"Command rejected: {ack.to_dict()}, statuses={statuses[-8:]}")

        wait_for("heartbeat", lambda: "HEARTBEAT" in latest, 20)
        for message_id in (32, 30, 33, 24, 193, 36, 242):
            link.mav.command_long_send(system_id, 1, 511, 0, message_id, 100000, 0, 0, 0, 0, 0)
        wait_for("GPS and EKF position ready", lambda:
                 "LOCAL_POSITION_NED" in latest and "GPS_RAW_INT" in latest and latest["GPS_RAW_INT"].fix_type >= 3 and
                 (("EKF_STATUS_REPORT" in latest and latest["EKF_STATUS_REPORT"].flags & 16) if is_ap else
                  ("SYS_STATUS" in latest and latest["SYS_STATUS"].onboard_control_sensors_health & mavutil.mavlink.MAV_SYS_STATUS_PREARM_CHECK)), 40)
        if dds:
            wait_for("native DDS state, publishers and services ready", dds.ready, 20)
            dds_ready = True
            if args.ready_barrier:
                with (args.ready_barrier / f"{args.stack}.ready").open("x", encoding="utf-8") as marker:
                    json.dump({"result_dir": str(result_dir), "pid": os.getpid()}, marker)
                wait_for("both native DDS stacks ready", lambda: (args.ready_barrier / "go").is_file(), 45)
        if mission:
            from prometheus_msgs.msg import UAVSetup
            wait_for("Prometheus state and input ready", mission.ready, 20)
            mission.setup(cmd=UAVSetup.SET_PX4_MODE, px4_mode="AUTO.LOITER")
            wait_for("Prometheus autonomous hold mode completed", mission.done, 10)
        elif is_ap:
            if dds:
                command(176, [1, 4, 0, 0, 0, 0, 0])
            else:
                link.mav.set_mode_send(system_id, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 4)
            wait_for("GUIDED confirmed", lambda: latest["HEARTBEAT"].custom_mode == 4 and (not dds or dds.mode_confirmed(4)))
        else:
            setpoint_ned = [0, 0, -3]
            if dds:
                dds.setpoint = setpoint_ned
            stream_start = latest["LOCAL_POSITION_NED"].time_boot_ms
            wait_for("OFFBOARD setpoint warmup", lambda: latest["LOCAL_POSITION_NED"].time_boot_ms - stream_start >= 2000)
            command(176, [1, 6, 0, 0, 0, 0, 0])
            wait_for("OFFBOARD confirmed", lambda: (latest["HEARTBEAT"].custom_mode >> 16) & 255 == 6 and (not dds or dds.mode_confirmed(6)))
        command(400, [1, 0, 0, 0, 0, 0, 0])  # Normal arm. No force-arm magic; prearm checks remain on.
        wait_for("armed confirmed", lambda: latest["HEARTBEAT"].base_mode & 128 and (not dds or dds.armed))
        if mission:
            mission.setup(cmd=UAVSetup.SET_CONTROL_MODE, control_state="COMMAND_CONTROL")
            wait_for("Prometheus COMMAND_CONTROL completed", mission.done, 30)
        elif is_ap:
            command(22, [0, 0, 0, 0, 0, 0, 3])
        wait_for("takeoff height reached", lambda: latest["LOCAL_POSITION_NED"].z <= -2.5 and (not dds or dds.position_ned[2] <= -2.5), 25)
        hold_start = latest["LOCAL_POSITION_NED"].time_boot_ms
        hold_samples = []
        while latest["LOCAL_POSITION_NED"].time_boot_ms - hold_start < 5000:
            pump()
            pos, att = latest["LOCAL_POSITION_NED"], latest["ATTITUDE"]
            hold_samples.append({"time_ms": pos.time_boot_ms, "height": -pos.z, "roll": att.roll, "pitch": att.pitch})
        result["hold"] = {"samples": len(hold_samples),
                          "max_height_error_m": max(abs(s["height"] - 3) for s in hold_samples),
                          "max_tilt_rad": max(max(abs(s["roll"]), abs(s["pitch"])) for s in hold_samples)}
        if result["hold"]["max_height_error_m"] > 0.6 or result["hold"]["max_tilt_rad"] > 0.35:
            raise RuntimeError("Hold integration thresholds failed")
        if not is_ap:
            setpoint_ned = [3, 2, -3]
        if mission:
            mission.move()
            wait_for("Prometheus waypoint accepted", mission.done, 5)
        elif dds:
            dds.setpoint = [3, 2, -3]
        else:
            link.mav.set_position_target_local_ned_send(
                latest["LOCAL_POSITION_NED"].time_boot_ms, system_id, 1,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED, 0xDF8, 3, 2, -3, 0, 0, 0, 0, 0, 0, 0, 0)

        def waypoint_reached():
            pos = latest["LOCAL_POSITION_NED"]
            error = math.sqrt((pos.x - 3) ** 2 + (pos.y - 2) ** 2 + (pos.z + 3) ** 2)
            speed = math.sqrt(pos.vx ** 2 + pos.vy ** 2 + pos.vz ** 2)
            return error <= 0.5 and speed <= 0.5 and (not dds or math.dist(dds.position_ned, [3, 2, -3]) <= 0.5)

        wait_for("waypoint reached", waypoint_reached, 20)
        waypoint_start = latest["LOCAL_POSITION_NED"].time_boot_ms
        while latest["LOCAL_POSITION_NED"].time_boot_ms - waypoint_start < 2000:
            pump()
            if not waypoint_reached():
                raise RuntimeError("Waypoint dwell thresholds failed")
        result["events"].append({"event": "waypoint dwell passed", "local_position": latest["LOCAL_POSITION_NED"].to_dict()})
        if args.yaw_gate:
            from sitl_dds import angle_error, ned_yaw_to_enu
            # Follow the already-written model trace only at dwell boundaries.
            # Its own timestamp selects independent truth samples, not a guessed
            # equality between ROS, FC boot, wall and model clocks.
            with (result_dir / "truth.jsonl").open(encoding="utf-8") as yaw_trace:
                last_truth = None

                def model_time_now():
                    nonlocal last_truth
                    while True:
                        start = yaw_trace.tell()
                        line = yaw_trace.readline()
                        if not line.endswith("\n"):
                            yaw_trace.seek(start)
                            break
                        last_truth = json.loads(line)
                    if last_truth is None:
                        raise RuntimeError("Missing model trace during yaw gate")
                    return last_truth["time"]

                def yaw_errors(target):
                    return {"dds_error_rad": angle_error(dds.yaw_enu, target),
                            "mavlink_error_rad": angle_error(ned_yaw_to_enu(latest["ATTITUDE"].yaw), target),
                            "dds_position_error_m": math.dist(dds.position_ned, [3, 2, -3])}

                for target in result["thresholds"]["yaw_targets_enu_rad"]:
                    dds.target_yaw_enu = target
                    wait_for(f"yaw ENU {target:.6f} reached", lambda:
                             waypoint_reached() and max(yaw_errors(target)[key] for key in
                             ("dds_error_rad", "mavlink_error_rad")) <= 0.15
                             and abs(latest["ATTITUDE"].yawspeed) <= 0.15
                             and abs(dds.latest["velocity"].twist.angular.z) <= 0.15, 15)
                    yaw_start = latest["LOCAL_POSITION_NED"].time_boot_ms
                    record = {"target_enu_rad": target, "model_start_s": model_time_now(),
                              "fc_start_ms": yaw_start, "max_dds_error_rad": 0.0,
                              "max_mavlink_error_rad": 0.0, "max_dds_position_error_m": 0.0}
                    result["yaw_checks"].append(record)
                    while (latest["LOCAL_POSITION_NED"].time_boot_ms - yaw_start < 2000
                           or model_time_now() - record["model_start_s"] < 2.0):
                        pump()
                        errors = yaw_errors(target)
                        if (not waypoint_reached() or errors["dds_error_rad"] > 0.15
                                or errors["mavlink_error_rad"] > 0.15):
                            raise RuntimeError(f"Yaw dwell thresholds failed: {errors}")
                        for key, value in errors.items():
                            record[f"max_{key}"] = max(record[f"max_{key}"], value)
                    record.update(model_end_s=model_time_now(),
                                  fc_end_ms=latest["LOCAL_POSITION_NED"].time_boot_ms, status="pass")
        command(21, [0, 0, 0, 0, 0, 0, 0])
        setpoint_ned = None
        if dds:
            dds.setpoint = None
        wait_for("landed and disarmed", lambda: not (latest["HEARTBEAT"].base_mode & 128) and abs(latest["LOCAL_POSITION_NED"].z) < 0.3
                 and (not dds or (not dds.armed and abs(dds.position_ned[2]) < 0.3)), 30)
        if dds:
            # Transport recovery is deliberately tested on the ground. This does
            # not stand in for an in-flight failsafe matrix or UE loss testing.
            dds_ready = False
            expected_exits.add(agent_process.pid)
            agent_process.terminate()
            agent_process.wait(timeout=5)
            before_ms = latest["LOCAL_POSITION_NED"].time_boot_ms
            outage_start = time.monotonic()
            wait_for("Agent offline 3 wall seconds", lambda: time.monotonic() - outage_start >= 3, 5)
            stale_detected = False
            try:
                dds.assert_fresh()
            except RuntimeError:
                stale_detected = True
            progressed_ms = latest["LOCAL_POSITION_NED"].time_boot_ms - before_ms
            if not stale_detected or progressed_ms < 1000:
                raise RuntimeError("DDS loss was not detected or physics/FC stalled without Agent")
            resumed_at = time.monotonic()
            agent_process = launch(agent_argv, "agent-restarted", run_dir)
            wait_for("native DDS reconnected with fresh state", lambda:
                     dds.received_at.get("position", 0) > resumed_at and dds.received_at.get("status", 0) > resumed_at
                     and dds.ready(), 25)
            dds_ready = True
            if mission:
                wait_for("Prometheus fresh state recovered", mission.ready, 10)
                mission.setup(cmd=UAVSetup.SET_PX4_MODE, px4_mode="AUTO.LOITER")
                wait_for("Prometheus post-reconnect mode completed", mission.done, 10)
            else:
                command(176, [1, 4 if is_ap else 3, 0, 0, 0, 0, 0])
                wait_for("post-reconnect mode confirmed", lambda: dds.mode_confirmed(4 if is_ap else 3), 5)
            if dds.armed:
                raise RuntimeError("Unexpected re-arming during ground reconnect diagnostic")
            result["dds_reconnect"] = {"status": "pass", "scope": "disarmed ground transport recovery only",
                                       "stale_detected": stale_detected, "fc_progress_during_outage_ms": progressed_ms,
                                       "recovery_wall_seconds": time.monotonic() - resumed_at}
        result["status"] = "pass"
    except Exception as error:
        result["error"] = str(error)
        print(f"FAILED: {error}", flush=True)
    finally:
        if mission:
            result["prometheus"] = mission.report()
            mission.log.close()
        if dds:
            try:
                result["dds"] = dds.report()
                dds.close()
            except Exception as error:
                result["status"], result["dds_cleanup_error"] = "failed", str(error)
        for child in reversed(children):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        for log in logfiles:
            log.close()
        if telemetry:
            telemetry.close()
        if link:
            link.close()
        result["wall_seconds"] = time.monotonic() - started
        result["children_reaped"] = all(child.poll() is not None for child in children)
        from probe_joint_clock import group_members
        result['child_exits'] = {str(child.pid): dict(returncode=child.returncode, remaining_group_members=group_members(child.pid))
                                 for child in children}
        if any(value['remaining_group_members'] for value in result['child_exits'].values()):
            result['status'], result['error'] = 'failed', 'Owned flight process group remains'
        if experimental_admission and 'arducopter' in result:
            if result['child_exits'][str(result['arducopter']['pid'])]['returncode'] != 0:
                result['status'], result['error'] = 'failed', 'Experimental AP did not exit normally'
        result["statuses"] = statuses
        truth_file = result_dir / "truth.jsonl"
        if truth_file.exists():
            records = [json.loads(line) for line in truth_file.read_text().splitlines()]
            if records:
                result["truth"] = {"records": len(records), "seconds": records[-1]["time"],
                                   "max_height_m": max(-s["vehicle"][8] for s in records),
                                   "final_height_m": -records[-1]["vehicle"][8],
                                   "final_position_ned_m": records[-1]["vehicle"][6:9],
                                   "min_waypoint_error_m": min(math.sqrt(sum((a - b) ** 2 for a, b in zip(s["vehicle"][6:9], [3, 2, -3]))) for s in records),
                                   "max_motor_rpm": max(max(s["vehicle"][16:20]) for s in records)}
                if result["status"] == "pass" and (result["truth"]["max_height_m"] < 2.5 or abs(result["truth"]["final_height_m"]) > 0.3 or result["truth"]["min_waypoint_error_m"] > 0.5):
                    result["status"], result["error"] = "failed", "Physical truth disagrees with takeoff/waypoint/landing"
                for record in result.get("yaw_checks", []):
                    if "model_end_s" not in record:
                        continue
                    dwell = [s for s in records if record["model_start_s"] <= s["time"] <= record["model_end_s"]]
                    record["truth_samples"] = len(dwell)
                    record["max_truth_error_rad"] = max((angle_error(ned_yaw_to_enu(s["vehicle"][11]), record["target_enu_rad"])
                                                         for s in dwell), default=math.inf)
                    record["max_truth_position_error_m"] = max((math.dist(s["vehicle"][6:9], [3, 2, -3])
                                                                for s in dwell), default=math.inf)
                    if (len(dwell) < 50 or record["model_end_s"] - record["model_start_s"] < 2.0
                            or record["max_truth_error_rad"] > 0.15 or record["max_truth_position_error_m"] > 0.5):
                        record["status"] = "failed"
                        result["status"], result["error"] = "failed", "Physical truth disagrees with yaw dwell thresholds"
        if result["status"] == "pass" and "truth" not in result:
            result["status"], result["error"] = "failed", "Missing physical truth evidence"
        if result["status"] == "pass" and dds:
            report = result["dds"]
            if (report["max_height_m"] < 2.5 or report["min_waypoint_error_m"] > 0.5
                    or abs(report["final"]["position_ned"][2]) > 0.3 or report["final"]["armed"]
                    or report["failsafe_observed_while_armed"]):
                result["status"], result["error"] = "failed", "Native DDS state disagrees with the flight gate"
        (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k in ("status", "error", "truth", "hold", "result_dir", "children_reaped")}, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
