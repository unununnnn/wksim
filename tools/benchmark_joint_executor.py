"""Isolated ROS executor microbenchmark: per-call rclpy.spin_once vs reused executor.

Compares the current Task.pump pattern — rclpy.spin_once(node, timeout_sec=0),
which the installed /opt/ros/humble rclpy implements as add_node + spin_once +
remove_node on every call (rclpy/__init__.py verified) — against one explicit
SingleThreadedExecutor with add_node once per batch and repeated
executor.spin_once(timeout_sec=0).

Executor-membership discipline (rclpy node.py executor setter + executors.py
add_node/remove_node verified): the global executor's add_node moves the node
OUT of any persistent executor via the node.executor setter. Therefore every
A batch starts with node.executor = None, every B batch starts with one
untimed executor.add_node(node) and asserts node.executor is the persistent
executor, and every batch ends with the node removed from that executor. The
two executors never own the node at the same time.

With-message class: one uniquely sequenced std_msgs/String per message; spin(0)
loops until that message's callback fires (per-message and global deadlines);
every spin records whether a callback ran. Both arms must receive the same N
messages. Processing cost is compared on callback=True samples only; empty
poll counts and per-message totals are reported separately so empty calls are
never mistaken for processing gain. CPU is time.thread_time_ns (this thread
only; DDS background threads excluded).

Probe-named node/topic only; no business or flight-control topic is touched.
Caller supplies the isolated namespace (unshare --net --ipc) and a fixed
ROS_DOMAIN_ID. All evidence, including failures with traceback, goes to a
fresh 'x'-mode file; pre-existing outputs are never modified.

Usage (inside the isolated namespace):
  ROS_DOMAIN_ID=77 python3 -B tools/benchmark_joint_executor.py --output <new.json>
"""
import argparse
import json
import hashlib
from pathlib import Path
import platform
import sys
import time
import os
import traceback

WALL_BUDGET_S = 25.0
PER_MESSAGE_DEADLINE_S = 2.0


def percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    return sorted_values[int(fraction * (len(sorted_values) - 1))]


def summarize(samples):
    ordered = sorted(samples)
    return {"count": len(samples),
            "median_ns": percentile(ordered, 0.50),
            "p95_ns": percentile(ordered, 0.95),
            "p99_ns": percentile(ordered, 0.99),
            "min_ns": ordered[0] if ordered else None,
            "max_ns": ordered[-1] if ordered else None}


def benchmark(output, empty_iterations, messages, repeats):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_msgs.msg import String

    started = time.monotonic()
    deadline = started + WALL_BUDGET_S
    result = {"schema": "wksim.joint-executor-benchmark.v2",
              "python": sys.version.split()[0], "platform": platform.platform(),
              "ros_distro": os.environ.get("ROS_DISTRO"),
              "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
              "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "empty_iterations": empty_iterations, "messages": messages, "repeats": repeats,
              "wall_budget_s": WALL_BUDGET_S, "truncated": False,
              "cpu_clock": "thread_time_ns (benchmark thread only)",
              "rclpy_spin_once_source": "add_node+spin_once+remove_node per call "
                                        "(installed /opt/ros/humble rclpy/__init__.py verified)",
              "arms": {}}
    try:
        xml = Path("/opt/ros/humble/share/rclpy/package.xml").read_text()
        result["rclpy_package_xml_version"] = xml.split("<version>")[1].split("</version>")[0]
    except (OSError, IndexError):
        result["rclpy_package_xml_version"] = None

    rclpy.init(args=[])
    node = None
    executor = None
    try:
        probe = f"wksim_executor_probe_{os.getpid()}"
        node = rclpy.create_node(probe)
        received = []
        subscription = node.create_subscription(String, f"/{probe}/probe",
                                                lambda msg: received.append(msg.data), 10)
        publisher = node.create_publisher(String, f"/{probe}/probe", 10)
        executor = SingleThreadedExecutor()

        # Warm the DDS entities so messages are delivered promptly.
        publisher.publish(String(data="warmup"))
        warmup_deadline = time.monotonic() + 5
        while not received and time.monotonic() < warmup_deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
        if not received:
            raise RuntimeError("probe topic never delivered its warmup message")
        received.clear()

        def timed(spin):
            wall = time.perf_counter_ns()
            cpu = time.thread_time_ns()
            spin()
            return {"wall_ns": time.perf_counter_ns() - wall,
                    "cpu_ns": time.thread_time_ns() - cpu}

        def batch_empty(arm):
            samples = []
            for _ in range(empty_iterations):
                if time.monotonic() > deadline:
                    result["truncated"] = True
                    break
                samples.append(timed(arm))
            return samples, 0, []

        def batch_messages(arm, class_name, arm_name):
            samples = []
            empty_polls = 0
            totals = []
            for index in range(messages):
                if time.monotonic() > deadline:
                    result["truncated"] = True
                    break
                marker = f"{class_name}-{arm_name}-{len(received)}-{index}"
                message_start = time.perf_counter_ns()
                publisher.publish(String(data=marker))
                before = len(received)
                message_deadline = time.monotonic() + PER_MESSAGE_DEADLINE_S
                while True:
                    sample = timed(arm)
                    sample["callback"] = len(received) > before
                    samples.append(sample)
                    if sample["callback"]:
                        totals.append(time.perf_counter_ns() - message_start)
                        break
                    empty_polls += 1
                    if time.monotonic() > message_deadline:
                        raise TimeoutError(f"probe message never consumed: {marker}")
                    if time.monotonic() > deadline:
                        result["truncated"] = True
                        return samples, empty_polls, totals
            return samples, empty_polls, totals

        def run_arm(class_name, arm_name, with_messages):
            """One ABBA arm batch with exclusive, asserted executor membership."""
            if arm_name == "rclpy_add_remove_per_call":
                # Global spin_once owns membership; start fully detached.
                node.executor = None
                spin = lambda: rclpy.spin_once(node, timeout_sec=0)
            else:
                executor.add_node(node)
                if node.executor is not executor or node not in executor.get_nodes():
                    raise RuntimeError("persistent executor does not own the probe node")
                spin = lambda: executor.spin_once(timeout_sec=0)
            try:
                if with_messages:
                    return batch_messages(spin, class_name, arm_name)
                return batch_empty(spin)
            finally:
                if arm_name == "rclpy_add_remove_per_call":
                    if node in executor.get_nodes():
                        raise RuntimeError("rclpy spin_once left the node in the persistent executor")
                    node.executor = None
                else:
                    executor.remove_node(node)
                    node.executor = None

        for class_name, with_messages in (("empty_queue", False), ("with_message", True)):
            order = (["rclpy_add_remove_per_call", "executor_add_node_once",
                      "executor_add_node_once", "rclpy_add_remove_per_call"] * repeats)
            for arm_name in order:
                if result["truncated"]:
                    break
                samples, empty_polls, totals = run_arm(class_name, arm_name, with_messages)
                consumed = sum(1 for s in samples if s.get("callback"))
                bucket = result["arms"].setdefault(class_name, {}).setdefault(
                    arm_name, {"batches": [], "callbacks": 0, "empty_polls": 0})
                bucket["batches"].append({"samples": samples, "message_totals_ns": totals})
                bucket["callbacks"] += consumed
                bucket["empty_polls"] += empty_polls
            if result["truncated"]:
                break
        for class_name, per_arm in result["arms"].items():
            for arm_name, bucket in per_arm.items():
                flat = [s for b in bucket["batches"] for s in b["samples"]]
                bucket["wall"] = summarize([s["wall_ns"] for s in flat])
                bucket["cpu"] = summarize([s["cpu_ns"] for s in flat])
                callback_wall = [s["wall_ns"] for s in flat if s.get("callback")]
                callback_cpu = [s["cpu_ns"] for s in flat if s.get("callback")]
                bucket["callback_wall"] = summarize(callback_wall)
                bucket["callback_cpu"] = summarize(callback_cpu)
                totals = [t for b in bucket["batches"] for t in b["message_totals_ns"]]
                bucket["message_total"] = summarize(totals)
                if class_name == "with_message":
                    expected = messages * (bucket["batches"] and len(bucket["batches"]) or 0)
                    if bucket["callbacks"] != len(totals) or (
                            not result["truncated"] and bucket["callbacks"] != expected):
                        raise RuntimeError(
                            f"callback accounting differs: {bucket['callbacks']} vs {len(totals)} totals, expected {expected}")
        result["wall_seconds"] = time.monotonic() - started
    except BaseException as error:
        result["error"] = repr(error)
        result["traceback"] = traceback.format_exc()
        result["wall_seconds"] = time.monotonic() - started
    finally:
        if executor is not None and node is not None:
            try:
                executor.remove_node(node)
            except Exception:
                pass
            try:
                executor.shutdown()
            except Exception:
                pass
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=1)
        stream.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--messages", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    result = benchmark(args.output, args.iterations, args.messages, args.repeats)
    for class_name, per_arm in result["arms"].items():
        for arm_name, bucket in per_arm.items():
            if "wall" not in bucket:
                print(f"{class_name}/{arm_name}: incomplete batch (see error field)")
                continue
            wall, cpu = bucket["wall"], bucket["cpu"]
            extra = ""
            if bucket.get("callback_wall") and bucket["callback_wall"]["count"]:
                extra = (f" | callback wall median={bucket['callback_wall']['median_ns']}ns "
                         f"cpu median={bucket['callback_cpu']['median_ns']}ns "
                         f"empty_polls={bucket['empty_polls']}")
            print(f"{class_name}/{arm_name}: n={wall['count']} callbacks={bucket['callbacks']} "
                  f"wall median={wall['median_ns']}ns p95={wall['p95_ns']}ns p99={wall['p99_ns']}ns "
                  f"cpu median={cpu['median_ns']}ns{extra}")
    print(f"total wall {result['wall_seconds']:.2f}s truncated={result['truncated']} "
          f"error={result.get('error')}")
    return 0 if "error" not in result else 1


if __name__ == "__main__":
    sys.exit(main())
