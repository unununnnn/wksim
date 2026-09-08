"""Owned SITL handoff: a human changes QGC mode, then explicitly requests takeover."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/'tools'))
from validate_airborne_takeover import TakeoverProbe
from Simulator.wksim_runtime.runtime import run
from Simulator.wksim_runtime.task import grounded
from Simulator.wksim_runtime.independent_profile import select_config


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


class HumanHandoffTask(TakeoverProbe):
    def __init__(self, *args, operator_directory, **kwargs):
        super().__init__(*args, **kwargs)
        self.operator_directory = operator_directory
        self.human_events = []
        self.expect_human_release = False
        self.observed_human_revocation = None
        self._human_wait_elapsed=0.0
        self._human_wait_started=None

    @property
    def operator_wait_seconds(self):
        return self._human_wait_elapsed+(time.monotonic()-self._human_wait_started
            if self._human_wait_started is not None else 0.0)

    def wait_human(self,label,predicate,timeout):
        self._human_wait_started=time.monotonic()
        try:
            return self.wait(label,predicate,timeout)
        finally:
            self._human_wait_elapsed+=time.monotonic()-self._human_wait_started
            self._human_wait_started=None

    def request_gate(self,action,event,filename,predicate,timeout):
        request=dict(version=1,action=action,run_id=self.run_id,control_epoch=self.epoch,nonce=uuid.uuid4().hex)
        path=self.operator_directory/filename
        if path.exists():
            raise RuntimeError('Operator request predates the current human decision')
        self.human_record(event,request=request,request_path=str(path),timeout_s=timeout)

        def requested():
            if not predicate():
                raise RuntimeError('Required native state lost during human decision')
            if not path.exists():
                return False
            if path.is_symlink() or json.loads(path.read_text())!=request:
                raise RuntimeError('Explicit operator request identity differs')
            return True

        self.wait_human('explicit_operator_'+action+'_requested',requested,timeout)
        self.human_record('explicit_operator_'+action+'_requested',request=request)

    def human_record(self, event, **details):
        self.human_events.append(dict(event=event, run_id=self.run_id, control_epoch=self.epoch,
                                      monotonic=time.monotonic(), **details))
        save(self.operator_directory/'human-handoff.json', dict(events=self.human_events,
                                                               current=self.human_events[-1]))

    def on_control_revoked(self, event):
        if self.expect_human_release and event.get('reason') == 'external_mode_left_no_automatic_reacquisition':
            self.observed_human_revocation = event
            self.human_record('external_mode_revocation_observed', native_event=event)
            return
        super().on_control_revoked(event)

    def send(self, msg, label, timeout=10):
        if label=='hold_completed':
            self.request_gate('start_flight','awaiting_window_ready','start-flight-request.json',
                lambda:self.fresh() and grounded(self.state,self.uav_id),300)
        if label == 'yield_mode_completed':
            if (not isinstance(msg, self.Setup) or msg.cmd != self.Setup.SET_PX4_MODE
                    or msg.px4_mode != self.release_mode or not self.owns_control()):
                raise RuntimeError('Human release requires the explicit airborne mode-switch boundary')
            self.expect_human_release = True
            self.human_record('awaiting_human_qgc_mode', expected_mode=self.release_mode,
                              timeout_s=300, mode_command_sent_by_task=False)
            try:
                self.wait_human('human_qgc_mode_observed', lambda: self.loitering()
                          and self.observed_human_revocation is not None, 300)
            finally:
                self.expect_human_release = False
            self.human_record('human_qgc_mode_observed', state=self.convert(self.state))
            return
        if label == 'fresh_airborne_takeover_completed':
            if not self.loitering() or self.observed_human_revocation is None:
                raise RuntimeError('Fresh takeover requires confirmed external mode release')
            self.request_gate('takeover','awaiting_explicit_takeover','takeover-request.json',self.loitering,300)
        return super().send(msg, label, timeout)

    def report(self):
        result = super().report()
        result['human_gcs_handoff'] = dict(events=self.human_events,
            mode_command_sent_by_task=False,
            limitation='Human QGC origin must additionally match the Windows bridge raw mode command evidence')
        return result

    def execute(self):
        super().execute()
        request=dict(run_id=self.run_id,control_epoch=self.epoch,nonce=uuid.uuid4().hex)
        self.human_record('ready_to_stop_bridge',stop_request=request)
        path=self.operator_directory/'bridge-stopped.json'
        def stopped():
            if not self.fresh() or not grounded(self.state,self.uav_id):
                raise RuntimeError('Ground state lost before bridge shutdown')
            if not path.exists():
                return False
            if path.is_symlink() or json.loads(path.read_text())!=request:
                raise RuntimeError('Bridge shutdown acknowledgement identity differs')
            return True
        self.wait('bridge_stop_confirmed_before_fc_exit',stopped,20)
        self.human_record('bridge_stopped_before_fc_exit',stop_request=request)


def gcs_mode_evidence(path, stack):
    """Decode only successfully forwarded, original QGC datagrams; never send."""
    from Simulator.wksim_runtime.telemetry_dialect import load_dialect
    dialect, identity = load_dialect(stack)
    target = 22 if stack == 'px4' else 241
    expected_custom = (4 << 16) | (3 << 24) if stack == 'px4' else 17
    matches=[]
    previous=0
    # The Windows bridge is still appending; only complete lines are evidence.
    for line in path.read_text().split('\n')[:-1]:
        row=json.loads(line)
        if row.get('kind') != 'gcs_bridge_reverse':
            continue
        count=row['relay']['reverse_forwarded']
        if count == previous:
            continue
        if count != previous+1:
            raise ValueError('GCS reverse forwarding sequence differs')
        previous=count
        raw=base64.b64decode(row['packet_base64'],validate=True)
        messages=dialect.MAVLink(None).parse_buffer(raw) or []
        for message in messages:
            if (message.get_srcSystem(),message.get_srcComponent()) != (255,190):
                continue  # Actual controlled QGC identity, verified in the preceding bridge runs.
            accepted=False
            if message.get_type() == 'SET_MODE':
                accepted=(message.target_system==target and message.base_mode & dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                          and message.custom_mode==expected_custom)
            elif message.get_type() == 'COMMAND_LONG' and message.command == dialect.MAV_CMD_DO_SET_MODE:
                accepted=(message.target_system==target and message.target_component in (0,1)
                    and message.param1==dialect.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                    and message.param2==(4 if stack=='px4' else 17)
                    and (stack!='px4' or message.param3==3))
            if accepted:
                matches.append(dict(reverse_forwarded_index=count, source_system=message.get_srcSystem(),
                    source_component=message.get_srcComponent(), message=message.to_dict(),
                    raw_sha256=hashlib.sha256(raw).hexdigest(), raw_base64=row['packet_base64']))
    if not matches:
        raise ValueError('No successfully forwarded QGC native release-mode command')
    return dict(dialect=identity, expected_mode='AUTO.LOITER' if stack=='px4' else 'BRAKE', matches=matches)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    config=json.loads(args.config.read_text())
    if 'mission' in config or config.get('promotion_flight'):
        raise ValueError('Human handoff uses the admitted independent profile without mission/promotion')
    config,_=select_config(config)
    os.environ['LD_LIBRARY_PATH']=str(Path(config['dds_workspace'])/'agent-install/lib')+os.pathsep+os.environ.get('LD_LIBRARY_PATH','')
    root=Path(tempfile.mkdtemp(prefix='wksim-independent-',dir='/root'))
    sources=[Path(__file__),REPO/'tools/validate_airborne_takeover.py',
             REPO/'tools/run-gcs-handoff.sh', REPO/'tools/validate_contained_gcs.py',
             REPO/'tools/request_gcs_takeover.py',REPO/'tools/run-visible-gcs.ps1',REPO/'tools/hold_gcs_button.py']
    record=dict(status='running', native_root=str(root), human_mode_command='required',
                sources_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    save(output/'report.json',record)

    def factory(*arguments, **kwargs):
        return HumanHandoffTask(*arguments,operator_directory=output,**kwargs)

    result=run(config,root,task_factory=factory,physics_duration=3600)
    record['runtime_result']=result
    archive=output/'run'
    archive.mkdir()
    for source in (root/config['run_id']).iterdir():
        if not source.is_symlink() and source.is_file() and source.suffix in ('.json','.jsonl','.log'):
            shutil.copyfile(source,archive/source.name)
    try:
        assert result['status']=='pass' and result['safe_landing'] and result['children_reaped']
        assert result['cleanup_errors']==[]
        events=result['task']['human_gcs_handoff']['events']
        for event in ('human_qgc_mode_observed','explicit_operator_takeover_requested'):
            assert sum(e['event']==event for e in events)==1
        probe=result['task']['takeover_probe']
        assert len(probe['checks'])==4 and len(probe['holds'])==1
        assert all(item['status']=='pass' for item in probe['checks']+probe['holds'])
        record['gcs_mode_evidence']=gcs_mode_evidence(output.parent/'bridge.jsonl',config['stack'])
        record['status']='pass'
    except (AssertionError,KeyError,ValueError,OSError) as error:
        record.update(status='failed',error=result.get('error') or repr(error))
    save(output/'report.json',record)
    print(json.dumps(dict(status=record['status'],report=str(output/'report.json'))),flush=True)
    return 0 if record['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
