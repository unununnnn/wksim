"""Product-owned public Prometheus task worker, on the joint ROS clock."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import traceback

from .evidence import write_json
from .joint_parent import DirectParentGuard
from .task import Task
from .joint_config import FIXED_TASKS
from .joint_aruco_profile import TASK as ARUCO_TASK
from tools.pv_trajectory_task import PVTask
from tools.mixed_control_task import MixedTask


class JointTask(Task):
    """Configured residence times on the existing Task simulation clock."""
    def dwell(self,label,predicate,seconds):
        key={'hold_completed':'hold','waypoint_completed':'waypoint'}.get(label)
        if key is None:
            return super().dwell(label,predicate,seconds)
        seconds=self.joint_dwell_seconds[key]
        start=self.task_time()
        deadline=start+seconds+15
        while self.task_time()-start<seconds:
            self.pump()
            if not predicate(): raise RuntimeError(label+': integration threshold exceeded')
            if self.task_time()>=deadline: raise TimeoutError(label+': ROS clock dwell timeout')
        self.phase(label)


class JointPVTask(PVTask, JointTask):
    recorder_name = 'wksim_joint_supervisor'


class JointMixedTask(MixedTask, JointTask):
    recorder_name = 'wksim_joint_supervisor'


def task_class(task_type):
    if task_type == ARUCO_TASK:
        from .aruco_joint_task import JointArUcoTask
        return JointArUcoTask
    return {FIXED_TASKS[0]: JointPVTask, FIXED_TASKS[1]: JointMixedTask,
            'public_position': JointTask, 'public_velocity_yaw': JointTask}[task_type]


def run(path):
    import rclpy
    settings=json.loads(path.read_text())
    directory=path.parent
    result=dict(status='failed',run_id=settings['run_id'],scene_epoch=settings['epoch'],
                stack=settings['stack'],uav_id=settings['uav_id'],task_mode=settings['mode'],phases=[],
                task_dwell_seconds=settings['task_dwell_seconds'],use_sim_time=True,
                task_profile=settings.get('task_type','public_position'))
    fixed = result['task_profile'] in FIXED_TASKS
    aruco = result['task_profile'] == ARUCO_TASK
    started=time.monotonic()
    task=None
    rclpy.init(args=[])
    try:
        package=Path(importlib.util.find_spec('prometheus_control').origin).parent.resolve()
        if str(package)!=settings['control_package']:
            raise RuntimeError('Task did not resolve the admitted installed Control package')
        health=DirectParentGuard(settings['parent'])
        def phase(name):
            row=dict(phase=name,wall_seconds=time.monotonic()-started,
                     ros_time_ns=task.node.get_clock().now().nanoseconds,
                     state=task.convert(task.state) if task.state is not None else None)
            result['phases'].append(row)
            write_json(directory/'progress.json',row)
        if fixed and (settings['mode'] != 'initial' or settings['task_dwell_seconds'] != {'hold':5,'waypoint':2}):
            raise ValueError('Fixed trajectory task cannot recover or change residence times')
        task=task_class(result['task_profile'])(directory,health,phase,settings['stack'],run_id=settings['run_id'],protocol='session_v1',
                  uav_id=settings['uav_id'],use_sim_time=True,scene_epoch=settings['epoch'],
                  **({'aruco_settings':settings['aruco_settings']} if result['task_profile']==ARUCO_TASK else {}),
                  **({'trajectory_epoch':settings['epoch']} if fixed else {}))
        task.joint_dwell_seconds=settings['task_dwell_seconds']
        # Initialize DDS transport before the supervisor starts its paced clock.
        # This marker grants no flight readiness or command authority; go.json
        # remains required before execute() can publish any task request.
        def transport_ready():
            return task.request_graph_ready() if fixed or aruco else (
                task.setup_pub.get_subscription_count()==1 and task.command_pub.get_subscription_count()==1)
        while not transport_ready():
            health()
            rclpy.spin_once(task.node,timeout_sec=.02)
            if aruco: task.raw_capture.drain()
        write_json(directory/'initialized.json',dict(version=1,run_id=settings['run_id'],epoch=settings['epoch'],
            stack=settings['stack'],token=settings['token'],control_subscriptions=[2,2] if fixed or aruco else [1,1],
            **({'request_graph':task.pv_request_graph} if fixed else
               {'request_graph':task.aruco_request_graph} if aruco else {})))
        # A product task may join a scene long after boot. Establish its current
        # ROS clock before calculating any simulation-time timeout.
        while task.task_time()==0:
            health()
            rclpy.spin_once(task.node,timeout_sec=.02)
            if aruco: task.raw_capture.drain()
        task.wait('public_ready',lambda:(task.recovery_transport_fresh() if settings['mode']=='recovery' else task.fresh())
                  and transport_ready(),55)
        ready=dict(version=1,run_id=settings['run_id'],epoch=settings['epoch'],uav_id=settings['uav_id'],
                   control_epoch=task.epoch,request_high_water=task.request_id,token=settings['token'])
        write_json(directory/'ready.json',ready)
        go=directory.parent/'go.json'
        while not go.is_file():
            task.pump()
        offer=json.loads(go.read_text())
        if (offer['run_id']!=settings['run_id'] or offer['epoch']!=settings['epoch']
                or offer['tasks'][settings['stack']]!=ready):
            raise ValueError('Task start offer differs from its ready identity')
        if settings['mode']=='recovery':
            if settings.get('task_type','public_position')!='public_position':
                raise ValueError('Airborne recovery is defined only for the public_position task')
            task.recover_then_land(allow_native_hold=settings['stack']=='px4')
        elif settings.get('task_type','public_position')=='public_velocity_yaw':
            task.execute_velocity_yaw()
        else:
            task.execute()
        result['status']='pass'
    except BaseException as error:
        result.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        if task is not None:
            try:
                result['task']=task.report()
            except BaseException as error:
                result.update(status='failed',report_error=repr(error),report_traceback=traceback.format_exc())
            try:
                task.close()
            except BaseException as error:
                result.update(status='failed',cleanup_error=repr(error))
        if rclpy.ok():
            rclpy.shutdown()
        result['wall_seconds']=time.monotonic()-started
        result['worker_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        write_json(directory/'result.json',result)
    return 0 if result['status']=='pass' else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('settings',type=Path)
    args=parser.parse_args()
    raise SystemExit(run(args.settings))
