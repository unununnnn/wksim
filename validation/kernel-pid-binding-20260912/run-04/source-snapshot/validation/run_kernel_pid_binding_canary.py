"""Five owned actors and nine named tasks: BPF FD transfer + real sched_switch.

Actors imitate only diagnostic thread names, never FC/model/control behavior.
This proves PID binding mechanics, not SITL, rates or flight acceptance.
"""
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Simulator.wksim_runtime.evidence import host_boot_id, json_identity
from tools.kernel_pid_probe import create_probe, adopt_probe


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def actor(args):
    stop = threading.Event()
    libc = ctypes.CDLL(None)
    def name(comm):
        if libc.prctl(15, comm.encode(), 0, 0, 0) != 0:
            raise RuntimeError('actor comm setup failed')
    names = {'ap_worker': ['wk'+args.epoch[:11]+'a'],
             'px4_worker': ['wk'+args.epoch[:11]+'p'],
             'supervisor': ['wk'+args.epoch[:11]+'s'],
             'ap_fc': ['arducopter', 'log_io', 'DDS'],
             'px4_fc': ['px4', 'sim_send', 'logger', 'wq:lp_default']}[args.role]
    name(names[0])
    ready, threads = [], []
    def work(comm, signal):
        name(comm)
        signal.set()
        while not stop.wait(.002):
            pass
    for comm in names[1:]:
        signal = threading.Event()
        thread = threading.Thread(target=work, args=(comm, signal))
        thread.start()
        threads.append(thread)
        ready.append(signal)
    try:
        if not all(signal.wait(5) for signal in ready):
            raise TimeoutError('actor thread names')
        write(args.output / ('ready-'+args.role+'.json'), json_identity(os.getpid()))
        # Remain schedulable, as workers would be when native inputs are flowing.
        while True:
            if select.select([0], [], [], .002)[0] and not os.read(0, 4096):
                break
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=1)


def child(args):
    path = ROOT / 'validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py'
    spec = importlib.util.spec_from_file_location('pid_canary_collector', path)
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    owners = json.loads(args.owners.read_text())
    args.output.mkdir(exist_ok=False)
    before = collector.preflight(owners, args.boot_id)
    probe = None
    instance = collector.TRACE / 'instances' / ('wksim-rate-'+uuid.uuid4().hex)
    inode = None
    result = {'status': 'fail', 'scope': 'five actors / nine task PID binding only', 'errors': []}
    try:
        probe = adopt_probe(args.manifest, args.map_fd, args.link_fd, args.run_id, args.boot_id)
        instance.mkdir()
        stat = instance.stat()
        inode = (stat.st_dev, stat.st_ino)
        result.update(instance=str(instance), instance_inode=list(inode))
        def put(relative, value):
            collector.guarded_instance(instance, inode)
            (instance / relative).write_text(value+'\n')
        put('tracing_on', '0')
        put('current_tracer', 'nop')
        put('events/enable', '0')
        put('trace_clock', 'mono')
        put('buffer_size_kb', '1024')
        stats_before = collector.statistics(instance)
        put('tracing_on', '1')
        mapping = collector.map_kernel_pids_bpf(instance, put, owners, args.epoch,
                                               args.output, probe, args.boot_id)
        collector.seal_bootstrap(instance, put, args.output, mapping)
        stats_after = collector.statistics(instance)
        delta, loss_free = collector.loss_counter_delta(stats_before, stats_after)
        result.update(mapping=mapping, stats_before=stats_before, stats_after=stats_after,
                      loss_delta=delta, loss_free=loss_free)
        if not loss_free:
            raise RuntimeError('canary bootstrap trace lost events')
        collector.post_capture_bpf_tasks(SimpleNamespace(boot_id=args.boot_id),
                                        result, owners, mapping, probe)
        result['status'] = 'pass'
    except BaseException as error:
        result['errors'].append(repr(error))
    finally:
        if inode is not None:
            try:
                collector.guarded_instance(instance, inode)
                (instance/'tracing_on').write_text('0\n')
                (instance/'events/enable').write_text('0\n')
                instance.rmdir()
                result['instance_removed'] = True
            except BaseException as error:
                result['errors'].append('trace cleanup: '+repr(error))
        if probe is not None:
            try:
                probe.close()
                result['probe_closed'] = True
            except BaseException as error:
                result['errors'].append('probe cleanup: '+repr(error))
        result['global_controls_unchanged'] = before['global_controls'] == {
            name: (collector.TRACE/name).read_text().strip() for name in before['global_controls']}
        if result['errors'] or not result['global_controls_unchanged']:
            result['status'] = 'fail'
        write(args.output/'result.json', result)
    return 0 if result['status'] == 'pass' else 1


def parent(args):
    args.output.mkdir(exist_ok=False)
    args.run_id = 'kernel-pid-canary-'+uuid.uuid4().hex[:12]
    args.epoch = uuid.uuid4().hex
    args.boot_id = host_boot_id()
    actors, logs = {}, []
    probe = collector = None
    result = {'status': 'fail', 'scope': 'mechanism canary, not real FCs', 'errors': [], 'cleanup': {}}
    source_paths = ['tools/kernel_pid_probe_native.c', 'tools/kernel_pid_probe.py',
                    'tools/kernel_pid_mapping.py', 'validation/run_kernel_pid_binding_canary.py',
                    'validation/rate-syscall-scheduler-plan-20260909/collect_tracefs.py']
    source_hashes = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in source_paths}
    write(args.output/'inputs.json', dict(run_id=args.run_id, epoch=args.epoch,
                                         boot_id=args.boot_id, source_sha256=source_hashes))
    try:
        probe = create_probe(args.output/'probe', args.run_id, args.boot_id)
        for role in ('ap_worker', 'px4_worker', 'supervisor', 'ap_fc', 'px4_fc'):
            log = (args.output/(role+'.log')).open('xb')
            logs.append(log)
            actors[role] = subprocess.Popen([sys.executable, __file__, '--actor', '--role', role,
                '--epoch', args.epoch, '--output', str(args.output)], stdin=subprocess.PIPE,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic()+15
        while not all((args.output/('ready-'+role+'.json')).exists() for role in actors):
            if time.monotonic() >= deadline or any(proc.poll() is not None for proc in actors.values()):
                raise RuntimeError('owned actor startup failed')
            time.sleep(.02)
        owners = {role: json_identity(proc.pid) for role, proc in actors.items()}
        write(args.output/'owners.json', owners)
        inherited = probe.inherited_fds()
        log = (args.output/'collector.log').open('xb')
        logs.append(log)
        collector = subprocess.Popen([sys.executable, __file__, '--child',
            '--manifest', str(probe.manifest_path), '--map-fd', str(inherited[0]),
            '--link-fd', str(inherited[1]), '--owners', str(args.output/'owners.json'),
            '--run-id', args.run_id, '--epoch', args.epoch, '--boot-id', args.boot_id,
            '--output', str(args.output/'capture')], pass_fds=inherited,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        probe.release_parent_after_spawn()
        if collector.wait(timeout=30) != 0:
            raise RuntimeError('inherited-descriptor collector failed')
        result['capture'] = json.loads((args.output/'capture/result.json').read_text())
        if result['capture']['status'] != 'pass':
            raise RuntimeError('canary binding result failed')
        result['status'] = 'pass'
    except BaseException as error:
        result['errors'].append(repr(error))
    finally:
        if collector is not None and collector.poll() is None:
            collector.terminate()
            try:
                collector.wait(timeout=10)
            except subprocess.TimeoutExpired:
                collector.kill()
                collector.wait(timeout=5)
        for role, proc in actors.items():
            if proc.stdin is not None:
                proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            result['cleanup'][role] = proc.returncode
            if proc.returncode != 0:
                result['status'] = 'fail'
        if probe is not None:
            probe.close()
        for log in logs:
            log.close()
        result['sources_unchanged'] = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == expected
                                          for name, expected in source_hashes.items())
        if not result['sources_unchanged']:
            result['status'] = 'fail'
            result['errors'].append('source changed during native canary')
        write(args.output/'summary.json', result)
    print(json.dumps({'status': result['status'], 'output': str(args.output), 'errors': result['errors']}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--actor', action='store_true')
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--role')
    parser.add_argument('--epoch')
    parser.add_argument('--run-id')
    parser.add_argument('--boot-id')
    parser.add_argument('--owners', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--map-fd', type=int)
    parser.add_argument('--link-fd', type=int)
    args = parser.parse_args()
    raise SystemExit(actor(args) if args.actor else child(args) if args.child else parent(args))
