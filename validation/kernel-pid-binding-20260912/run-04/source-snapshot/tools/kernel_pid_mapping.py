"""Bind owned procfs task lifetimes to namespace-filtered kernel BPF records.

Procfs NSpid[0] is never used as a kernel ID. All kernel IDs come from the two
PID helpers on the same task. A record must postdate the END of the procfs
start-time tick, excluding stale entries even after local PID reuse in that tick.
"""

BASE = ('ap_worker', 'px4_worker', 'supervisor')
FC_THREADS = {'ap_fc': ('arducopter', 'log_io', 'DDS'),
              'px4_fc': ('sim_send', 'logger', 'wq:lp_default')}


def require(value, message):
    if not value:
        raise ValueError(message)


def desired_tasks(owners, epoch, inventories):
    require(set(owners) == set(BASE) | set(FC_THREADS), 'BPF mapping needs five owners')
    selected, leaders, other_names = {}, {}, {}
    for role, owner in owners.items():
        rows = inventories[role]
        leader = [row for row in rows if row['local_tid'] == owner['pid']]
        require(len(leader) == 1, 'BPF owner leader missing or ambiguous: ' + role)
        require(leader[0]['start_ticks'] == owner['start_ticks'], 'BPF owner lifetime changed: ' + role)
        leaders[role] = leader[0]
    for role, suffix in zip(BASE, ('a', 'p', 's')):
        comm = 'wk' + epoch[:11] + suffix
        require(leaders[role]['comm'] == comm, 'BPF diagnostic leader name differs: ' + role)
        selected[role] = dict(leaders[role], local_tgid=owners[role]['pid'])
        other_names[role] = [row for row in inventories[role]
                             if row['comm'] == comm and row['local_tid'] != owners[role]['pid']]
    for role, names in FC_THREADS.items():
        for name in names:
            if role == 'ap_fc' and name == 'arducopter':
                matches = [leaders[role]] if leaders[role]['comm'] == name else []
            else:
                matches = [row for row in inventories[role] if row['comm'] == name]
            require(len(matches) <= 1, 'BPF FC thread name is ambiguous: ' + role + '/' + name)
            if not matches:
                return None
            selected[role + '/' + name] = dict(matches[0], local_tgid=owners[role]['pid'])
    return selected, leaders, other_names


def bind_tasks(probe, owners, epoch, inventories, clock_ticks, read_boot_ns):
    """Return a full binding, or None while a task/valid kernel record is absent."""
    require(type(clock_ticks) is int and clock_ticks > 0, 'Invalid procfs clock tick frequency')
    require(probe.dropped_updates == 0, 'Kernel PID map dropped updates')
    choice = desired_tasks(owners, epoch, inventories)
    if choice is None:
        return None
    selected, leaders, same_comm = choice
    records = {role: probe.lookup(row['local_tid']) for role, row in selected.items()}
    now_boot_ns = read_boot_ns()
    require(type(now_boot_ns) is int and now_boot_ns > 0, 'Invalid BOOTTIME observation')
    targets, owner_kernel_groups = {}, {}
    for role, local in selected.items():
        record = records[role]
        if record is None:
            return None
        require(isinstance(record, dict), 'Invalid kernel PID record')
        for field in ('kernel_ids', 'local_tid', 'local_tgid', 'observed_boot_ns'):
            require(type(record.get(field)) is int and record[field] > 0,
                    'Invalid kernel PID field: ' + field)
        require(record['kernel_ids'] < 2**64, 'Kernel PID word overflow')
        require(record['local_tid'] == local['local_tid'], 'BPF local TID differs: ' + role)
        require(record['local_tgid'] == local['local_tgid'], 'BPF local TGID differs: ' + role)
        require(record['observed_boot_ns'] <= now_boot_ns, 'BPF sample comes from the future')
        if (record['comm'] != local['comm']
                or record['observed_boot_ns'] * clock_ticks < (local['start_ticks'] + 1) * 1_000_000_000):
            return None
        kernel_tid = record['kernel_ids'] & 0xffffffff
        kernel_tgid = record['kernel_ids'] >> 32
        require(kernel_tid > 0 and kernel_tgid > 0, 'BPF kernel PID is zero')
        owner_role = role.split('/')[0]
        if owner_role in owner_kernel_groups:
            require(owner_kernel_groups[owner_role] == kernel_tgid, 'BPF FC kernel TGID disagrees')
        owner_kernel_groups[owner_role] = kernel_tgid
        if local['local_tid'] == local['local_tgid']:
            require(kernel_tid == kernel_tgid, 'BPF leader TID/TGID differs')
        targets[role] = dict(local_tid=local['local_tid'], local_tgid=local['local_tgid'],
                             global_tid=kernel_tid, global_tgid=kernel_tgid,
                             start_ticks=local['start_ticks'], comm=local['comm'],
                             proof='kernel_bpf_pid_helpers', observed_boot_ns=record['observed_boot_ns'])
    require(len({row['global_tid'] for row in targets.values()}) == len(targets),
            'BPF target kernel TIDs are not distinct')
    require(len(set(owner_kernel_groups.values())) == 5, 'BPF owner kernel TGIDs are not distinct')
    require(probe.dropped_updates == 0, 'Kernel PID map dropped updates during binding')
    fc_leaders = {
        role: dict(global_tid=owner_kernel_groups[role], global_tgid=owner_kernel_groups[role],
                   local_tid=owner['pid'], local_tgid=owner['pid'],
                   start_ticks=owner['start_ticks'], comm=leaders[role]['comm'],
                   proof='kernel_bpf_tgid_from_owned_task')
        for role, owner in owners.items() if role in FC_THREADS}
    return dict(method='kernel BPF namespace/current PID helpers plus owned procfs lifetimes',
                leaders_proven_by='kernel_bpf_pid_helpers',
                names={role: row['comm'] for role, row in targets.items()},
                kernel_pids={role: row['global_tid'] for role, row in targets.items()},
                base_leaders={role: row for role, row in targets.items()
                              if role in BASE or role == 'ap_fc/arducopter'},
                fc_leaders=fc_leaders,
                local_threads={role: row for role, row in targets.items() if '/' in role},
                targets=targets, bpf_records=records, clock_ticks=clock_ticks,
                observed_after_boot_ns=now_boot_ns, inventories_before=inventories,
                same_comm_threads=same_comm)


def verify_lifetimes(mapping, owners, inventories):
    """Revalidate all nine selected tasks and all five leaders after sampling."""
    expected_roles = set(BASE) | {role + '/' + name for role, names in FC_THREADS.items() for name in names}
    require(set(mapping['targets']) == expected_roles, 'BPF binding target set differs')
    for role, owner in owners.items():
        leaders = [row for row in inventories[role] if row['local_tid'] == owner['pid']]
        require(len(leaders) == 1 and leaders[0]['start_ticks'] == owner['start_ticks'],
                'BPF post owner lifetime differs: ' + role)
    for role, expected in mapping['targets'].items():
        owner_role = role.split('/')[0]
        matches = [row for row in inventories[owner_role] if row['local_tid'] == expected['local_tid']]
        require(len(matches) == 1, 'BPF post task missing: ' + role)
        for field in ('local_tid', 'comm', 'start_ticks'):
            require(matches[0][field] == expected[field], 'BPF post task identity differs: ' + role + '/' + field)
        require(owners[owner_role]['pid'] == expected['local_tgid'], 'BPF post owner association differs')
    return dict(roles_verified=sorted(expected_roles), count=len(expected_roles),
                owner_count=len(owners), source='kernel_bpf_then_stable_proc_lifetimes')
