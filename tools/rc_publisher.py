"""Software RC publisher for #99 RC_POS_CONTROL verifications.

Publishes strict `wksim.rc-input` frames (the schema enforced by
Simulator/wksim_control/rc_input.py) to the control node's RC topic and
records every published frame raw. Profile-driven; neutral first frame so
the node can bind a candidate. No flight controller is contacted directly.
"""
import argparse
import json
import time

import rclpy
from std_msgs.msg import String

VERSION = 1
SOURCE = "wksim.rc-input"
MAX_SEQUENCE = 9007199254


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
    profile = json.loads(open(args.profile, "r", encoding="utf-8").read())
    assert isinstance(profile, list) and profile, "profile must be a non-empty segment list"
    neutral = [1500, 1500, 1500, 1500, 1000, 1500, 1000, 1000]
    for index, segment in enumerate(profile):
        channels = segment["channels_us"]
        assert isinstance(channels, list) and len(channels) == 8, index
        assert all(type(v) is int and 1000 <= v <= 2000 for v in channels), index
        assert segment["hold_s"] >= 0, index
    rclpy.init()
    node = rclpy.create_node("wksim_rc_publisher")
    pub = node.create_publisher(String, args.topic, 1)
    out = open(args.out, "w", encoding="utf-8", newline="\n")
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
                assert sequence <= MAX_SEQUENCE
                produced = time.monotonic_ns()
                channels = neutral if index == 0 else segment["channels_us"]
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
