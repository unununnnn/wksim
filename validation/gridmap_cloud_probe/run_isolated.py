#!/usr/bin/env python3
"""Run real GridMap/ROS cloud callbacks with explicitly synthetic, map-only odom.

Requires a sourced ROS1 and built EGO environment. Creates its own ROS master;
does not start the planner, a flight controller, or a control-state publisher.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import xmlrpc.client

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_probe_result(value):
    """Require the real map contract, never a bare success marker."""
    def require(condition, label):
        if not condition:
            raise ValueError('invalid GridMap probe evidence: ' + label)
    require(value['schema'] == 'wksim.gridmap-cloud-probe.v1', 'schema')
    require(value['result'] == 'pass', 'result')
    require(value['node_name'] == '/uav1_ego_planner_node', 'node')
    require(value['timing_config_valid'] is True, 'timing')
    require(value['timed_out'] is False and value['ros_shutdown_before_success'] is False, 'deadline/shutdown')
    for gate in ('cloud_received_11000', 'cloud_frame_world', 'cloud_layout_valid',
                 'cloud_xyz32_voxel_set', 'odom_received', 'odom_at_contract_start', 'input_gate'):
        require(value['gates'][gate] is True, gate)
    cloud = value['ros_inputs']['cloud']
    require(cloud['unique_voxel_count'] == cloud['point_count'] == 11000, 'voxel count')
    require(all(cloud[name] == 0 for name in ('duplicate_voxel_count', 'invalid_point_count',
                                           'nonfinite_point_count', 'missing_voxel_count')), 'voxel errors')
    require(value['map']['product_odom_valid'] is True, 'product odom')
    require(value['map']['geometry_match'] is True and value['map']['frame_match'] is True, 'map geometry')
    expected = [([-4, 0, 3], 0), ([4, 0, 3], 0), ([0, 0, 3], 1),
                ([-.45, -.95, .05], 1), ([.55, 1.05, 3], 1), ([2, 3, 3], 0),
                ([-10, -6, 0], -1), ([10, 6, 6], -1)]
    require(len(value['queries']) == len(expected), 'query count')
    for query, (coordinate, occupancy) in zip(value['queries'], expected):
        require(query['coordinate'] == coordinate, 'query coordinate')
        require(type(query['actual']) is int and query['actual'] == occupancy, 'actual occupancy')
        require(query['expected'] == occupancy and query['pass'] is True, 'expected occupancy')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--expected-probe-sha256', required=True,
                        help='SHA256 from the independently verified probe build')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    processes = {}
    logs = []
    report = {'status': 'failed', 'map_only': True,
              'odom_source': 'synthetic stationary map fixture; not flight feedback',
              'control_state_published': False, 'cleanup': {}, 'errors': []}
    rospy = None
    try:
        if sha(args.probe) != args.expected_probe_sha256:
            raise ValueError('probe binary differs from expected build SHA256')
        with socket.socket() as port_socket:
            port_socket.bind(('127.0.0.1', 0))
            port = port_socket.getsockname()[1]
        uri = f'http://127.0.0.1:{port}'
        os.environ.update(ROS_MASTER_URI=uri, ROS_IP='127.0.0.1',
                          ROS_HOSTNAME='127.0.0.1', ROS_LOG_DIR=str(output / 'roslogs'))
        report['master_uri'] = uri

        def launch(name, argv):
            stdout = (output / f'{name}.stdout').open('xb')
            stderr = (output / f'{name}.stderr').open('xb')
            logs.extend((stdout, stderr))
            child = subprocess.Popen(argv, stdout=stdout, stderr=stderr,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            processes[name] = child
            report.setdefault('processes', {})[name] = {'pid': child.pid, 'argv': argv,
                'proc_stat': Path(f'/proc/{child.pid}/stat').read_text()}
            return child

        master = launch('master', ['/opt/ros/noetic/bin/rosmaster', '--core', '-p', str(port)])
        # Bound XMLRPC socket calls as well as the readiness loop.
        socket.setdefaulttimeout(2.0)
        rpc = xmlrpc.client.ServerProxy(uri)
        deadline = time.monotonic() + 15
        while True:
            if master.poll() is not None:
                raise RuntimeError('owned ROS master exited before readiness')
            try:
                response = rpc.getPid('/gridmap_isolated_runner')
                if response[0] != 1 or response[2] != master.pid:
                    raise RuntimeError('ROS master endpoint is not the owned process')
                break
            except (OSError, xmlrpc.client.ProtocolError):
                if time.monotonic() >= deadline:
                    raise TimeoutError('owned ROS master readiness')
                time.sleep(.05)

        import rospy as ros
        rospy = ros
        from nav_msgs.msg import Odometry
        from sensor_msgs.msg import PointCloud2
        from tools.publish_ego_profile_scene import validate_pointcloud_message, payload_identity

        rospy.init_node('gridmap_isolated_runner', disable_signals=True)
        rospy.set_param('/use_sim_time', False)
        xml = ROOT / 'Modules/ego_planner_swarm/plan_manage/launch_for_prometheus/advanced_param_wksim_single_box.xml'
        params = {}
        converters = {'int': int, 'double': float, 'bool': lambda x: x == 'true', 'string': str}
        for param in ET.parse(xml).getroot().find('node').findall('param'):
            name = '/uav1_ego_planner_node/' + param.attrib['name']
            value = converters[param.attrib['type']](param.attrib['value'])
            rospy.set_param(name, value)
            params[name] = value
        write(output / 'parameters.json', params)
        report['sources'] = {str(path.relative_to(ROOT)): sha(path) for path in (
            xml, Path(__file__).resolve(), ROOT / 'tools/publish_ego_profile_scene.py',
            ROOT / 'Simulator/wksim_planning/scene_profile.py',
            ROOT / 'validation/gridmap_cloud_probe/gridmap_cloud_probe.cpp',
            ROOT / 'Modules/ego_planner_swarm/plan_env/src/grid_map.cpp')}
        report['probe_binary_sha256'] = sha(args.probe)
        report['profile'] = payload_identity()
        observed = {}

        def receive_cloud(message):
            if observed:
                return
            try:
                validate_pointcloud_message(message)
                data = bytes(message.data)
                receipt = {'frame': message.header.frame_id, 'width': message.width,
                           'height': message.height, 'point_step': message.point_step,
                           'row_step': message.row_step, 'stamp_ns': message.header.stamp.to_nsec(),
                           'payload_sha256': hashlib.sha256(data).hexdigest(),
                           'data_base64': base64.b64encode(data).decode('ascii')}
                write(output / 'received-cloud.json', receipt)
                observed.update(valid=True, payload_sha256=receipt['payload_sha256'])
            except Exception as error:
                observed.update(valid=False, error=repr(error))

        subscriber = rospy.Subscriber('/map_generator/global_cloud', PointCloud2,
                                      receive_cloud, queue_size=1)
        odom_pub = rospy.Publisher('/uav1/prometheus/odom', Odometry, queue_size=1, latch=True)
        odom = Odometry()
        odom.header.frame_id = 'world'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = -4.0
        odom.pose.pose.position.z = 3.0
        odom.pose.pose.orientation.w = 1.0
        probe = launch('probe', [str(args.probe.resolve()), '__name:=uav1_ego_planner_node',
            '~grid_map/cloud:=/map_generator/global_cloud',
            '~grid_map/odom:=/uav1/prometheus/odom', '_probe_timeout_s:=30.0'])
        cloud = launch('publisher', [sys.executable, str(ROOT / 'tools/publish_ego_profile_scene.py'),
                         '--master-uri', uri, '--duration', '10', '--subscriber-timeout', '10'])
        deadline = time.monotonic() + 45
        count = 0
        while probe.poll() is None or cloud.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError('map-only probe/publisher deadline')
            if master.poll() is not None:
                raise RuntimeError('owned master exited during probe')
            odom.header.stamp = rospy.Time.now()
            odom_pub.publish(odom)
            count += 1
            time.sleep(.05)
        report['synthetic_odom_messages'] = count
        report['received_cloud'] = observed
        probe_result = json.loads((output / 'probe.stdout').read_text())
        publisher_result = json.loads((output / 'publisher.stdout').read_text())
        write(output / 'probe.json', probe_result)
        write(output / 'publisher.json', publisher_result)
        verify_probe_result(probe_result)
        if (probe.returncode != 0 or cloud.returncode != 0
                or probe_result.get('result') != 'pass' or observed.get('valid') is not True):
            raise RuntimeError('actual ROS/GridMap evidence failed; inspect raw reports')
        report['status'] = 'pass'
    except BaseException as error:
        report['errors'].append(repr(error))
    finally:
        if rospy is not None:
            rospy.signal_shutdown('owned map-only validation finished')
        # All three direct children are single-process tools; no broad process search/kill.
        for name, child in reversed(list(processes.items())):
            forced = False
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    forced = True
                    child.kill()
                    child.wait(timeout=5)
            report['cleanup'][name] = {'returncode': child.poll(), 'forced_kill': forced,
                                       'reaped': child.poll() is not None}
            if forced or child.poll() is None:
                report['status'] = 'failed'
        for log in logs:
            log.close()
        write(output / 'summary.json', report)
    print(json.dumps({'status': report['status'], 'output': str(output), 'errors': report['errors']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
