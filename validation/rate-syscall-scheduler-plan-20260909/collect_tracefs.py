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
    """Return stable, namespace-bound task identities for one owned process.

    Each row binds BOTH namespace views of one thread, read from
    ``/proc/<tgid>/task/<tid>/status``: ``local_tid`` is the innermost
    (namespace-local) tid -- the ``NSpid`` chain's last entry -- and ``global_tid``
    is the outermost (root-namespace) entry ``NSpid[0]``, which is the ID the
    kernel ``sched_switch`` tracepoint reports.  The ``/proc`` task directory name
    is the namespace-local id, so it must equal ``local_tid`` (``NSpid[-1]``), and
    ``Tgid`` must equal the owned pid.  A missing or empty ``NSpid`` line, a
    non-positive id, a chain whose namespace depth differs between threads of the
    same process, or a directory name that does not match ``NSpid[-1]`` (a
    global/local swap) all fail closed.  This is the namespace-mismatch guard the
    one real diagnostic exposed (Ubuntu/local pid 601 vs kernel/global pid 1015).
    """
    root=Path('/proc')/str(pid)/'task'
    result=[]
    chain_depth=None
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
        nspid=re.search(r'^NSpid:[ \t]*(\d+(?:[ \t]+\d+)*)[ \t]*$',status,re.MULTILINE)
        require(len(before_fields)>19 and len(after_fields)>19 and tgid is not None
                and int(tgid.group(1))==pid,
                'Task does not belong to owned process: '+path.name)
        require(nspid is not None,'Task NSpid chain is missing: '+path.name)
        chain=[int(value) for value in nspid.group(1).split()]
        require(chain and all(value>0 for value in chain),
                'Task NSpid chain is malformed: '+path.name)
        if chain_depth is None:
            chain_depth=len(chain)
        require(len(chain)==chain_depth,'Task NSpid chain mismatch: '+path.name)
        global_tid=chain[0];local_tid=chain[-1]
        require(local_tid==int(path.name),
                'Task NSpid global/local confusion: '+path.name)
        comm=(path/'comm').read_text().strip()
        require(before_comm==after_comm==comm and before_fields[19]==after_fields[19],
                'Task identity changed during inventory: '+path.name)
        result.append(dict(local_tid=local_tid,global_tid=global_tid,comm=comm,
                           start_ticks=int(before_fields[19])))
    require(result,'Owned process has no tasks: '+str(pid))
    require(len({row['global_tid'] for row in result})==len(result),
            'Task global NSpid identities are not distinct: '+str(pid))
    return result


def select_leader(rows,owner_pid,comm):
    """Return ``(leader, same_comm_others)`` for one owned process and exact comm.

    The leader (main) thread of a process has a namespace-local tid equal to the
    owned pid, so requiring ``local_tid == owner_pid`` together with the exact
    comm pins the leader precisely.  Other threads that happen to share the comm
    (for example helper threads that inherited the diagnostic name) do NOT make
    the target ambiguous -- they are returned as evidence (``same_comm_others``)
    instead of failing the selection.  The selection fails closed when no row is
    both the leader and an exact comm match, or when more than one leader row
    matches.
    """
    rows=list(rows)
    leaders=[row for row in rows
             if row.get('local_tid')==owner_pid and row.get('comm')==comm]
    require(len(leaders)==1,'Leader thread absent/ambiguous for comm: '+comm)
    leader=leaders[0]
    others=[row for row in rows
            if row.get('comm')==comm and row.get('local_tid')!=leader.get('local_tid')]
    return leader,others


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


def _fc_thread_probe(owners):
    """Return the FC inventory without turning startup absence into a fault."""
    selected={}
    inventories={}
    missing=[]
    ambiguous=[]
    for role,names in FC_THREADS.items():
        try:
            rows=task_inventory(owners[role]['pid'])
        except (FileNotFoundError,NotADirectoryError,PermissionError):
            missing.extend(role+'/'+name for name in names)
            continue
        inventories[role]=rows
        for name in names:
            matches=[row for row in rows if row['comm']==name]
            if len(matches)==1:
                selected[role+'/'+name]=matches[0]
            elif not matches:
                missing.append(role+'/'+name)
            else:
                ambiguous.append(role+'/'+name)
    return selected,inventories,missing,ambiguous


def wait_required_fc_threads(owners,timeout=None):
    """Wait for FC tasks to exist, but fail immediately on duplicate ownership."""
    timeout=FC_THREAD_TIMEOUT_S if timeout is None else timeout
    deadline=time.monotonic()+timeout
    missing=[]
    while time.monotonic()<deadline:
        selected,inventories,missing,ambiguous=_fc_thread_probe(owners)
        require(not ambiguous,'Required FC thread ownership ambiguous: '+','.join(ambiguous))
        if not missing:
            selected,inventories=required_fc_threads(owners)
            return selected,inventories
        time.sleep(MAPPING_SELECT_S)
    raise TimeoutError('Required FC thread inventory timed out: '+','.join(missing))


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
FC_THREAD_TIMEOUT_S=15.
BOOTSTRAP_SCHEMA='wksim.private-tracefs.capture-bootstrap-active.v1'
ACTIVE_SCHEMA='wksim.private-tracefs.capture-active.v1'


def _sched_switch_pairs(line):
    """Return exact comm/PID pairs from one textual sched_switch event."""
    pairs=[]
    for match in re.finditer(
            r'prev_comm=(\S+)\s+prev_pid=(\d+)|next_comm=(\S+)\s+next_pid=(\d+)',line):
        pairs.append((match.group(1) or match.group(3),match.group(2) or match.group(4)))
    return pairs


def scan_global_comm_owners(expected,proc_root=None,*,allow_foreign=False):
    """Require every target comm's pinned owner task to be present in /proc.

    Strict mode (``allow_foreign=False``, the default) keeps the historical guard:
    each target comm must be owned by EXACTLY the expected local task, and any
    other same-comm task is a foreign owner that fails closed.  With
    ``allow_foreign=True`` the pinned owner (``tgid``, ``tid`` == the leader's
    namespace-local identity) must still be present, but ADDITIONAL same-comm
    tasks -- for example helper threads that inherited the name before the leader
    was renamed -- are recorded in the returned ``foreign`` evidence list instead
    of failing, because the leader has already been pinned by
    ``local_tid == owner pid``.  A collection may be supplied to allow this only
    for selected comm names; this keeps fixed FC thread names strict.  A comm whose
    pinned owner is ABSENT fails closed in every mode.
    """
    require(expected and len(expected)==len(set(expected)),'Expected comm names are not distinct')
    if allow_foreign is True:
        allowed_foreign=set(expected)
    elif allow_foreign in (False,None):
        allowed_foreign=set()
    else:
        allowed_foreign=set(allow_foreign)
        require(allowed_foreign<=set(expected),'Unknown foreign-owner comm allowance')
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
        absent=[];foreign=[];last_missing=[]
        for name,owner in expected.items():
            values=matches[name]
            if not values:last_missing.append(name)
            pinned=dict(tgid=owner['tgid'],tid=owner['tid'])
            if pinned not in values:
                absent.append(dict(comm=name,expected=owner,observed=values))
            else:
                extra=[value for value in values if value!=pinned]
                if extra:
                    foreign.append(dict(comm=name,expected=owner,observed=extra))
        if not absent:
            forbidden=[row for row in foreign if row['comm'] not in allowed_foreign]
            if forbidden:
                raise ValueError('Global comm ownership mismatch: '+json.dumps(forbidden,sort_keys=True))
            return dict(matches=matches,foreign=foreign,scan_attempts=attempt+1,ignored_races=races)
        only_missing=all(not row['observed'] for row in absent)
        if not (attempt==0 and only_missing and races):
            raise ValueError('Global comm ownership mismatch: '+json.dumps(absent,sort_keys=True))
    raise ValueError('Global comm ownership missing after retry: '+','.join(last_missing))


def map_sched_switch_pids(instance,put,names,output,*,retain=False,expected=None,evidence=None):
    """Map exact comm names using a bounded private sched_switch window.

    The tracepoint PID fields are the only source of kernel-visible IDs, and they
    are ROOT-namespace (global) pids.  With no ``expected`` (the default) the
    mapping accepts one and only one PID for each exact comm; a second PID is an
    ambiguity and a missing name at the deadline fails closed.  When a role is
    pinned in ``expected`` (role -> the leader's ``global_tid`` == NSpid[0]), only
    that global pid is accepted as the target; any other same-comm pid (for
    example a helper thread that inherited the diagnostic name) does NOT make the
    target ambiguous -- it is appended to ``evidence`` (when given) instead.  A
    pinned leader that is never observed still fails closed at the deadline.
    Polling trace_pipe makes the window event-driven instead of sleeping for a
    fixed warm-up interval.
    """
    require(len(set(names.values()))==len(names),'Trace comm names are not distinct')
    expected={} if expected is None else dict(expected)
    expression=' || '.join(
        f'prev_comm == "{name}" || next_comm == "{name}"'
        for name in names.values())
    candidates={role:set() for role in names}
    comm_to_role={name:role for role,name in names.items()}
    raw=bytearray()
    descriptor=None
    pending=b''
    primary=None
    foreign_seen=set()
    def observe(text):
        for comm,pid_text in _sched_switch_pairs(text):
            role=comm_to_role.get(comm)
            if role is None:
                continue
            pid=int(pid_text)
            if role in expected:
                if pid==expected[role]:
                    candidates[role].add(pid)
                elif evidence is not None:
                    key=(role,comm,pid)
                    if key not in foreign_seen:
                        foreign_seen.add(key)
                        evidence.append(dict(role=role,comm=comm,kernel_pid=pid))
            else:
                candidates[role].add(pid)
                require(len(candidates[role])==1,
                        'Kernel PID mapping ambiguous: '+role)
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
                observe(line.decode(errors='replace'))
        if pending.strip():
            observe(pending.decode(errors='replace'))
        missing=[role for role,values in candidates.items() if len(values)!=1]
        require(not missing,'Kernel PID mapping timed out: '+','.join(missing))
    except BaseException as error:
        primary=error
    finally:
        cleanup_errors=[]
        if not retain:
            for relative,value in (('tracing_on','0'),
                                   ('events/sched/sched_switch/enable','0')):
                try:put(relative,value)
                except BaseException as error:cleanup_errors.append(relative+': '+str(error))
        if descriptor is not None:
            try:os.close(descriptor)
            except BaseException as error:cleanup_errors.append('trace_pipe close: '+str(error))
        try:(output/'pid-mapping-trace.txt').write_bytes(bytes(raw))
        except BaseException as error:cleanup_errors.append('mapping trace write: '+str(error))
        if not retain:
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


def map_kernel_pids(instance,put,owners,epoch,output,*,retain=False):
    """Correlate exact owned comm names while consuming bootstrap trace immediately.

    FC tasks may appear after the supervisor publishes the bootstrap token.  The
    scheduler window therefore starts with all expected comm names, and the
    local task inventory is sealed only after the event-driven trace drain has
    observed every name.  This prevents the 1 MiB private ring from filling
    while startup ownership is still converging.
    """
    names={role:'wk'+epoch[:11]+suffix for role,suffix in (
        ('ap_worker','a'),('px4_worker','p'),('supervisor','s'))}
    for role,name in names.items():
        require((Path('/proc')/str(owners[role]['pid'])/'comm').read_text().strip()==name,
                'Diagnostic comm name missing or wrong: '+role)
    if 'ap_fc' in owners:
        for fc_role,comms in FC_THREADS.items():
            for comm in comms:
                names[fc_role+'/'+comm]=comm
    require(len(set(names.values()))==len(names),'Trace comm names are not distinct')
    # Pin each base-role leader thread (local_tid == owner pid, exact comm) and bind
    # its root-namespace tid.  Other threads sharing the diagnostic comm (e.g.
    # helper threads named before the leader was renamed) are recorded as evidence,
    # NOT treated as an ambiguity, because the leader is pinned by local_tid.
    base_leaders={}
    same_comm_threads={}
    for role in BASE_ROLES:
        leader,others=select_leader(task_inventory(owners[role]['pid']),
                                    owners[role]['pid'],names[role])
        base_leaders[role]=leader
        if others:
            same_comm_threads[role]=others
    expected_base={name:dict(role=role,tgid=owners[role]['pid'],
                             tid=base_leaders[role]['local_tid'])
                   for role,name in names.items() if role in BASE_ROLES}
    comm_owners_before=scan_global_comm_owners(expected_base,allow_foreign=True)
    sched_switch_same_comm=[]
    mapped=map_sched_switch_pids(instance,put,names,output,retain=retain,
                                 expected={role:base_leaders[role]['global_tid'] for role in BASE_ROLES},
                                 evidence=sched_switch_same_comm)
    require(len(set(mapped.values()))==len(mapped),'Kernel PID mappings are not distinct')
    # sched_switch reports the root-namespace (global) pid; bind it to the pinned
    # leader's NSpid[0], never the namespace-local id (the WSL diagnostic split).
    # The pinned-expected mapping above already selects it; this re-check is the
    # fail-closed guard against a global/local swap (and holds even if the mapping
    # were produced without the leader pins).
    for role in BASE_ROLES:
        require(mapped.get(role)==base_leaders[role]['global_tid'],
                'Kernel/global leader identity differs: '+role)
    local_threads,inventories_after=wait_required_fc_threads(owners) if 'ap_fc' in owners else ({},{})
    for role,thread in local_threads.items():
        require(mapped.get(role)==thread['global_tid'],
                'Kernel/global FC thread identity differs: '+role)
    expected={name:dict(role=role,tgid=(owners[role]['pid'] if role in BASE_ROLES else
        owners[role.split('/')[0]]['pid']),tid=(base_leaders[role]['local_tid'] if role in BASE_ROLES else
        local_threads[role]['local_tid'])) for role,name in names.items()}
    comm_owners_after=scan_global_comm_owners(
        expected,allow_foreign={names[role] for role in BASE_ROLES})
    mapping_trace=output/'pid-mapping-trace.txt'
    mapping_sha256=hashlib.sha256(mapping_trace.read_bytes()).hexdigest()
    mapping=dict(names=names,kernel_pids=mapped,
                base_leaders=base_leaders,same_comm_threads=same_comm_threads,
                sched_switch_same_comm=sched_switch_same_comm,
                local_threads=local_threads,inventories_before=inventories_after,
                inventories_after=inventories_after,
                comm_owners_before=comm_owners_before,comm_owners_after=comm_owners_after,
                method='owned exact comm names observed in a bounded private sched_switch window',
                mapping_source='private_sched_switch',
                mapping_timeout_s=MAPPING_TIMEOUT_S,
                mapping_sha256=mapping_sha256,
                mapping_trace_bytes=mapping_trace.stat().st_size,
                limitation=('A missing pinned leader, a snapshot-absent pinned owner, or a kernel/global '
                            'pid that does not match the leader NSpid[0] fails closed; a foreign '
                            'same-comm thread/PID is recorded as evidence once the leader is pinned by '
                            'local_tid == owner pid; a transient foreign same-comm task absent from both '
                            '/proc snapshots cannot be excluded'))
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


def loss_counter_delta(before,after):
    """Return comparable loss counters and whether bootstrap stayed loss-free."""
    before_counts=before.get('loss_counts',{}) if isinstance(before,dict) else {}
    after_counts=after.get('loss_counts',{}) if isinstance(after,dict) else {}
    cpus=sorted(set(before_counts)|set(after_counts))
    delta={}
    loss_free=True
    for cpu in cpus:
        old=before_counts.get(cpu,{})
        new=after_counts.get(cpu,{})
        fields=sorted(set(old)|set(new))
        delta[cpu]={}
        for field in fields:
            old_value=old.get(field)
            new_value=new.get(field)
            delta[cpu][field]=None if old_value is None or new_value is None else new_value-old_value
            if (old_value is None or new_value is None or new_value != old_value
                    or old_value != 0 or new_value != 0):
                loss_free=False
    return delta,loss_free


def _emit_capture_token(path,metadata,*,schema,state,phase,started_monotonic_ns=None):
    """Publish one exclusive, fully-written token after a trace boundary."""
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
    started = (metadata.get('started_monotonic_ns')
               if started_monotonic_ns is None else started_monotonic_ns)
    require(type(started) is int and started>0,
            'Capture token start timestamp is invalid')
    payload=dict(schema=schema,state=state,phase=phase,
                 collector_pid=os.getpid(),collector_start_ticks=metadata['collector_start_ticks'],
                 supervisor_pid=supervisor['pid'],supervisor_start_ticks=supervisor['start_ticks'],
                 instance_owner_sha256=owner_sha256,instance=metadata['instance'],
                 instance_inode=metadata['instance_inode'],run_id=metadata['run_id'],
                 epoch=metadata['epoch'],started_monotonic_ns=started,
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


def emit_capture_active(path,metadata):
    """Publish the filtered capture token after all precise filters are enabled."""
    return _emit_capture_token(path,metadata,schema=ACTIVE_SCHEMA,state='active',phase='filtered')


def emit_capture_bootstrap(path,metadata):
    """Publish a distinct sched_switch-only token used solely by the tick-zero gate."""
    payload=_emit_capture_token(path,metadata,schema=BOOTSTRAP_SCHEMA,
                                state='bootstrap_active',phase='bootstrap_sched_switch',
                                started_monotonic_ns=metadata.get('bootstrap_started_monotonic_ns'))
    metadata['capture_bootstrap_token']=str(path)
    metadata['capture_bootstrap']=payload
    return payload


def wait_gate_release(path,bootstrap,owners,run_id,epoch,timeout=FC_THREAD_TIMEOUT_S):
    """Require the gate to release exactly this bootstrap token before mapping."""
    path=Path(path)
    if not path:
        raise ValueError('Gate-release path is required for bootstrap capture')
    token_sha256=hashlib.sha256(
        (Path(bootstrap['token_path']).read_bytes() if bootstrap.get('token_path')
         else b'')).hexdigest() if bootstrap.get('token_path') else bootstrap.get('sha256')
    expected_sha=bootstrap.get('sha256') or token_sha256
    gate_ready_path=path.with_name('gate-ready.json')
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if path.exists():
            value=json.loads(path.read_bytes())
            owner=owners['supervisor']
            observed_sha=value.get('capture_token_sha256',value.get('capture_active_sha256'))
            require(isinstance(value,dict) and value.get('schema')=='wksim.private-tracefs.capture-release.v1'
                    and value.get('state')=='released' and value.get('run_id')==run_id
                    and value.get('epoch')==epoch and value.get('tick')==0
                    and value.get('supervisor_pid')==owner['pid']
                    and value.get('supervisor_start_ticks')==owner['start_ticks']
                    and value.get('capture_token_schema')==BOOTSTRAP_SCHEMA
                    and observed_sha==expected_sha
                    and value.get('instance')==bootstrap.get('instance')
                    and value.get('instance_inode')==bootstrap.get('instance_inode')
                    and value.get('instance_owner_sha256')==bootstrap.get('instance_owner_sha256')
                    and value.get('collector_pid')==bootstrap.get('collector_pid')
                    and value.get('collector_start_ticks')==bootstrap.get('collector_start_ticks')
                    and type(value.get('capture_token_published_monotonic_ns')) is int
                    and value.get('capture_token_published_monotonic_ns')==bootstrap.get('published_monotonic_ns')
                    and type(value.get('released_monotonic_ns')) is int
                    and value.get('released_monotonic_ns')>=bootstrap.get('published_monotonic_ns')
                    and value.get('gate_ready_sha256')==hashlib.sha256(gate_ready_path.read_bytes()).hexdigest(),
                    'Bootstrap gate-release binding differs')
            return value
        time.sleep(MAPPING_SELECT_S)
    raise TimeoutError('Bootstrap gate release was not published')


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
    bootstrap_token=(args.capture_bootstrap_token or output/'capture-bootstrap-active.json').resolve()
    require(active_token.parent==output and not active_token.exists(),
            'Capture-active token must be a new file inside output')
    require(bootstrap_token.parent==output and not bootstrap_token.exists()
            and bootstrap_token!=active_token,
            'Capture-bootstrap token must be a distinct new file inside output')
    path=TRACE/'instances'/('wksim-rate-'+uuid.uuid4().hex)
    collector_identity=identity(os.getpid())
    metadata=dict(schema='wksim.private-tracefs.v1',run_id=args.run_id,epoch=args.epoch,
        acceptance_eligible=False,requested_duration_s=args.duration,preflight=before,
        owners=owners,command=sys.argv,instance=str(path),errors=[],status='diagnostic_partial',
        collector_pid=collector_identity['pid'],collector_start_ticks=collector_identity['start_ticks'],
        boundary_syscalls_may_be_unpaired=True,
        bootstrap_token=str(bootstrap_token),filtered_token=str(active_token),
        capture_boundaries={})
    (output/'preflight.json').write_text(json.dumps(before,indent=2)+'\n')
    inode=None; descriptor=None; destination=None; stopped=None; began=None
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
        bootstrap_started=time.monotonic_ns()
        metadata['bootstrap_started_monotonic_ns']=bootstrap_started
        metadata['bootstrap_semantics']='sched_switch-only retained window before precise filters'
        metadata['capture_boundaries']['bootstrap_raw_retained']=False
        metadata['bootstrap_stats_before']=statistics(path)
        put('events/sched/sched_switch/filter',' || '.join(
            f'prev_comm == "{name}" || next_comm == "{name}"'
            for name in ('wk'+args.epoch[:11]+'a','wk'+args.epoch[:11]+'p','wk'+args.epoch[:11]+'s')))
        put('events/sched/sched_switch/enable','1')
        put('tracing_on','1')
        bootstrap_payload=emit_capture_bootstrap(bootstrap_token,metadata)
        bootstrap_sha256=hashlib.sha256(bootstrap_token.read_bytes()).hexdigest()
        metadata['capture_boundaries']['bootstrap_token_sha256']=bootstrap_sha256
        metadata['capture_boundaries']['bootstrap_published_monotonic_ns']=bootstrap_payload['published_monotonic_ns']
        gate_release=wait_gate_release(args.capture_gate_release,dict(
            bootstrap_payload,sha256=bootstrap_sha256),owners,
            args.run_id,args.epoch)
        metadata['gate_release']=gate_release
        metadata['capture_boundaries']['gate_release_monotonic_ns']=gate_release.get('released_monotonic_ns')
        mapping=map_kernel_pids(path,put,owners,args.epoch,output,retain=True)
        metadata['pid_mapping']=mapping
        bootstrap_trace=output/'pid-mapping-trace.txt'
        bootstrap_raw=bootstrap_trace.read_bytes()
        metadata['bootstrap_stats_after']=statistics(path)
        delta,loss_free=loss_counter_delta(metadata['bootstrap_stats_before'],
                                            metadata['bootstrap_stats_after'])
        metadata['bootstrap_loss_delta']=delta
        metadata['bootstrap_loss_free']=loss_free
        metadata['bootstrap_trace']=dict(path=str(bootstrap_trace),bytes=len(bootstrap_raw),
            sha256=hashlib.sha256(bootstrap_raw).hexdigest())
        require(loss_free,'Bootstrap trace buffer loss detected; refusing retained capture')
        trace_path=output/'trace.txt'
        destination=trace_path.open('xb')
        destination.write(bootstrap_raw)
        trace_boundary_bytes=0
        if bootstrap_raw and not bootstrap_raw.endswith(b'\n'):
            destination.write(b'\n')
            trace_boundary_bytes=1
        destination.flush()
        metadata['trace_sections']={'bootstrap':dict(offset=0,bytes=len(bootstrap_raw),
            sha256=hashlib.sha256(bootstrap_raw).hexdigest()),
            'boundary_bytes':trace_boundary_bytes}
        metadata['capture_boundaries']['filtered_transition_monotonic_ns']=time.monotonic_ns()
        metadata['capture_boundaries']['bootstrap_raw_retained']=True
        applied=filters(mapping['kernel_pids'])
        for event,expression in applied.items():
            put('events/'+event+'/filter',expression)
            put('events/'+event+'/enable','1')
        metadata['applied_filters']={e:(path/'events'/e/'filter').read_text() for e in applied}
        metadata['fd_before']={name:fds(value['pid']) for name,value in verify(owners,args.boot_id).items()}
        metadata['stats_before']=statistics(path)
        descriptor=os.open(path/'trace_pipe',TRACE_PIPE_FLAGS)
        began,deadline=enable_capture(put,args.duration,metadata,active_token)
        metadata['capture_boundaries']['filtered_token_sha256']=hashlib.sha256(active_token.read_bytes()).hexdigest()
        metadata['capture_boundaries']['filtered_published_monotonic_ns']=metadata['capture_active']['published_monotonic_ns']
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
        destination.flush()
        filtered_offset=(metadata['trace_sections']['bootstrap']['bytes']
                         +metadata['trace_sections']['boundary_bytes'])
        filtered_bytes=destination.tell()-filtered_offset
        metadata['trace_sections']['filtered']=dict(offset=filtered_offset,bytes=filtered_bytes)
    except BaseException as error:
        metadata['errors'].append(type(error).__name__+': '+str(error))
    finally:
        if destination is not None:
            try: destination.close()
            except BaseException as error: metadata['errors'].append('Trace output close: '+str(error))
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
    parser.add_argument('--capture-bootstrap-token',type=Path)
    parser.add_argument('--capture-gate-release',type=Path,required=False)
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
    require(args.capture_gate_release is not None,'Capture needs --capture-gate-release')
    result=collect(args,owners)
    print(json.dumps({k:result.get(k) for k in ('status','complete','elapsed_s','instance_removed','errors')}))
    return 0 if result['complete'] else 1


if __name__=='__main__':raise SystemExit(main())
