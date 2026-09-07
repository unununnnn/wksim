"""Opt-in DEBUG-wksim-native-state observer around the sealed real Control code.

Calls each original callback/state/freshness method exactly once. No publisher,
flight command, clock adjustment, sleep, or replacement validity decision.
"""
import atexit
import hashlib
import json
from pathlib import Path


def install(path):
    from rclpy.node import Node
    from rclpy.executors import Executor
    import rclpy.executors
    from rclpy.serialization import serialize_message
    from prometheus_control.native_px4 import PX4Link
    from px4_msgs.msg import (VehicleStatus, VehicleLocalPosition, VehicleAttitude,
                             SensorGps, EstimatorStatusFlags)

    classes = (VehicleStatus, VehicleLocalPosition, VehicleAttitude, SensorGps, EstimatorStatusFlags)
    keys = ('status', 'position', 'attitude', 'gps', 'estimator')
    stream = Path(path).open('x', buffering=1)
    original_subscription = Node.create_subscription
    original_take = Executor._take_subscription
    original_receive, original_state, original_fresh = PX4Link.receive, PX4Link.state, PX4Link.fresh
    receipts, evaluations, signatures = {}, {}, {}
    closed = False
    executor_path = Path(rclpy.executors.__file__)
    stream.write(json.dumps(dict(tag='DEBUG-wksim-native-state',kind='runtime_source',
        executor_path=str(executor_path),executor_sha256=hashlib.sha256(executor_path.read_bytes()).hexdigest()))+'\n')

    def context(link):
        session = getattr(link.node, 'session', None)
        scene = getattr(link.node, 'scene', None)
        return dict(run_id=getattr(session, 'run_id', None), control_epoch=getattr(session, 'epoch', None),
                    scene_epoch=getattr(scene, 'epoch', None), native_generation=link.generation,
                    last_public_sequence=getattr(link.node, 'sequence', None), clock_invalid=link.clock_invalid)

    def write(kind, link, **fields):
        stream.write(json.dumps(dict(tag='DEBUG-wksim-native-state', kind=kind,
                                    **context(link), **fields), allow_nan=False, separators=(',', ':'))+'\n')

    def snapshot(link, key):
        message = link.latest.get(key)
        if message is None:
            return dict(missing=True)
        return dict(received_monotonic_s=link.received[key], source_timestamp_us=message.timestamp,
                    sample_timestamp_us=getattr(message, 'timestamp_sample', None),
                    receipt=receipts.get((id(link), key)), cdr_hex=serialize_message(message).hex())

    def publishers(link, info):
        if info is None or not hasattr(link.node, 'get_publishers_info_by_topic'):
            return None
        return [dict(gid=bytes(writer.endpoint_gid).hex(),node_name=writer.node_name,
                     node_namespace=writer.node_namespace)
                for writer in link.node.get_publishers_info_by_topic(info['topic'])]

    def subscription(node, msg_type, topic, callback, qos, *args, **kwargs):
        if msg_type not in classes:
            return original_subscription(node, msg_type, topic, callback, qos, *args, **kwargs)
        def observed(message):
            node._wksim_debug_message_info = observed._wksim_debug_message_info
            try:
                callback(message)
            finally:
                node._wksim_debug_message_info = None
        observed._wksim_debug_topic = topic
        observed._wksim_debug_message_info = None
        return original_subscription(node, msg_type, topic, observed, qos, *args, **kwargs)

    def take(executor, sub):
        # This installed Humble executor discards take_message()[1]. Retain only
        # that metadata, preserving its one take and unchanged returned message.
        if not hasattr(sub.callback, '_wksim_debug_topic'):
            return original_take(executor, sub)
        with sub.handle:
            pair = sub.handle.take_message(sub.msg_type, sub.raw)
            if pair is not None:
                message, info = pair
                sub.callback._wksim_debug_message_info = dict(topic=sub.callback._wksim_debug_topic,
                    publisher_gid=bytes(info['publisher_gid']).hex() if 'publisher_gid' in info else None,
                    available_message_info_keys=sorted(info),
                    dds_source_timestamp_ns=info['source_timestamp'],
                    dds_received_timestamp_ns=info['received_timestamp'])
                return message
        return None

    def receive(link, key, message):
        result = original_receive(link, key, message)
        if key in keys:
            accepted = link.latest.get(key) is message
            info = getattr(link.node, '_wksim_debug_message_info', None)
            if accepted:
                receipts[id(link), key] = info
            if key == 'estimator' or not accepted:
                write('native_callback', link, key=key, accepted=accepted, callback_monotonic_s=link.last_clock,
                      accepted_received_monotonic_s=link.received.get(key), receipt=info,
                      publishers_discovered_after_callback=publishers(link,info),
                      source_timestamp_us=message.timestamp, cdr_hex=serialize_message(message).hex(),
                      latest_rejection=link.rejections[-1] if not accepted and link.rejections else None)
        return result

    def fresh(link, *wanted):
        result = original_fresh(link, *wanted)
        checks = evaluations.get(id(link))
        if checks is not None:
            now = link.last_clock
            checks.append(dict(keys=list(wanted), evaluated_monotonic_s=now, result=result,
                stale_seconds=link.stale_seconds, clock_invalid=link.clock_invalid,
                ages_s={key:now-link.received[key] if key in link.received else None for key in wanted}))
        return result

    def state(link, uav_id):
        checks = []
        evaluations[id(link)] = checks
        try:
            result = original_state(link, uav_id)
        finally:
            evaluations.pop(id(link), None)
        signature = (result.connected, result.odom_valid, link.generation, result.mode, result.armed)
        if signatures.get(id(link)) != signature:
            signatures[id(link)] = signature
            write('state_transition', link, uav_id=uav_id, connected=result.connected,
                odom_valid=result.odom_valid, mode=result.mode, armed=result.armed, checks=checks,
                public_state_cdr_hex=serialize_message(result).hex(),
                sources={key:dict(**snapshot(link,key),publishers_discovered_after_evaluation=
                    publishers(link,receipts.get((id(link),key)))) for key in keys})
        return result

    def close():
        nonlocal closed
        if not closed:
            Node.create_subscription = original_subscription
            Executor._take_subscription = original_take
            PX4Link.receive, PX4Link.state, PX4Link.fresh = original_receive, original_state, original_fresh
            stream.close()
            closed = True

    Node.create_subscription = subscription
    Executor._take_subscription = take
    PX4Link.receive, PX4Link.state, PX4Link.fresh = receive, state, fresh
    atexit.register(close)
    return close
