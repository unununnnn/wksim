"""Read-only native DDS clock instrumentation for the bounded #8 ground probe.

No flight-control publishers, service clients, or waiting for a sample to unlock
physics. CDR bytes preserve the real messages, including invalid pose floats;
only clock/identity fields are extracted for this experiment.
"""
from collections import Counter
import json
import math
import time


def message_types():
    from ardupilot_msgs.msg import Status, WksimState
    from px4_msgs.msg import VehicleLocalPosition, VehicleStatus
    return dict(ap_clock=WksimState, ap_status=Status,
                px4_clock=VehicleLocalPosition, px4_status=VehicleStatus)


def extract(key, message):
    if key == 'ap_clock':
        stamp = message.time_boot_us
        header_ns = message.header.stamp.sec * 1_000_000_000 + message.header.stamp.nanosec
        if header_ns != stamp * 1000:
            raise ValueError('AP WksimState boot/header clocks disagree')
        return dict(stamp_us=stamp, header_ns=header_ns)
    if key == 'px4_clock':
        return dict(stamp_us=message.timestamp, sample_us=message.timestamp_sample)
    if key == 'ap_status':
        return dict(armed=message.armed)
    if key == 'px4_status':
        if message.system_id != 22:
            raise ValueError('Unexpected native PX4 system identity')
        return dict(armed=message.arming_state == message.ARMING_STATE_ARMED,
                    system_id=message.system_id, stamp_us=message.timestamp)
    raise ValueError('Unsupported observer topic')


def check_sample(value, tick, previous=None):
    if value.get('armed', False):
        raise ValueError('Ground clock probe observed an armed native DDS status')
    stamp = value.get('stamp_us')
    if stamp is not None:
        if type(stamp) is not int or not 0 <= stamp <= tick * 1000:
            raise ValueError('Native source clock is outside the sent model timeline')
        if previous is not None and stamp < previous:
            raise ValueError('Native source clock regressed')
    return stamp


def ap_counter_recurrence(timestamps):
    """Source-derived arithmetic fingerprint, NOT a replacement FC clock.

    Fixed SIM_JSON.cpp:499-521 uses uint64 += (double_stamp-last)*1e6.
    This Python binary64 recurrence is compared to real CDR samples; agreement
    is reported as evidence, never assumed from the formula alone.
    """
    previous, counter, result = 0.0, 0, []
    for stamp in timestamps:
        delta = stamp - previous
        if not math.isfinite(stamp) or not 0 < delta < .1:
            raise ValueError('Arithmetic fingerprint requires regular positive timestamp increments')
        counter = int(counter + delta * 1e6)
        previous = stamp
        result.append(counter)
    return result


class NativeClockObserver:
    def __init__(self, probe):
        import rclpy
        from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
        from rclpy.serialization import serialize_message
        self.ros, self.serialize = rclpy, serialize_message
        self.probe = probe
        self.latest, self.last_stamp, self.counts = {}, {}, Counter()
        self.topics = {}
        rclpy.init(args=[])
        try:
            self.node = rclpy.create_node('wksim_joint_clock_observer', use_global_arguments=False,
                                         enable_rosout=False, start_parameter_services=False)
            qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT,
                             durability=DurabilityPolicy.VOLATILE)
            self.subscriptions = []
            for key, cls in message_types().items():
                if key.startswith('ap_'):
                    topic = '/ap/' + ('wksim/local_state_v1' if key == 'ap_clock' else 'status')
                else:
                    name = 'vehicle_local_position' if key == 'px4_clock' else 'vehicle_status'
                    version = getattr(cls, 'MESSAGE_VERSION', 0)
                    topic = '/wksim_px4_21/fmu/out/' + name + (f'_v{version}' if version else '')
                self.topics[key] = topic
                self.subscriptions.append(self.node.create_subscription(
                    cls, topic, lambda message, key=key: self.receive(key, message), qos))
        except BaseException:
            if hasattr(self, 'node'):
                self.node.destroy_node()
            rclpy.shutdown()
            raise

    def receive(self, key, message):
        value = extract(key, message)
        stamp = check_sample(value, self.probe.tick, self.last_stamp.get(key))
        if stamp is not None:
            self.last_stamp[key] = stamp
        record = dict(topic=self.topics[key], fields=value, received_tick=self.probe.tick,
                      received_monotonic_ns=time.monotonic_ns())
        self.latest[key] = record
        self.counts[key] += 1
        self.probe.log('native-clock', key=key, cdr_hex=self.serialize(message).hex(), **record)

    def pump(self):
        # Never wait for DDS before granting a physical tick. Process at most
        # one ready callback, using a zero timeout, on each diagnostic pump.
        self.ros.spin_once(self.node, timeout_sec=0)

    def ready(self):
        return (set(self.latest) == set(self.topics)
                and all(self.last_stamp.get(key, 0) > 0 for key in ('ap_clock', 'px4_clock')))

    def snapshot(self):
        return dict(latest=dict(self.latest), counts=dict(self.counts))

    def report(self):
        publishers = self.node.get_publisher_names_and_types_by_node(self.node.get_name(), self.node.get_namespace())
        # rclpy can own its standard parameter-events publisher; it is not a
        # flight command endpoint. Disallow every other publisher here.
        if any(name != '/parameter_events' for name, _ in publishers):
            raise RuntimeError('Clock observer unexpectedly owns a publisher')
        clients = self.node.get_client_names_and_types_by_node(self.node.get_name(), self.node.get_namespace())
        if clients:
            raise RuntimeError('Clock observer unexpectedly owns a service client')
        return dict(**self.snapshot(), ready=self.ready(), topics=self.topics,
                    publishers=publishers, service_clients=clients,
                    use_sim_time=self.node.get_parameter('use_sim_time').value,
                    control_publishers_created=0, control_commands_sent=0)

    def close(self):
        self.node.destroy_node()
        self.ros.shutdown()


def audit_native_clock(directory, result):
    """Re-decode retained real CDR; receipt lag is NOT an FC clock error budget."""
    from rclpy.serialization import deserialize_message
    types = message_types()
    counts, last_stamp = Counter(), {}
    samples = {key: [] for key in ('ap_clock', 'px4_clock')}
    pause_counts = Counter()
    with (directory / 'native-clock.jsonl').open() as source:
        for line in source:
            if not line.endswith('\n'):
                raise ValueError('Partial native observation line')
            item = json.loads(line)
            key = item['key']
            value = extract(key, deserialize_message(bytes.fromhex(item['cdr_hex']), types[key]))
            if value != item['fields'] or item['topic'] != result['native_clock_observer']['topics'][key]:
                raise ValueError('Native CDR/topic does not match reported clock/identity')
            stamp = check_sample(value, item['tick'], last_stamp.get(key))
            if stamp is not None:
                last_stamp[key] = stamp
            counts[key] += 1
            if key in samples:
                samples[key].append((stamp, item['tick']))
            if item['phase'].startswith('paused'):
                pause_counts[item['phase'] + '/' + key] += 1
    native = result['native_clock_observer']
    if counts != Counter(native['counts']) or not native['ready']:
        raise ValueError('Native clock summary/counts are not supported')
    if (native['control_publishers_created'] or native['control_commands_sent'] or native['service_clients']
            or native['use_sim_time'] or any(name != '/parameter_events' for name, _ in native['publishers'])):
        raise ValueError('Native observer scope changed')
    summary = {}
    for key, values in samples.items():
        if len(values) < 5:
            raise ValueError('Insufficient native clock observations')
        residues = {stamp % 1000 for stamp, _ in values}
        summary[key] = dict(samples=len(values), first_us=values[0][0], last_us=values[-1][0],
                            millisecond_grid_residues_us=sorted(residues),
                            off_millisecond_grid=sum(stamp % 1000 != 0 for stamp, _ in values),
                            max_receipt_lag_us=max(tick * 1000 - stamp for stamp, tick in values))
    with (directory / 'arducopter-truth.jsonl').open() as source:
        times = [json.loads(line)['state'][2] for line in source]
    predicted = ap_counter_recurrence(times)
    inverse = {stamp: tick for tick, stamp in enumerate(predicted, 1)}
    matches = [(stamp, inverse[stamp], received) for stamp, received in samples['ap_clock']
               if stamp in inverse and inverse[stamp] <= received]
    deficits = [tick * 1000 - stamp for stamp, tick, _ in matches]
    fingerprint = dict(kind='source-derived binary64/integer recurrence, not independent FC telemetry',
                       final_predicted_deficit_us=len(predicted) * 1000 - predicted[-1],
                       native_samples_matching_predicted_grid=len(matches),
                       native_samples_total=len(samples['ap_clock']),
                       matched_native_deficit_us=dict(min=min(deficits), max=max(deficits)) if deficits else None)
    return dict(clocks=summary, delivered_during_pause=dict(pause_counts),
                ap_arithmetic_fingerprint=fingerprint,
                scope='native microsecond observations, not per-tick AP control ACK or a production time budget')
