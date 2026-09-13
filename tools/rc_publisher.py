"""Software RC publisher for #99 RC_POS_CONTROL verifications.

Publishes strict `wksim-software-rc-v1` frames (the schema enforced by
Simulator/wksim_control/rc_input.py) to the control node's RC topic and
records every published frame raw. Start a normal profile with a neutral segment
to offer a candidate. Probe profiles are published exactly as supplied.
"""
import argparse
import json
import hashlib
import math
import os
from pathlib import Path
import sys
import time

import rclpy
from std_msgs.msg import String

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_control.rc_input import VERSION, SOURCE, MAX_SEQUENCE


def frame(run_id, control_epoch, uav_id, boot_id, stream_id, sequence, produced_ns, channels):
    return {
        "version": VERSION,
        "source": SOURCE,
        "run_id": run_id,
        "control_epoch": control_epoch,
        "uav_id": uav_id,
        "boot_id": boot_id,
        "stream_id": stream_id,
        "sequence": sequence,
        "produced_monotonic_ns": produced_ns,
        "channels_us": list(channels),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--control-epoch", required=True)
    parser.add_argument("--uav-id", type=int, default=1)
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--stream-id", required=True)
    parser.add_argument("--topic", default="/uav1/prometheus/v2/rc_input")
    parser.add_argument("--profile", required=True, help="JSON: list of {hold_s, channels_us[8]} segments")
    parser.add_argument("--out", required=True)
    parser.add_argument("--ready-file", default=None)
    args = parser.parse_args()
    profile_bytes = Path(args.profile).read_bytes()
    profile = json.loads(profile_bytes)
    if not isinstance(profile, list) or not profile:
        raise ValueError('profile must be a non-empty segment list')
    for index, segment in enumerate(profile):
        channels = segment["channels_us"]
        if (not isinstance(channels, list) or len(channels) != 8
                or not all(type(v) is int and 1000 <= v <= 2000 for v in channels)
                or type(segment['hold_s']) not in (int, float)
                or not math.isfinite(segment['hold_s']) or segment['hold_s'] < 0):
            raise ValueError('invalid profile segment '+str(index))
    rclpy.init()
    node = rclpy.create_node("wksim_rc_publisher")
    pub = node.create_publisher(String, args.topic, 1)
    out = open(args.out, "x", encoding="utf-8", newline="\n")
    out.write(json.dumps(dict(kind='publisher_identity', argv=sys.argv, pid=os.getpid(),
        proc_stat=Path('/proc/self/stat').read_text(), actual_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        profile_sha256=hashlib.sha256(profile_bytes).hexdigest(), arguments=vars(args)))+'\n')
    sequence = 0
    started = time.monotonic()
    if args.ready_file:
        with open(args.ready_file, "w", encoding="utf-8") as handle:
            handle.write(str(node.get_clock().now().nanoseconds))
    try:
        for index, segment in enumerate(profile):
            deadline = time.monotonic() + segment["hold_s"]
            first = True
            while first or time.monotonic() < deadline:
                first = False
                sequence += 1
                if sequence > MAX_SEQUENCE:
                    raise ValueError('RC sequence exhausted')
                produced = time.monotonic_ns()
                channels = segment['channels_us']
                payload = frame(args.run_id, args.control_epoch, args.uav_id, args.boot_id,
                                args.stream_id, sequence, produced, channels)
                pub.publish(String(data=json.dumps(payload)))
                out.write(json.dumps({"segment": index, "published_monotonic_ns": produced,
                                      "frame": payload}, sort_keys=True) + "\n")
                out.flush()
                node.get_clock().sleep_for(rclpy.duration.Duration(seconds=0.02))
                rclpy.spin_once(node, timeout_sec=0.0)
    finally:
        out.close()
        node.destroy_node()
        rclpy.shutdown()
    print(json.dumps({"frames": sequence, "out": args.out}))


if __name__ == "__main__":
    main()
