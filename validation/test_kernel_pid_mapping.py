import copy
from types import SimpleNamespace
import pytest
from tools.kernel_pid_mapping import bind_tasks, verify_lifetimes


def fixture():
    epoch = 'a' * 32
    owners = {role: {'pid': pid, 'start_ticks': pid * 10} for role, pid in
              [('ap_worker', 11), ('px4_worker', 22), ('supervisor', 33), ('ap_fc', 44), ('px4_fc', 55)]}
    names = {'ap_worker': ['wk' + epoch[:11] + 'a'], 'px4_worker': ['wk' + epoch[:11] + 'p'],
             'supervisor': ['wk' + epoch[:11] + 's'], 'ap_fc': ['arducopter', 'log_io', 'DDS'],
             'px4_fc': ['px4', 'sim_send', 'logger', 'wq:lp_default']}
    inventories, records = {}, {}
    for role, owner in owners.items():
        rows = inventories[role] = []
        for offset, name in enumerate(names[role]):
            tid = owner['pid'] + offset
            rows.append(dict(local_tid=tid, global_tid=tid, start_ticks=owner['start_ticks'], comm=name))
            records[tid] = dict(kernel_ids=((owner['pid'] + 1000) << 32) | (tid + 1000),
                                local_tid=tid, local_tgid=owner['pid'], comm=name,
                                observed_boot_ns=(owner['start_ticks'] + 2) * 10_000_000)
    probe = SimpleNamespace(dropped_updates=0, lookup=records.get)
    return probe, owners, epoch, inventories, records


def bind(data):
    probe, owners, epoch, inventories, _ = data
    return bind_tasks(probe, owners, epoch, inventories, 100, lambda: 10_000_000_000)


def test_kernel_ids_come_from_bpf_not_proc_first_nspid():
    data = fixture()
    result = bind(data)
    assert result['kernel_pids']['ap_worker'] == 1011
    assert len(result['kernel_pids']) == 9
    assert result['fc_leaders']['px4_fc']['global_tid'] == 1055
    assert verify_lifetimes(result, data[1], data[3])['count'] == 9


def test_old_entry_even_in_same_start_tick_is_not_accepted():
    data = fixture()
    data[4][11]['observed_boot_ns'] = 110 * 10_000_000 + 9_999_999
    assert bind(data) is None


@pytest.mark.parametrize('field,value', [('local_tgid', 999), ('local_tid', 999),
                                        ('kernel_ids', True), ('observed_boot_ns', 20_000_000_000)])
def test_inconsistent_kernel_record_is_rejected(field, value):
    data = fixture()
    data[4][11][field] = value
    with pytest.raises(ValueError):
        bind(data)


def test_drop_counter_prevents_binding():
    data = fixture()
    data[0].dropped_updates = 1
    with pytest.raises(ValueError, match='dropped'):
        bind(data)


def test_missing_fc_thread_waits_without_inventing_identity():
    data = fixture()
    data[3]['px4_fc'].pop()
    assert bind(data) is None


def test_ap_main_thread_is_pinned_despite_inherited_comm():
    data = fixture()
    data[3]['ap_fc'].append(dict(local_tid=49, start_ticks=441, comm='arducopter'))
    assert bind(data)['kernel_pids']['ap_fc/arducopter'] == 1044


def test_conflicting_fc_kernel_group_fails():
    data = fixture()
    data[4][45]['kernel_ids'] = (9999 << 32) | 1045
    with pytest.raises(ValueError, match='TGID disagrees'):
        bind(data)


def test_post_capture_pid_reuse_cannot_validate_old_binding():
    data = fixture()
    mapping = bind(data)
    after = copy.deepcopy(data[3])
    after['ap_fc'][1]['start_ticks'] += 1
    with pytest.raises(ValueError, match='identity differs'):
        verify_lifetimes(mapping, data[1], after)
