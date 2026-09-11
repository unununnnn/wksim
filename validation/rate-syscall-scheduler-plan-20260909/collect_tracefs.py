"""Private tracefs diagnostic collector. --preflight never creates/enables tracing.

Capture needs root, three or five exact PID:start_ticks identities and their boot_id.
It sends no signal to a target. All tracefs mutations stay in one new instance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import sys
import tempfile
import time
import uuid

TRACE=Path('/sys/kernel/tracing')
EVENTS=('syscalls/sys_enter_write','syscalls/sys_exit_write',
        'syscalls/sys_enter_fsync','syscalls/sys_exit_fsync',
        'syscalls/sys_enter_fdatasync','syscalls/sys_exit_fdatasync',
        'sched/sched_switch','sched/sched_wakeup')
LOSS=('overrun','commit overrun','dropped events')
FC_THREADS={'ap_fc':('arducopter','log_io','DDS'),
            'px4_fc':('sim_send','logger','wq:lp_default')}
BASE_ROLES=('ap_worker','px4_worker','supervisor')
TRACE_PIPE_FLAGS=os.O_RDONLY|getattr(os,'O_NONBLOCK',0)


def require(value,message):
    if not value: raise ValueError(message)


def owner(text):
    require(re.fullmatch(r'[1-9][0-9]*:[1-9][0-9]*',text) is not None,'Expected PID:start_ticks')
    pid,start=map(int,text.split(':'))
    return dict(pid=pid,start_ticks=start)


def boot():return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def identity(pid):
    root=Path('/proc')/str(pid)
    text=(root/'stat').read_text()
    fields=text[text.rfind(')')+2:].split()
    require(len(fields)>19,'Process identity is incomplete')
    return dict(pid=pid,pgid=int(fields[2]),start_ticks=int(fields[19]),
                argv=(root/'cmdline').read_bytes().rstrip(b'\0').decode(errors='replace').split('\0'))


def task_inventory(pid):
    """Return stable namespace-local task identities for one owned process."""
    root=Path('/proc')/str(pid)/'task'
    result=[]
    for path in sorted(root.iterdir(),key=lambda value:int(value.name)):
        require(path.name.isdigit(),'Non-numeric task entry')
        before=(path/'stat').read_text()
        status=(path/'status').read_text()
        after=(path/'stat').read_text()
        before_end=before.rfind(')');after_end=after.rfind(')')
        before_fields=before[before_end+2:].split();after_fields=after[after_end+2:].split()
        before_comm=before[before.find('(')+1:before_end]
        after_comm=after[after.find('(')+1:after_end]
        tgid=re.search(r'^Tgid:\s*(\d+)$',status,re.MULTILINE)
        require(len(before_fields)>19 and len(after_fields)>19 and tgid is not None
                and int(tgid.group(1))==pid,
                'Task does not belong to owned process: '+path.name)
        comm=(path/'comm').read_text().strip()
        require(before_comm==after_comm==comm and before_fields[19]==after_fields[19],
                'Task identity changed during inventory: '+path.name)
        result.append(dict(local_tid=int(path.name),comm=comm,start_ticks=int(before_fields[19])))
    require(result,'Owned process has no tasks: '+str(pid))
    return result


def required_fc_threads(owners):
    """Select one exact local task for every required FC comm name."""
    selected={}
    inventories={}
    for role,names in FC_THREADS.items():
        rows=task_inventory(owners[role]['pid'])
        inventories[role]=rows
        for name in names:
            matches=[row for row in rows if row['comm']==name]
            require(len(matches)==1,'Required FC thread absent/ambiguous: '+role+'/'+name)
            selected[role+'/'+name]=matches[0]
    return selected,inventories


def verify(owners,expected_boot):
    require(boot()==expected_boot,'Boot identity changed')
    found={}
    for name,expected in owners.items():
        value=identity(expected['pid'])
        require(value['start_ticks']==expected['start_ticks'],'Owned lifetime changed: '+name)
        found[name]=value
    return found


def fds(pid):
    root=Path('/proc')/str(pid)
    values={}
    for path in sorted((root/'fd').iterdir()):
        try:
            values[path.name]=dict(target=os.readlink(path),fdinfo=(root/'fdinfo'/path.name).read_text())
        except FileNotFoundError:
            values[path.name]=dict(raced_with_close=True)
    return dict(fds=values,mountinfo=(root/'mountinfo').read_text())


def verify_roles(found,run_id,epoch):
    for role,stack in (('ap_worker','arducopter'),('px4_worker','px4')):
        argv=found[role]['argv']
        require('Simulator.wksim_core.worker' in argv and argv.count('--epoch')==1 and argv.count('--trace')==1,
                'Target is not the expected model worker: '+role)
        require(argv[argv.index('--epoch')+1]==epoch,'Worker epoch differs')
        trace=Path(argv[argv.index('--trace')+1])
        require(trace.name==stack+'-truth.jsonl' and trace.parent.name==epoch
                and trace.parent.parent.name=='epochs' and trace.parent.parent.parent.name==run_id,
                'Worker trace/run binding differs')
    argv=found['supervisor']['argv']
    require('Simulator.wksim_runtime.joint_runtime' in argv and epoch in argv
            and any(v.startswith('/') and Path(v).name==run_id for v in argv),'Supervisor run/epoch differs')
    for role,binary in (('ap_fc','arducopter'),('px4_fc','px4')):
        if role not in found:continue
        argv=found[role]['argv']
        require(argv and Path(argv[0]).name==binary and any(run_id in v and epoch in v for v in argv),
                'FC run/epoch differs: '+role)


def filters(pids):
    workers=[pids[n] for n in ('ap_worker','px4_worker')]
    loggers=[pids[n] for n in ('ap_fc/log_io','px4_fc/logger') if n in pids]
    writes=' || '.join('common_pid == '+str(pid) for pid in workers+loggers)
    tids=list(pids.values())
    switches=' || '.join(f'prev_pid == {pid} || next_pid == {pid}' for pid in tids)
    wakes=' || '.join('pid == '+str(pid) for pid in tids)
    result={'syscalls/sys_enter_write':writes,'syscalls/sys_exit_write':writes,
            'sched/sched_switch':switches,'sched/sched_wakeup':wakes}
    if loggers:
        syncs=' || '.join('common_pid == '+str(pid) for pid in loggers)
        result.update({'syscalls/sys_enter_fsync':syncs,'syscalls/sys_exit_fsync':syncs,
            'syscalls/sys_enter_fdatasync':syncs,'syscalls/sys_exit_fdatasync':syncs})
    return result


MAPPING_TIMEOUT_S=3.
MAPPING_SELECT_S=.01


def _sched_switch_pairs(line):
    """Return exact comm/PID pairs from one textual sched_switch event."""
    pairs=[]
    for match in re.finditer(
            r'prev_comm=(\S+)\s+prev_pid=(\d+)|next_comm=(\S+)\s+next_pid=(\d+)',line):
        pairs.append((match.group(1) or match.group(3),match.group(2) or match.group(4)))
    return pairs


def scan_global_comm_owners(expected,proc_root=None):
    """Require every target comm to belong to exactly one expected local task."""
    require(expected and len(expected)==len(set(expected)),'Expected comm names are not distinct')
    proc_root=Path('/proc') if proc_root is None else Path(proc_root)
    last_missing=[]
    for attempt in range(2):
        matches={name:[] for name in expected}
        races=[]
        for process in proc_root.iterdir():
            if not process.name.isdigit():continue
            try:tasks=list((process/'task').iterdir())
            except (FileNotFoundError,NotADirectoryError) as error:
                races.append(str(error));continue
            for task in tasks:
                if not task.name.isdigit():continue
                try:comm=(task/'comm').read_text().strip()
                except (FileNotFoundError,NotADirectoryError) as error:
                    races.append(str(error));continue
                if comm in matches:
                    matches[comm].append(dict(tgid=int(process.name),tid=int(task.name)))
        foreign=[];last_missing=[]
        for name,owner in expected.items():
            values=matches[name]
            if not values:last_missing.append(name)
            if values!=[dict(tgid=owner['tgid'],tid=owner['tid'])]:
                foreign.append(dict(comm=name,expected=owner,observed=values))
        if not foreign:
            return dict(matches=matches,scan_attempts=attempt+1,ignored_races=races)
        only_missing=all(not row['observed'] for row in foreign)
        if not (attempt==0 and only_missing and races):
            raise ValueError('Global comm ownership mismatch: '+json.dumps(foreign,sort_keys=True))
    raise ValueError('Global comm ownership missing after retry: '+','.join(last_missing))


def map_sched_switch_pids(instance,put,names,output):
    """Map exact comm names using a bounded private sched_switch window.

    The tracepoint PID fields are the only source of kernel-visible IDs. The
    mapping accepts one and only one PID for each exact comm; a second PID is
    an ambiguity and a missing name at the deadline fails closed. Polling
    trace_pipe makes the window event-driven instead of sleeping for a fixed
    warm-up interval.
    """
    require(len(set(names.values()))==len(names),'Trace comm names are not distinct')
    expression=' || '.join(
        f'prev_comm == "{name}" || next_comm == "{name}"'
        for name in names.values())
    candidates={role:set() for role in names}
    raw=bytearray()
    descriptor=None
    pending=b''
    primary=None
    try:
        put('events/sched/sched_switch/filter',expression)
        put('events/sched/sched_switch/enable','1')
        descriptor=os.open(instance/'trace_pipe',TRACE_PIPE_FLAGS)
        put('tracing_on','1')
        deadline=time.monotonic()+MAPPING_TIMEOUT_S
        while time.monotonic()<deadline and not all(len(values)==1 for values in candidates.values()):
            timeout=min(MAPPING_SELECT_S,max(0,deadline-time.monotonic()))
            ready,_,_=select.select([descriptor],[],[],timeout)
            if not ready:
                continue
            try:chunk=os.read(descriptor,1024*1024)
            except BlockingIOError:continue
            if not chunk:
                continue
            raw.extend(chunk)
            pending+=chunk
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1)
                text=line.decode(errors='replace')
                for comm,pid_text in _sched_switch_pairs(text):
                    for role,name in names.items():
                        if comm==name:
                            candidates[role].add(int(pid_text))
                            require(len(candidates[role])==1,
                                    'Kernel PID mapping ambiguous: '+role)
                            break
        if pending.strip():
            text=pending.decode(errors='replace')
            for comm,pid_text in _sched_switch_pairs(text):
                for role,name in names.items():
                    if comm==name:
                        candidates[role].add(int(pid_text))
                        require(len(candidates[role])==1,
                                'Kernel PID mapping ambiguous: '+role)
                        break
        missing=[role for role,values in candidates.items() if len(values)!=1]
        require(not missing,'Kernel PID mapping timed out: '+','.join(missing))
    except BaseException as error:
        primary=error
    finally:
        cleanup_errors=[]
        for relative,value in (('tracing_on','0'),
                               ('events/sched/sched_switch/enable','0')):
            try:put(relative,value)
            except BaseException as error:cleanup_errors.append(relative+': '+str(error))
        if descriptor is not None:
            try:os.close(descriptor)
            except BaseException as error:cleanup_errors.append('trace_pipe close: '+str(error))
        try:(output/'pid-mapping-trace.txt').write_bytes(bytes(raw))
        except BaseException as error:cleanup_errors.append('mapping trace write: '+str(error))
        try:put('trace','')
        except BaseException as error:cleanup_errors.append('trace: '+str(error))
        if cleanup_errors:
            try:(output/'pid-mapping-cleanup-errors.json').write_text(
                    json.dumps(cleanup_errors,indent=2)+'\n')
            except BaseException as error:cleanup_errors.append('cleanup evidence: '+str(error))
            message='Kernel PID mapping cleanup failed: '+'; '.join(cleanup_errors)
            if primary is not None:message=str(primary)+'; '+message
            primary=ValueError(message)
    if primary is not None:raise primary
    return {role:values.pop() for role,values in candidates.items()}


def map_kernel_pids(instance,put,owners,epoch,output):
    """Correlate exact owned comm names through a bounded private sched trace."""
    names={role:'wk'+epoch[:11]+suffix for role,suffix in (
        ('ap_worker','a'),('px4_worker','p'),('supervisor','s'))}
    for role,name in names.items():
        require((Path('/proc')/str(owners[role]['pid'])/'comm').read_text().strip()==name,
                'Diagnostic comm name missing or wrong: '+role)
    local_threads,inventories_before=required_fc_threads(owners) if 'ap_fc' in owners else ({},{})
    names.update({role:value['comm'] for role,value in local_threads.items()})
    require(len(set(names.values()))==len(names),'Trace comm names are not distinct')
    expected={name:dict(role=role,tgid=(owners[role]['pid'] if role in BASE_ROLES else
        owners[role.split('/')[0]]['pid']),tid=(owners[role]['pid'] if role in BASE_ROLES else
        local_threads[role]['local_tid'])) for role,name in names.items()}
    comm_owners_before=scan_global_comm_owners(expected)
    mapped=map_sched_switch_pids(instance,put,names,output)
    require(len(set(mapped.values()))==len(mapped),'Kernel PID mappings are not distinct')
    local_threads_after,inventories_after=required_fc_threads(owners) if 'ap_fc' in owners else ({},{})
    require(local_threads_after==local_threads,'Required FC thread identity changed during mapping')
    comm_owners_after=scan_global_comm_owners(expected)
    mapping_trace=output/'pid-mapping-trace.txt'
    mapping_sha256=hashlib.sha256(mapping_trace.read_bytes()).hexdigest()
    mapping=dict(names=names,kernel_pids=mapped,
                local_threads=local_threads,inventories_before=inventories_before,
                inventories_after=inventories_after,
                comm_owners_before=comm_owners_before,comm_owners_after=comm_owners_after,
                method='owned exact comm names observed in a bounded private sched_switch window',
                mapping_source='private_sched_switch',
                mapping_timeout_s=MAPPING_TIMEOUT_S,
                mapping_sha256=mapping_sha256,
                mapping_trace_bytes=mapping_trace.stat().st_size,
                limitation=('A missing, multiply observed or snapshot-visible foreign owner fails closed; '
                            'a transient foreign same-comm task absent from both /proc snapshots cannot be excluded'))
    encoded=(json.dumps(mapping,sort_keys=True,indent=2)+'\n').encode()
    (output/'pid-mapping-status.json').write_bytes(encoded)
    return mapping


def preflight(owners=None,expected_boot=None):
    require(sys.platform=='linux','Requires WSL/Linux')
    result=dict(read_only=True,boot_id=boot(),instance_creation_not_tested=True,
        tracefs=str(TRACE),instances_available=(TRACE/'instances').is_dir(),
        clock_choices=(TRACE/'trace_clock').read_text().strip(),
        global_controls={n:(TRACE/n).read_text().strip() for n in ('tracing_on','current_tracer','trace_clock')},
        event_formats={e:(TRACE/'events'/e/'format').read_text() for e in EVENTS})
    require(result['instances_available'] and 'mono' in result['clock_choices'].replace('[','').replace(']','').split(),
            'Private instance/mono clock unavailable')
    if owners:
        result['verified_owners']=verify(owners,expected_boot)
        result['filters_pending_kernel_mapping']=True
    return result


def guarded_instance(path,expected_inode):
    parent=(TRACE/'instances').resolve(strict=True)
    require(not path.is_symlink() and path.resolve(strict=True).parent==parent
            and re.fullmatch('wksim-rate-[0-9a-f]{32}',path.name),'Refuse foreign/global tracefs path')
    stat=path.stat()
    require((stat.st_dev,stat.st_ino)==expected_inode,'Private instance identity changed')


def statistics(instance):
    raw={p.parent.name:p.read_text() for p in sorted((instance/'per_cpu').glob('cpu*/stats'))}
    counts={}
    for cpu,text in raw.items():
        fields={k.strip():v.strip() for line in text.splitlines() if ':' in line for k,v in [line.split(':',1)]}
        counts[cpu]={key:int(fields[key]) if key in fields else None for key in LOSS}
    return dict(raw=raw,loss_counts=counts)


def emit_capture_active(path,metadata):
    """Publish one exclusive, fully-written token after tracing is enabled."""
    target=Path(path)
    if target.exists():
        raise FileExistsError(str(target))
    owner_path=target.parent/'instance-owner.json'
    owner_raw=owner_path.read_bytes()
    owner=json.loads(owner_raw)
    require(isinstance(owner,dict) and owner.get('schema')=='wksim.private-tracefs.instance-owner.v1',
            'Capture instance owner proof is invalid')
    owner_sha256=hashlib.sha256(owner_raw).hexdigest()
    supervisor=metadata['owners']['supervisor']
    payload=dict(schema='wksim.private-tracefs.capture-active.v1',state='active',
                 collector_pid=os.getpid(),collector_start_ticks=metadata['collector_start_ticks'],
                 supervisor_pid=supervisor['pid'],supervisor_start_ticks=supervisor['start_ticks'],
                 instance_owner_sha256=owner_sha256,instance=metadata['instance'],
                 instance_inode=metadata['instance_inode'],run_id=metadata['run_id'],
                 epoch=metadata['epoch'],started_monotonic_ns=metadata['started_monotonic_ns'],
                 published_monotonic_ns=time.monotonic_ns())
    raw=(json.dumps(payload,sort_keys=True,indent=2)+'\n').encode()
    descriptor=None
    temporary=None
    try:
        descriptor,temporary=tempfile.mkstemp(prefix='.'+target.name+'-',suffix='.tmp',dir=target.parent)
        offset=0
        while offset<len(raw):
            offset += os.write(descriptor,raw[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor=None
        if target.exists():
            raise FileExistsError(str(target))
        # A hard-link publication is atomic and create-only: unlike replace,
        # it cannot overwrite a token created in the check-to-publish window.
        os.link(temporary,target)
        Path(temporary).unlink()
        temporary=None
    except BaseException:
        if descriptor is not None:
            try:os.close(descriptor)
            except OSError:pass
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        raise
    metadata['capture_active_token']=str(target)
    metadata['capture_active']=payload
    return payload


def enable_capture(put,duration,metadata,active_token):
    # Includes the complete enabling write, never a post-enable underestimate.
    began=time.monotonic_ns()
    metadata['started_monotonic_ns']=began
    metadata['started_realtime_ns']=time.time_ns()
    metadata['window_semantics']='before enable write through completed disable write'
    put('tracing_on','1')
    emit_capture_active(active_token,metadata)
    return began,began+int(duration*1e9)


def finalize_capture(path,inode,descriptor,metadata,output,before,owners,expected_boot,handlers,cancelled,began,stopped):
    def attempt(label,action):
        try:return action()
        except BaseException as error:
            metadata['errors'].append(label+': '+type(error).__name__+': '+str(error))
            return None
    try:
        if inode is not None:
            def disable():
                guarded_instance(path,inode)
                (path/'tracing_on').write_text('0\n')
                return time.monotonic_ns()
            final_stop=attempt('Disable',disable)
            stopped=stopped or final_stop
            measured=attempt('Statistics',lambda:statistics(path))
            if measured is not None:metadata['stats_after']=measured
        if descriptor is not None:attempt('Trace fd close',lambda:os.close(descriptor))
        def after_owners():
            metadata['owners_after']=verify(owners,expected_boot)
            metadata['fd_after']={n:fds(v['pid']) for n,v in metadata['owners_after'].items()}
        attempt('Owners after',after_owners)
    finally:
        try:
            # Every prior post-processing failure still reaches own rmdir.
            if inode is not None:
                def remove():
                    guarded_instance(path,inode)
                    path.rmdir()
                    return True
                metadata['instance_removed']=attempt('Owned instance removal',remove) is True
            metadata['stopped_monotonic_ns']=stopped
            began=began if began is not None else metadata.get('started_monotonic_ns')
            metadata['elapsed_s']=(stopped-began)/1e9 if began is not None and stopped is not None else None
            metadata['signals']=cancelled
            controls=attempt('Global controls read',lambda:{n:(TRACE/n).read_text().strip() for n in ('tracing_on','current_tracer','trace_clock')})
            metadata['global_controls_after']=controls
            metadata['global_controls_unchanged']=controls==before['global_controls']
            def trace_hash():
                raw=output/'trace.txt'
                if raw.exists():
                    metadata['trace_sha256']=hashlib.sha256(raw.read_bytes()).hexdigest()
                    metadata['trace_bytes']=raw.stat().st_size
            attempt('Trace evidence hash',trace_hash)
            loss=metadata.get('stats_after',{}).get('loss_counts',{})
            metadata['loss_free']=bool(loss) and all(v==0 for c in loss.values() for v in c.values())
            metadata['duration_cap_met']=metadata['elapsed_s'] is not None and metadata['elapsed_s']<=20
            metadata['events_observed']=metadata.get('trace_bytes',0)>0
            metadata['complete']=not metadata['errors'] and not cancelled and metadata.get('instance_removed',False) and metadata['loss_free'] and metadata['duration_cap_met'] and metadata['global_controls_unchanged'] and metadata['events_observed']
            metadata['status']='diagnostic_window_captured' if metadata['complete'] else 'diagnostic_partial'
        finally:
            try:
                with (output/'metadata.json').open('x') as stream:json.dump(metadata,stream,indent=2)
            finally:
                # SIGINT/SIGTERM handlers stay installed through disable, all
                # post-processing, rmdir and metadata persistence.
                for signum,previous in handlers.items():
                    attempt('Restore signal handler',lambda s=signum,p=previous:signal.signal(s,p))


def collect(args,owners):
    require(os.geteuid()==0,'Capture requires root')
    before=preflight(owners,args.boot_id)
    verify_roles(before['verified_owners'],args.run_id,args.epoch)
    output=args.output.resolve()
    require(args.output.is_absolute() and not output.exists(),'Use a new absolute output directory')
    require(not any(output.is_relative_to(Path(p)) for p in ('/sys','/proc','/dev')),'Output cannot be a control filesystem')
    output.mkdir(mode=0o700)
    active_token=(args.capture_active_token or output/'capture-active.json').resolve()
    require(active_token.parent==output and not active_token.exists(),
            'Capture-active token must be a new file inside output')
    path=TRACE/'instances'/('wksim-rate-'+uuid.uuid4().hex)
    collector_identity=identity(os.getpid())
    metadata=dict(schema='wksim.private-tracefs.v1',run_id=args.run_id,epoch=args.epoch,
        acceptance_eligible=False,requested_duration_s=args.duration,preflight=before,
        owners=owners,command=sys.argv,instance=str(path),errors=[],status='diagnostic_partial',
        collector_pid=collector_identity['pid'],collector_start_ticks=collector_identity['start_ticks'],
        boundary_syscalls_may_be_unpaired=True)
    (output/'preflight.json').write_text(json.dumps(before,indent=2)+'\n')
    inode=None; descriptor=None; stopped=None; began=None
    cancelled=[]
    handlers={}
    try:
        def interrupt(signum,frame):cancelled.append(signum)
        for signum in (signal.SIGINT,signal.SIGTERM):
            handlers[signum]=signal.signal(signum,interrupt)
        # mkdir is exclusive. If it fails, this process does not own this path.
        path.mkdir()
        stat=path.stat();inode=(stat.st_dev,stat.st_ino)
        metadata['instance_inode']=list(inode)
        owner_proof=verify(owners,args.boot_id)
        with (output/'instance-owner.json').open('x') as stream:
            json.dump(dict(schema='wksim.private-tracefs.instance-owner.v1',instance=str(path),
                           instance_inode=list(inode),collector_pid=collector_identity['pid'],
                           collector_start_ticks=collector_identity['start_ticks'],
                           supervisor_pid=owners['supervisor']['pid'],
                           supervisor_start_ticks=owners['supervisor']['start_ticks'],
                           owners=owner_proof,boot_id=args.boot_id,run_id=args.run_id,epoch=args.epoch),
                      stream,indent=2,sort_keys=True)
        guarded_instance(path,inode)
        def put(relative,value):
            guarded_instance(path,inode)
            target=path/relative
            require(target.resolve(strict=True).is_relative_to(path.resolve()),'Escaping instance control')
            target.write_text(value+'\n')
        put('tracing_on','0')
        put('current_tracer','nop')
        put('events/enable','0')
        put('trace_clock','mono')
        put('buffer_size_kb','1024')
        require('[mono]' in (path/'trace_clock').read_text(),'Instance mono clock not selected')
        require(args.map_comm,'Capture requires namespace-verified --map-comm')
        mapping=map_kernel_pids(path,put,owners,args.epoch,output)
        metadata['pid_mapping']=mapping
        applied=filters(mapping['kernel_pids'])
        for event,expression in applied.items():
            put('events/'+event+'/filter',expression)
            put('events/'+event+'/enable','1')
        metadata['applied_filters']={e:(path/'events'/e/'filter').read_text() for e in applied}
        metadata['fd_before']={name:fds(value['pid']) for name,value in verify(owners,args.boot_id).items()}
        metadata['stats_before']=statistics(path)
        descriptor=os.open(path/'trace_pipe',TRACE_PIPE_FLAGS)
        with (output/'trace.txt').open('xb') as destination:
            began,deadline=enable_capture(put,args.duration,metadata,active_token)
            while time.monotonic_ns()<deadline and not cancelled:
                verify(owners,args.boot_id)
                timeout=min(.05,max(0,(deadline-time.monotonic_ns())/1e9))
                if select.select([descriptor],[],[],timeout)[0]:
                    try: destination.write(os.read(descriptor,1024*1024))
                    except BlockingIOError: pass
            put('tracing_on','0')
            stopped=time.monotonic_ns()
            metadata['stop_reason']='signal' if cancelled else 'duration'
            # No new events once disabled. Drain only this owned instance.
            while True:
                try: chunk=os.read(descriptor,1024*1024)
                except BlockingIOError: break
                if not chunk:break
                destination.write(chunk)
    except BaseException as error:
        metadata['errors'].append(type(error).__name__+': '+str(error))
    finally:
        finalize_capture(path,inode,descriptor,metadata,output,before,owners,args.boot_id,handlers,cancelled,began,stopped)
    return metadata


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',action='store_true',help='Read-only availability; also identity checks if all owners supplied')
    parser.add_argument('--ap-worker',type=owner,metavar='PID:START_TICKS')
    parser.add_argument('--px4-worker',type=owner,metavar='PID:START_TICKS')
    parser.add_argument('--supervisor',type=owner,metavar='PID:START_TICKS')
    parser.add_argument('--ap-fc',type=owner,metavar='PID:START_TICKS')
    parser.add_argument('--px4-fc',type=owner,metavar='PID:START_TICKS')
    parser.add_argument('--boot-id')
    parser.add_argument('--run-id')
    parser.add_argument('--epoch')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--capture-active-token',type=Path)
    parser.add_argument('--duration',type=float,default=10.)
    parser.add_argument('--map-comm',action='store_true',help='Map exact per-run diagnostic comm names to kernel tracepoint IDs')
    args=parser.parse_args()
    require(0<args.duration<=20,'Duration must be >0 and <=20 seconds')
    owner_roles=BASE_ROLES+tuple(FC_THREADS)
    owners={n:getattr(args,n) for n in owner_roles if getattr(args,n) is not None}
    if owners or not args.preflight:
        shape=tuple(owners)==BASE_ROLES or tuple(owners)==owner_roles
        require(shape and len({v['pid'] for v in owners.values()})==len(owners) and args.boot_id,
                'Supply three base or five full distinct owned identities and boot-id')
    if args.preflight:
        value=preflight(owners,args.boot_id)
        if owners and args.run_id and args.epoch:verify_roles(value['verified_owners'],args.run_id,args.epoch)
        print(json.dumps(value,indent=2));return 0
    require(args.output is not None and args.run_id and args.epoch and re.fullmatch('[0-9a-f]{32}',args.epoch),'Capture needs output/run-id/32hex epoch')
    result=collect(args,owners)
    print(json.dumps({k:result.get(k) for k in ('status','complete','elapsed_s','instance_removed','errors')}))
    return 0 if result['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
