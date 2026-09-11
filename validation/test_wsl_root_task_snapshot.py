"""Offline unit tests and clean live test for wsl_root_task_snapshot (#102 / Task17o)."""
import base64
import os
import re
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.wsl_root_task_snapshot import (
    _run_bounded,
    build_exporter_sh_script,
    detect_local_pid_ns_inode,
    normalize_owned_processes,
    parse_exporter_output,
    parse_task_record,
    snapshot_wsl_root_tasks,
    verify_lsns_root,
)


def make_stat(pid: int, comm: str, start_ticks: int = 5000) -> str:
    """Generate a valid Linux /proc/<pid>/stat line."""
    fields = ['S'] + ['0'] * 18 + [str(start_ticks)] + ['0'] * 30
    return f'{pid} ({comm}) ' + ' '.join(fields) + '\n'


def make_status(comm: str, tgid: int, pid: int, nstgid: list[int], nspid: list[int]) -> str:
    """Generate a valid Linux /proc/<pid>/status text snippet."""
    nstgid_str = '\t'.join(str(v) for v in nstgid)
    nspid_str = '\t'.join(str(v) for v in nspid)
    return (
        f'Name:\t{comm}\n'
        f'Tgid:\t{tgid}\n'
        f'Pid:\t{pid}\n'
        f'PPid:\t1\n'
        f'NStgid:\t{nstgid_str}\n'
        f'NSpid:\t{nspid_str}\n'
    )


def make_task_export_line(
    gtgid: int,
    gtid: int,
    ns_inode: int,
    comm: str,
    local_tgid: int,
    local_tid: int,
    start_ticks: int = 5000,
    stat_override: str | None = None,
    stat2_override: str | None = None,
    status_override: str | None = None,
    comm_override: str | None = None,
) -> str:
    """Encode synthetic task procfs data into the exporter protocol line."""
    stat_text = stat_override or make_stat(gtid, comm, start_ticks)
    stat2_text = stat2_override or stat_text
    status_text = status_override or make_status(comm, gtgid, gtid, [gtgid, local_tgid], [gtid, local_tid])
    comm_text = comm_override or (comm + '\n')

    s1_b64 = base64.b64encode(stat_text.encode('utf-8')).decode('ascii')
    s2_b64 = base64.b64encode(stat2_text.encode('utf-8')).decode('ascii')
    st_b64 = base64.b64encode(status_text.encode('utf-8')).decode('ascii')
    cm_b64 = base64.b64encode(comm_text.encode('utf-8')).decode('ascii')
    ns_str = f'pid:[{ns_inode}]'

    return f'TASK {gtgid} {gtid} {ns_str} {s1_b64} {st_b64} {cm_b64} {s2_b64}'


def make_exporter_output(lsns_body: str, task_lines: list[str]) -> str:
    tasks_joined = '\n'.join(task_lines)
    return (
        '===LSNS_BEGIN===\n'
        f'{lsns_body}\n'
        '===LSNS_END===\n'
        '===TASKS_BEGIN===\n'
        f'{tasks_joined}\n'
        '===TASKS_END===\n'
    )


VALID_LSNS = (
    '        NS        PNS PID PPID COMMAND\n'
    '4026532209          0   1    0 /init\n'
    '4026532221 4026532209   2    1 /sbin/init'
)


class WslRootTaskSnapshotSyntheticTests(unittest.TestCase):
    """Synthetic adversarial offline unit tests."""

    def test_verify_lsns_root_valid(self):
        proof = verify_lsns_root(VALID_LSNS, 4026532221)
        self.assertEqual(proof['root_ns'], 4026532209)
        self.assertEqual(proof['target_ns'], 4026532221)
        self.assertEqual(proof['root_pid'], 1)
        self.assertEqual(proof['target_pid'], 2)

    def test_verify_lsns_root_fails_closed_without_pns_zero(self):
        bad_lsns = (
            '        NS        PNS PID PPID COMMAND\n'
            '4026532209        999   1    0 /init\n'
            '4026532221 4026532209   2    1 /sbin/init'
        )
        with self.assertRaisesRegex(RuntimeError, 'Expected exactly 1 root PID namespace'):
            verify_lsns_root(bad_lsns, 4026532221)

    def test_verify_lsns_root_fails_closed_when_target_missing(self):
        missing_target_lsns = (
            '        NS        PNS PID PPID COMMAND\n'
            '4026532209          0   1    0 /init\n'
            '4026539999 4026532209   2    1 /sbin/init'
        )
        with self.assertRaisesRegex(RuntimeError, 'Target PID namespace 4026532221 not observed'):
            verify_lsns_root(missing_target_lsns, 4026532221)

    def test_verify_lsns_root_fails_closed_when_target_parent_differs(self):
        bad_parent_lsns = (
            '        NS        PNS PID PPID COMMAND\n'
            '4026532209          0   1    0 /init\n'
            '4026532221 4026531111   2    1 /sbin/init'
        )
        with self.assertRaisesRegex(RuntimeError, 'parent PNS is 4026531111, expected root 4026532209'):
            verify_lsns_root(bad_parent_lsns, 4026532221)

    def test_parse_task_record_valid_leader_and_helper(self):
        leader_line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026532221, comm='wk-s',
            local_tgid=601, local_tid=601, start_ticks=7890
        )
        rec = parse_task_record(leader_line, 4026532221)
        self.assertEqual(rec['global_tgid'], 1015)
        self.assertEqual(rec['global_tid'], 1015)
        self.assertEqual(rec['local_tgid'], 601)
        self.assertEqual(rec['local_tid'], 601)
        self.assertEqual(rec['comm'], 'wk-s')
        self.assertEqual(rec['start_ticks'], 7890)
        self.assertTrue(rec['is_leader'])

        helper_line = make_task_export_line(
            gtgid=1015, gtid=1016, ns_inode=4026532221, comm='helper',
            local_tgid=601, local_tid=602, start_ticks=7895
        )
        helper_rec = parse_task_record(helper_line, 4026532221)
        self.assertEqual(helper_rec['global_tid'], 1016)
        self.assertEqual(helper_rec['local_tid'], 602)
        self.assertFalse(helper_rec['is_leader'])

    def test_parse_task_record_rejects_wrong_namespace(self):
        line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026539999, comm='wk-s',
            local_tgid=601, local_tid=601
        )
        with self.assertRaisesRegex(ValueError, 'Namespace link mismatch'):
            parse_task_record(line, 4026532221)

    def test_parse_task_record_rejects_raced_stat(self):
        s1 = make_stat(1015, 'wk-s', 5000)
        s2 = make_stat(1015, 'wk-s', 6000)
        line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026532221, comm='wk-s',
            local_tgid=601, local_tid=601, stat_override=s1, stat2_override=s2
        )
        with self.assertRaisesRegex(RuntimeError, 'raced during snapshot'):
            parse_task_record(line, 4026532221)

    def test_parse_task_record_rejects_comm_mismatch(self):
        line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026532221, comm='wk-s',
            local_tgid=601, local_tid=601, comm_override='other\n'
        )
        with self.assertRaisesRegex(ValueError, 'comm mismatch'):
            parse_task_record(line, 4026532221)

    def test_parse_task_record_rejects_non_positive_ids(self):
        status = make_status('wk-s', 1015, 1015, [1015, 0], [1015, 601])
        line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026532221, comm='wk-s',
            local_tgid=601, local_tid=601, status_override=status
        )
        with self.assertRaisesRegex(ValueError, 'Non-positive ID in namespace chain'):
            parse_task_record(line, 4026532221)

    def test_parse_task_record_rejects_single_level_nspid(self):
        status = 'Name:\twk-s\nTgid:\t1015\nPid:\t1015\nNStgid:\t1015\nNSpid:\t1015\n'
        line = make_task_export_line(
            gtgid=1015, gtid=1015, ns_inode=4026532221, comm='wk-s',
            local_tgid=601, local_tid=601, status_override=status
        )
        with self.assertRaisesRegex(ValueError, 'expected 2-level namespace chains'):
            parse_task_record(line, 4026532221)

    def test_parse_exporter_output_full_flow(self):
        lines = [
            make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000),
            make_task_export_line(1002, 1002, 4026532221, 'wk-p', 22, 22, 2000),
            make_task_export_line(1003, 1003, 4026532221, 'wk-s', 33, 33, 3000),
            make_task_export_line(1003, 1004, 4026532221, 'helper', 33, 34, 3010),
            # An unowned process should be ignored cleanly
            make_task_export_line(1099, 1099, 4026532221, 'unowned', 99, 99, 9000),
        ]
        out_text = make_exporter_output(VALID_LSNS, lines)
        owners = {
            'ap_worker': {'pid': 11, 'start_ticks': 1000},
            'px4_worker': {'pid': 22, 'start_ticks': 2000},
            'supervisor': {'pid': 33, 'start_ticks': 3000},
        }
        res = parse_exporter_output(out_text, 4026532221, owners)
        self.assertEqual(res['root_pid_ns'], 4026532209)
        self.assertEqual(res['target_pid_ns'], 4026532221)
        self.assertEqual(len(res['leaders']), 3)
        self.assertEqual(res['leaders'][11]['global_tid'], 1001)
        self.assertEqual(res['leaders'][22]['global_tid'], 1002)
        self.assertEqual(res['leaders'][33]['global_tid'], 1003)
        self.assertEqual(len(res['tasks']), 4)  # 3 leaders + 1 helper
        self.assertEqual(res['tasks_by_local_tid'][34]['global_tid'], 1004)

    def test_parse_exporter_output_rejects_missing_owned_process(self):
        lines = [
            make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000),
        ]
        out_text = make_exporter_output(VALID_LSNS, lines)
        owners = {
            'ap_worker': {'pid': 11, 'start_ticks': 1000},
            'px4_worker': {'pid': 22, 'start_ticks': 2000},
        }
        with self.assertRaisesRegex(ValueError, 'px4_worker.*not observed in host snapshot'):
            parse_exporter_output(out_text, 4026532221, owners)

    def test_parse_exporter_output_rejects_start_ticks_mismatch(self):
        lines = [
            make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 9999),
        ]
        out_text = make_exporter_output(VALID_LSNS, lines)
        owners = {
            'ap_worker': {'pid': 11, 'start_ticks': 1000},
        }
        with self.assertRaisesRegex(ValueError, 'start_ticks mismatch: observed=9999 vs expected=1000'):
            parse_exporter_output(out_text, 4026532221, owners)

    def test_parse_exporter_output_rejects_duplicate_global_tid(self):
        lines = [
            make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000),
            make_task_export_line(1001, 1001, 4026532221, 'wk-p', 22, 22, 2000),
        ]
        out_text = make_exporter_output(VALID_LSNS, lines)
        owners = {
            'ap_worker': {'pid': 11, 'start_ticks': 1000},
            'px4_worker': {'pid': 22, 'start_ticks': 2000},
        }
        with self.assertRaisesRegex(ValueError, 'Duplicate global TID observed'):
            parse_exporter_output(out_text, 4026532221, owners)

    def test_snapshot_wsl_root_tasks_with_mock_executor(self):
        lines = [
            make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000),
        ]
        out_text = make_exporter_output(VALID_LSNS, lines)

        def mock_executor(cmd, timeout):
            self.assertIn('--system', cmd)
            self.assertIn('-u', cmd)
            self.assertIn('root', cmd)
            return (0, out_text.encode('utf-8'), b'')

        res = snapshot_wsl_root_tasks(
            4026532221,
            {'ap_worker': {'pid': 11, 'start_ticks': 1000}},
            executor=mock_executor,
        )
        self.assertEqual(res['leaders'][11]['global_tid'], 1001)

    def test_task_record_rejects_non_base64_field(self):
        line = make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000)
        parts = line.split()
        parts[4] = 'not!!!base64'  # stat1 with characters outside the alphabet
        with self.assertRaises(Exception):
            parse_task_record(' '.join(parts), 4026532221)

    def test_namespace_inode_input_strictness(self):
        for bad in (True, False, 1.5, 'abc123', '12x', '-5', '0'):
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError, TypeError)):
                    snapshot_wsl_root_tasks(bad, {'a': {'pid': 1, 'start_ticks': 1}},
                                            executor=lambda c, t: (0, b'', b''))

    def test_owned_identity_rejects_bool_and_float_before_execution(self):
        for owner in ({'pid': True, 'start_ticks': 1},
                      {'pid': 1, 'start_ticks': True},
                      {'pid': 1.5, 'start_ticks': 1},
                      {'pid': 1, 'start_ticks': 1.5}):
            with self.subTest(owner=owner), self.assertRaisesRegex(ValueError, 'positive integer'):
                snapshot_wsl_root_tasks(4026532221, {'owner': owner},
                    executor=lambda c, t: self.fail('invalid owner reached exporter'))

    def test_stat_pid_must_match_exported_directory(self):
        line = make_task_export_line(1001, 1001, 4026532221, 'wk-a', 11, 11, 1000)
        fields = line.split()
        for index in (4, 7):
            raw = base64.b64decode(fields[index])
            fields[index] = base64.b64encode(raw.replace(b'1001 (', b'9999 (', 1)).decode()
        with self.assertRaisesRegex(ValueError, 'Stat pid'):
            parse_task_record(' '.join(fields), 4026532221)

    def test_executor_seam_output_cap_rejects(self):
        def fat_executor(cmd, timeout):
            return (0, b'x' * 1024, b'')
        with self.assertRaises(ValueError):
            snapshot_wsl_root_tasks(4026532221, {'a': {'pid': 1, 'start_ticks': 1}},
                                    executor=fat_executor, max_output_bytes=64)

    def test_run_bounded_read_cap_kills_owned_child(self):
        with self.assertRaises(ValueError):
            _run_bounded([sys.executable, '-c', 'print("x" * 100000)'],
                         5.0, 1000)

    def test_run_bounded_timeout_kills_owned_child(self):
        import time
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            _run_bounded([sys.executable, '-c', 'import time; time.sleep(30)'], 0.3, 1024)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_run_bounded_deadline_survives_closed_output_pipes(self):
        import time
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            _run_bounded([sys.executable, '-c',
                          'import os,time; os.close(1); os.close(2); time.sleep(30)'], 0.3, 1024)
        self.assertLess(time.monotonic() - started, 5.0)

    def test_run_bounded_limits_stderr_and_drains_both_streams(self):
        with self.assertRaises(ValueError):
            _run_bounded([sys.executable, '-c',
                          'import sys; sys.stderr.write("x" * 100000)'], 5.0, 1000)
        code, out, err = _run_bounded([sys.executable, '-c',
            'import sys; print("out"); sys.stderr.write("err")'], 5.0, 1024)
        self.assertEqual((code, out.strip(), err), (0, b'out', b'err'))


class WslRootTaskSnapshotLiveSubprocessTest(unittest.TestCase):
    """Clean live test spawning one self-owned short-lived Python process.

    Spawns one child process, verifies host root snapshot mapping, and
    guarantees clean termination of the child in a try/finally block.
    """

    def test_live_short_lived_owned_process_snapshot(self):
        child = None
        try:
            if sys.platform == 'linux':
                if not Path('/proc/self/ns/pid').exists():
                    self.skipTest('Live test requires Linux /proc/self/ns/pid')
                wsl_bin = Path('/mnt/c/Windows/System32/wsl.exe')
                if not wsl_bin.is_file() or not os.access(wsl_bin, os.X_OK):
                    self.skipTest('/mnt/c/Windows/System32/wsl.exe not accessible')

                child = subprocess.Popen(
                    [sys.executable, '-c', 'import time; time.sleep(30)'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                child_pid = child.pid
                stat_text = Path(f'/proc/{child_pid}/stat').read_text()
                rparen = stat_text.rfind(')')
                fields = stat_text[rparen + 2:].split()
                child_start_ticks = int(fields[19])
                local_ns = detect_local_pid_ns_inode()
            else:
                # Windows host: spawn short-lived child inside WSL Ubuntu-22.04
                child = subprocess.Popen(
                    ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', 'python3', '-c',
                     'import os,sys; print(os.getpid(), flush=True); sys.stdin.readline()'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                )
                line = child.stdout.readline().strip()
                if not line or not line.isdigit():
                    self.skipTest('Failed to spawn test python process in WSL')
                child_pid = int(line)
                ns_str = subprocess.run(
                    ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', 'readlink', '/proc/self/ns/pid'],
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                local_ns = int(re.search(r'\[(\d+)\]', ns_str).group(1))
                stat_out = subprocess.run(
                    ['wsl', '-d', 'Ubuntu-22.04', '-u', 'root', 'cat', f'/proc/{child_pid}/stat'],
                    capture_output=True, text=True, check=True
                ).stdout
                rparen = stat_out.rfind(')')
                fields = stat_out[rparen + 2:].split()
                child_start_ticks = int(fields[19])

            owners = {
                'test_canary': {'pid': child_pid, 'start_ticks': child_start_ticks}
            }

            try:
                distro = os.environ.get('WSL_DISTRO_NAME', 'Ubuntu-22.04') if sys.platform == 'linux' else 'Ubuntu-22.04'
                snapshot = snapshot_wsl_root_tasks(local_ns, owners, distro=distro, timeout_s=5.0)
            except RuntimeError as err:
                if 'WSLInterop' in str(err) or 'binfmt_misc' in str(err):
                    self.skipTest(str(err))
                raise

            self.assertIn('root_pid_ns', snapshot)
            self.assertIn('target_pid_ns', snapshot)
            self.assertEqual(snapshot['target_pid_ns'], local_ns)
            self.assertIn(child_pid, snapshot['leaders'])

            leader = snapshot['leaders'][child_pid]
            self.assertEqual(leader['local_tgid'], child_pid)
            self.assertEqual(leader['local_tid'], child_pid)
            self.assertEqual(leader['start_ticks'], child_start_ticks)
            self.assertGreater(leader['global_tid'], 0)
            self.assertEqual(leader['global_tgid'], leader['global_tid'])
            self.assertTrue(leader['is_leader'])

        finally:
            if child is not None:
                # Closing stdin lets the Windows-launched Linux canary exit
                # itself; killing wsl.exe alone does not prove remote cleanup.
                if child.stdin is not None:
                    child.stdin.close()
                    child.wait(timeout=5.0)
                if child.stdout is not None:
                    try:
                        child.stdout.close()
                    except Exception:
                        pass
                try:
                    child.terminate()
                    child.wait(timeout=2.0)
                except Exception:
                    try:
                        child.kill()
                        child.wait(timeout=2.0)
                    except Exception:
                        pass


if __name__ == '__main__':
    unittest.main()
