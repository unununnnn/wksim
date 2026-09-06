"""Exercise the generated ROS2 types and isolated RMW topic/service/action paths.

Run through build-prometheus-ros2.sh, never against a live flight ROS graph.
Test values are wire fixtures, not vehicle commands or sensor-valid scenarios.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import traceback

import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.serialization import deserialize_message, serialize_message
from rosidl_parser import definition as d
from rosidl_runtime_py.utilities import get_action, get_message, get_service


def sample(slot):
    if isinstance(slot, d.BasicType):
        if slot.typename == 'boolean':
            return True
        if slot.typename in ('float', 'double', 'long double'):
            return -1.25  # Exactly representable in both float32 and float64.
        if slot.typename in ('char', 'wchar'):
            return 'x'
        if slot.typename == 'octet':
            return b'\x07'
        return 7
    if isinstance(slot, d.AbstractGenericString):
        return 'wksim_测'[:getattr(slot, 'maximum_size', 20)]
    if isinstance(slot, d.NamespacedType):
        cls = getattr(importlib.import_module('.'.join(slot.namespaces)), slot.name)
        return populated(cls)
    if isinstance(slot, d.Array):
        return [sample(slot.value_type) for _ in range(slot.size)]
    if isinstance(slot, (d.BoundedSequence, d.UnboundedSequence)):
        return [sample(slot.value_type) for _ in range(min(2, getattr(slot, 'maximum_size', 2)))]
    raise TypeError(f'Unhandled IDL type: {slot!r}')


def populated(cls):
    msg = cls()
    for name, slot in zip(msg.get_fields_and_field_types(), msg.SLOT_TYPES):
        setattr(msg, name, sample(slot))
    return msg


def wire_roundtrip(cls):
    results = []
    for msg in (cls(), populated(cls)):
        data = serialize_message(msg)
        restored = deserialize_message(data, cls)
        if restored != msg:
            raise AssertionError(f'CDR roundtrip mismatch for {cls.__name__}')
        results.append(dict(size=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return dict(type=cls.__name__, default=results[0], populated=results[1])


def spin_until(node, ready, timeout=15):
    deadline = time.monotonic() + timeout
    while not ready():
        if time.monotonic() >= deadline:
            raise TimeoutError('ROS2 test did not complete before the wall-clock deadline')
        rclpy.spin_once(node, timeout_sec=0.02)


def middleware_test():
    # A unique name is supplementary isolation; a private net namespace is required.
    if os.readlink('/proc/self/ns/net') == os.readlink('/proc/1/ns/net'):
        raise RuntimeError('Refusing middleware tests in the host network namespace')
    from prometheus_msgs.msg import UAVCommand
    from prometheus_msgs.srv import SwitchLocationSource
    from prometheus_msgs.action import CheckForObjects

    rclpy.init()
    node = rclpy.create_node(f'prometheus_interface_check_{os.getpid()}', namespace='/wksim_interface_test')
    try:
        received = []
        subscription = node.create_subscription(UAVCommand, 'uav_command', received.append, 10)
        publisher = node.create_publisher(UAVCommand, 'uav_command', 10)
        command = populated(UAVCommand)
        command.agent_cmd = UAVCommand.MOVE
        command.move_mode = UAVCommand.XYZ_POS
        command.command_id = 123456
        spin_until(node, lambda: publisher.get_subscription_count() == 1)
        publisher.publish(command)
        spin_until(node, lambda: bool(received))
        if received[0] != command:
            raise AssertionError('DDS topic content mismatch')

        request_seen = []
        def service_cb(request, response):
            request_seen.append(request)
            return populated(SwitchLocationSource.Response)
        server = node.create_service(SwitchLocationSource, 'switch_source', service_cb)
        client = node.create_client(SwitchLocationSource, 'switch_source')
        spin_until(node, client.service_is_ready)
        request = populated(SwitchLocationSource.Request)
        future = client.call_async(request)
        spin_until(node, future.done)
        if request_seen != [request] or future.result() != populated(SwitchLocationSource.Response):
            raise AssertionError('DDS service content mismatch')

        feedback, goals = [], []
        def execute(goal):
            goals.append(goal.request)
            goal.publish_feedback(CheckForObjects.Feedback())
            goal.succeed()
            return populated(CheckForObjects.Result)
        action_server = ActionServer(node, CheckForObjects, 'check_objects', execute_callback=execute)
        action_client = ActionClient(node, CheckForObjects, 'check_objects')
        spin_until(node, action_client.server_is_ready)
        goal = populated(CheckForObjects.Goal)
        accepted = action_client.send_goal_async(goal, feedback_callback=feedback.append)
        spin_until(node, accepted.done)
        if not accepted.result().accepted:
            raise AssertionError('Action goal was rejected')
        result = accepted.result().get_result_async()
        spin_until(node, lambda: result.done() and bool(feedback))
        from action_msgs.msg import GoalStatus
        if (goals != [goal] or result.result().status != GoalStatus.STATUS_SUCCEEDED
                or result.result().result != populated(CheckForObjects.Result)):
            raise AssertionError('DDS action content/status mismatch')
        action_client.destroy()
        action_server.destroy()
        return dict(topic='UAVCommand', service='SwitchLocationSource', action='CheckForObjects',
                    action_feedback=len(feedback), namespace=node.get_namespace(),
                    network_namespace=os.readlink('/proc/self/ns/net'), domain=os.environ['ROS_DOMAIN_ID'])
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    started = time.time()
    report = dict(status='failed', started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  workspace=str(args.workspace), ros_distro=os.environ.get('ROS_DISTRO'), python=platform.python_version(),
                  rmw=rclpy.utilities.get_rmw_implementation_identifier(), schemas=[], source_sha256={})
    try:
        package = args.workspace/'src/prometheus_msgs'
        provenance = json.loads((package/'UPSTREAM.json').read_text())
        import prometheus_msgs
        module_file = Path(prometheus_msgs.__file__).resolve()
        if not module_file.is_relative_to((args.workspace/'install').resolve()):
            raise RuntimeError(f'Imported a different prometheus_msgs build: {module_file}')
        report['imported_package'] = str(module_file)
        report['upstream_commit'] = provenance['commit']
        report['source_sha256'] = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in sorted(package.rglob('*')) if p.is_file()}
        for interface in provenance['interfaces']:
            if report['source_sha256'][interface['file']] != interface['migrated_sha256']:
                raise AssertionError(f'Staged schema differs from provenance: {interface["file"]}')
            path = Path(interface['file'])
            name = f'prometheus_msgs/{path.parent.name}/{path.stem}'
            if path.suffix == '.msg':
                classes = [get_message(name)]
            elif path.suffix == '.srv':
                srv = get_service(name)
                classes = [srv.Request, srv.Response]
            else:
                action = get_action(name)
                classes = [action.Goal, action.Result, action.Feedback]
            report['schemas'].append(dict(interface=name, messages=[wire_roundtrip(cls) for cls in classes]))
        report['middleware'] = middleware_test()
        report['status'] = 'pass'
    except Exception:
        report['error'] = traceback.format_exc()
    report['elapsed_seconds'] = time.time() - started
    report['interface_count'] = len(report['schemas'])
    report['message_type_count'] = sum(len(s['messages']) for s in report['schemas'])
    report['roundtrip_count'] = report['message_type_count'] * 2
    report['versions'] = subprocess.check_output(['dpkg-query', '-W', '-f=${Package} ${Version}\n',
        'ros-humble-rosidl-default-generators', 'ros-humble-rclpy', 'ros-humble-rmw-fastrtps-cpp', 'python3-colcon-core'], text=True)
    output = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (args.evidence/'result.json').write_text(output)
    print(json.dumps({k:report[k] for k in ('status', 'interface_count', 'message_type_count', 'roundtrip_count', 'elapsed_seconds')}, indent=2))
    if 'error' in report:
        print(report['error'])
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
