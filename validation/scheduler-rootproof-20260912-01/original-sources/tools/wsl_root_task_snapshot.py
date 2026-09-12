"""WSL host-root procfs task snapshot exporter and verifier.

Provides read-only, namespace-verified binding between container-local task
identities (local_tid, local_tgid) and host kernel-global identities (global_tid,
global_tgid).

Executed via a fixed argv invocation of ``wsl.exe -d <distro> --system -u root sh``
against the WSL VM system container (root PID namespace PNS 0), preserving raw
bytes via base64 without requiring Python on the system host.
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

DEFAULT_DISTRO = 'Ubuntu-22.04'
DEFAULT_TIMEOUT_S = 5.0
DEFAULT_MAX_BYTES = 2 * 1024 * 1024

WSL_C_PATH = Path('/mnt/c/Windows/System32/wsl.exe')
WSL_WIN_PATH = Path(r'C:\Windows\System32\wsl.exe')

LSNS_PATTERN = re.compile(
    r'^\s*(?P<ns>\d+)\s+(?P<pns>\d+)\s+(?P<pid>\d+)\s+(?P<ppid>\d+)\s+(?P<cmd>\S+)',
    re.MULTILINE,
)

TGID_RE = re.compile(r'^Tgid:\s*(\d+)$', re.MULTILINE)
PID_RE = re.compile(r'^Pid:\s*(\d+)$', re.MULTILINE)
NSTGID_RE = re.compile(r'^NStgid:\s*(\d+(?:\s+\d+)*)$', re.MULTILINE)
NSPID_RE = re.compile(r'^NSpid:\s*(\d+(?:\s+\d+)*)$', re.MULTILINE)


def find_wsl_binary() -> str:
    """Locate the wsl.exe binary on WSL or Windows."""
    if WSL_C_PATH.is_file() and os.access(WSL_C_PATH, os.X_OK):
        return str(WSL_C_PATH)
    found = shutil.which('wsl.exe')
    if found:
        return found
    if WSL_WIN_PATH.is_file():
        return str(WSL_WIN_PATH)
    return 'wsl.exe'


def detect_local_pid_ns_inode() -> int:
    """Return the local PID namespace inode from /proc/self/ns/pid."""
    ns_path = Path('/proc/self/ns/pid')
    if not ns_path.exists():
        raise NotImplementedError('Local PID namespace detection requires /proc/self/ns/pid (Linux)')
    link = os.readlink(ns_path)
    match = re.search(r'\[(\d+)\]', link)
    if not match:
        raise ValueError(f'Cannot parse local PID namespace inode from {link}')
    return int(match.group(1))


def build_exporter_sh_script(target_ns_inode: int) -> str:
    """Generate the POSIX sh script executed inside the system container.

    The system container has no Python, but has sh, base64, readlink, lsns.
    The script outputs delimited sections:
      ===LSNS_BEGIN=== ... ===LSNS_END===
      ===TASKS_BEGIN=== ... ===TASKS_END===
    Each task line:
      TASK <gtgid> <gtid> <ns_link> <stat1_b64> <status_b64> <comm_b64> <stat2_b64>
    """
    return (
        f'TARGET_NS="{int(target_ns_inode)}"\n'
        'echo "===LSNS_BEGIN==="\n'
        'lsns -t pid -o NS,PNS,PID,PPID,COMMAND 2>/dev/null || echo "LSNS_FAILED"\n'
        'echo "===LSNS_END==="\n'
        'echo "===TASKS_BEGIN==="\n'
        'for p in /proc/[0-9]*; do\n'
        '    [ -d "$p" ] || continue\n'
        '    ns=$(readlink "$p/ns/pid" 2>/dev/null)\n'
        '    [ "$ns" = "pid:[$TARGET_NS]" ] || continue\n'
        '    gtgid="${p##*/}"\n'
        '    for t in "$p"/task/[0-9]*; do\n'
        '        [ -d "$t" ] || continue\n'
        '        gtid="${t##*/}"\n'
        '        s1=$(cat "$t/stat" 2>/dev/null | base64 | tr -d "\\r\\n")\n'
        '        [ -n "$s1" ] || continue\n'
        '        st=$(cat "$t/status" 2>/dev/null | base64 | tr -d "\\r\\n")\n'
        '        cm=$(cat "$t/comm" 2>/dev/null | base64 | tr -d "\\r\\n")\n'
        '        s2=$(cat "$t/stat" 2>/dev/null | base64 | tr -d "\\r\\n")\n'
        '        echo "TASK $gtgid $gtid $ns $s1 $st $cm $s2"\n'
        '    done\n'
        'done\n'
        'echo "===TASKS_END==="\n'
    )


def verify_lsns_root(lsns_text: str, target_ns_inode: int) -> dict[str, Any]:
    """Verify that the host lsns output confirms a genuine root PID namespace (PNS 0).

    Fails closed if the root namespace is not PNS 0, or if the target namespace
    is not a direct descendant of the verified root.
    """
    matches = list(LSNS_PATTERN.finditer(lsns_text))
    if not matches:
        raise RuntimeError('lsns failed to produce valid PID namespace table')

    rows = [{k: int(v) if k != 'cmd' else v for k, v in m.groupdict().items()}
            for m in matches]

    roots = [r for r in rows if r['pns'] == 0]
    if len(roots) != 1:
        raise RuntimeError(f'Expected exactly 1 root PID namespace (PNS 0), found {len(roots)}')
    root_ns = roots[0]['ns']

    targets = [r for r in rows if r['ns'] == target_ns_inode]
    if not targets:
        raise RuntimeError(f'Target PID namespace {target_ns_inode} not observed in lsns table')
    target_row = targets[0]
    if target_row['pns'] != root_ns:
        raise RuntimeError(
            f'Target PID namespace {target_ns_inode} parent PNS is {target_row["pns"]}, '
            f'expected root {root_ns}'
        )

    return {
        'root_ns': root_ns,
        'target_ns': target_ns_inode,
        'root_pid': roots[0]['pid'],
        'target_pid': target_row['pid'],
        'raw': lsns_text.strip(),
    }


def parse_stat_identity(stat_text: str, gtid_str: str) -> tuple[str, str, int]:
    """Extract (pid_str, comm, start_ticks) from a /proc/<pid>/stat line."""
    rparen = stat_text.rfind(')')
    lparen = stat_text.find('(')
    if rparen < 0 or lparen < 0 or lparen >= rparen:
        raise ValueError(f'Malformed stat line for task {gtid_str}: {stat_text!r}')

    pid_str = stat_text[:lparen].strip()
    comm = stat_text[lparen + 1:rparen]
    fields = stat_text[rparen + 2:].split()
    if len(fields) <= 19:
        raise ValueError(f'Incomplete stat fields for task {gtid_str}')
    start_ticks = int(fields[19])
    return pid_str, comm, start_ticks


def parse_task_record(line: str, expected_ns_inode: int) -> dict[str, Any]:
    """Parse, decode base64, and strictly validate a single exported task line.

    Verifies:
      - ns == pid:[<expected_ns_inode>]
      - stat stability (comm, pid, start_ticks do not change during inventory)
      - comm in stat matches comm file
      - NStgid == [global_tgid, local_tgid] with all > 0
      - NSpid == [global_tid, local_tid] with all > 0
      - directory names match global IDs
      - start_ticks > 0
    """
    parts = line.strip().split()
    if len(parts) != 8 or parts[0] != 'TASK':
        raise ValueError(f'Malformed task export line: {line!r}')

    _, gtgid_str, gtid_str, ns_str, s1_b64, st_b64, cm_b64, s2_b64 = parts

    expected_link = f'pid:[{expected_ns_inode}]'
    if ns_str != expected_link:
        raise ValueError(f'Namespace link mismatch: {ns_str} != {expected_link}')

    s1_bytes = base64.b64decode(s1_b64, validate=True)
    st_bytes = base64.b64decode(st_b64, validate=True)
    cm_bytes = base64.b64decode(cm_b64, validate=True)
    s2_bytes = base64.b64decode(s2_b64, validate=True)

    s1_text = s1_bytes.decode('utf-8', errors='replace').strip()
    s2_text = s2_bytes.decode('utf-8', errors='replace').strip()
    st_text = st_bytes.decode('utf-8', errors='replace')
    comm = cm_bytes.decode('utf-8', errors='replace').strip()

    pid1, comm1, ticks1 = parse_stat_identity(s1_text, gtid_str)
    pid2, comm2, ticks2 = parse_stat_identity(s2_text, gtid_str)

    if pid1 != pid2 or comm1 != comm2 or ticks1 != ticks2:
        raise RuntimeError(
            f'Task {gtid_str} raced during snapshot: stat identity before/after differ '
            f'({pid1}:{comm1}:{ticks1} vs {pid2}:{comm2}:{ticks2})'
        )

    if pid1 != gtid_str:
        raise ValueError(f'Stat pid {pid1} != directory gtid {gtid_str}')

    if comm1 != comm:
        raise ValueError(f'Task {gtid_str} comm mismatch: stat={comm1!r} vs comm={comm!r}')

    if ticks1 <= 0:
        raise ValueError(f'Task {gtid_str} non-positive start_ticks: {ticks1}')

    tgid_m = TGID_RE.search(st_text)
    pid_m = PID_RE.search(st_text)
    nstgid_m = NSTGID_RE.search(st_text)
    nspid_m = NSPID_RE.search(st_text)

    if not tgid_m or not pid_m or not nstgid_m or not nspid_m:
        raise ValueError(f'Task {gtid_str} status is missing required ID fields')

    gtgid = int(gtgid_str)
    gtid = int(gtid_str)
    if gtgid <= 0 or gtid <= 0:
        raise ValueError(f'Non-positive global ID: gtgid={gtgid}, gtid={gtid}')

    if int(tgid_m.group(1)) != gtgid:
        raise ValueError(f'Tgid {tgid_m.group(1)} != directory gtgid {gtgid}')
    if int(pid_m.group(1)) != gtid:
        raise ValueError(f'Pid {pid_m.group(1)} != directory gtid {gtid}')

    nstgid_chain = [int(v) for v in nstgid_m.group(1).split()]
    nspid_chain = [int(v) for v in nspid_m.group(1).split()]

    if len(nstgid_chain) != 2 or len(nspid_chain) != 2:
        raise ValueError(
            f'Task {gtid_str} expected 2-level namespace chains, got '
            f'NStgid={nstgid_chain}, NSpid={nspid_chain}'
        )

    if not all(v > 0 for v in nstgid_chain + nspid_chain):
        raise ValueError(f'Non-positive ID in namespace chain: {nstgid_chain}, {nspid_chain}')

    if nstgid_chain[0] != gtgid or nspid_chain[0] != gtid:
        raise ValueError('Root namespace chain entry does not match global ID')

    local_tgid = nstgid_chain[1]
    local_tid = nspid_chain[1]

    is_leader = (local_tid == local_tgid)
    if is_leader and (gtid != gtgid):
        raise ValueError(f'Thread leader local_tid==local_tgid but gtid({gtid})!=gtgid({gtgid})')

    return {
        'global_tgid': gtgid,
        'global_tid': gtid,
        'local_tgid': local_tgid,
        'local_tid': local_tid,
        'comm': comm,
        'start_ticks': ticks1,
        'is_leader': is_leader,
        'evidence': {
            'stat_before': s1_text,
            'stat_after': s2_text,
            'status': st_text.strip(),
            'comm': comm,
            'ns_link': ns_str,
        },
    }


def normalize_owned_processes(
    owned: Mapping[str, Any]
) -> dict[int, dict[str, Any]]:
    """Normalize input owned process definitions into {local_pid: {'role': ..., 'expected_start_ticks': ...}}."""
    result: dict[int, dict[str, Any]] = {}
    for key, val in owned.items():
        if isinstance(val, dict):
            raw_ticks = val.get('expected_start_ticks', val.get('start_ticks'))
            if type(raw_ticks) is not int or raw_ticks <= 0:
                raise ValueError('Owned start_ticks must be a positive integer')
            if 'pid' in val and (type(val['pid']) is not int or val['pid'] <= 0):
                raise ValueError('Owned pid must be a positive integer')
            if 'expected_start_ticks' in val:
                pid = int(key) if isinstance(key, (int, str)) and str(key).isdigit() else int(val.get('pid', key))
                ticks = int(val['expected_start_ticks'])
                role = str(val.get('role', key))
            else:
                pid = int(val['pid'])
                ticks = int(val['start_ticks'])
                role = str(val.get('role', key))
        elif isinstance(val, (int, str)) and isinstance(key, (int, str)):
            if type(val) is not int or isinstance(key, bool):
                raise ValueError('Owned identity must use integer pid and start_ticks')
            pid = int(key)
            ticks = int(val)
            role = str(key)
        else:
            raise TypeError(f'Unsupported owned process entry: {key!r}: {val!r}')

        if pid <= 0 or ticks <= 0:
            raise ValueError(f'Owned process has non-positive pid or start_ticks: {pid}:{ticks}')
        if pid in result:
            raise ValueError(f'Duplicate owned process pid: {pid}')
        result[pid] = {'role': role, 'expected_start_ticks': ticks}
    return result


def parse_exporter_output(
    output_text: str,
    target_ns_inode: int,
    expected_owners: Mapping[str, Any],
) -> dict[str, Any]:
    """Parse and strictly validate the full output of the system sh exporter."""
    lsns_start = output_text.find('===LSNS_BEGIN===')
    lsns_end = output_text.find('===LSNS_END===')
    tasks_start = output_text.find('===TASKS_BEGIN===')
    tasks_end = output_text.find('===TASKS_END===')

    if min(lsns_start, lsns_end, tasks_start, tasks_end) < 0:
        raise RuntimeError('Exporter output is missing required section delimiters')

    lsns_content = output_text[lsns_start + len('===LSNS_BEGIN==='):lsns_end].strip()
    tasks_content = output_text[tasks_start + len('===TASKS_BEGIN==='):tasks_end].strip()

    lsns_proof = verify_lsns_root(lsns_content, target_ns_inode)

    owners_map = normalize_owned_processes(expected_owners)
    target_pids = set(owners_map.keys())

    all_tasks: list[dict[str, Any]] = []
    seen_global_tids: set[int] = set()
    seen_local_tids: set[int] = set()

    for line in tasks_content.splitlines():
        line = line.strip()
        if not line or not line.startswith('TASK '):
            continue
        rec = parse_task_record(line, target_ns_inode)
        # Filter to only tasks belonging to owned target processes
        if rec['local_tgid'] not in target_pids:
            continue

        gtid = rec['global_tid']
        ltid = rec['local_tid']
        if gtid in seen_global_tids:
            raise ValueError(f'Duplicate global TID observed: {gtid}')
        if ltid in seen_local_tids:
            raise ValueError(f'Duplicate local TID observed: {ltid}')
        seen_global_tids.add(gtid)
        seen_local_tids.add(ltid)

        rec['role'] = owners_map[rec['local_tgid']]['role']
        all_tasks.append(rec)

    # Verify that every owned process has exactly one leader thread matching start_ticks
    leaders_by_pid: dict[int, dict[str, Any]] = {}
    threads_by_pid: dict[int, list[dict[str, Any]]] = {pid: [] for pid in target_pids}

    for task in all_tasks:
        pid = task['local_tgid']
        threads_by_pid[pid].append(task)
        if task['is_leader']:
            if pid in leaders_by_pid:
                raise ValueError(f'Multiple leader threads for local pid {pid}')
            leaders_by_pid[pid] = task

    for pid, meta in owners_map.items():
        if pid not in leaders_by_pid:
            raise ValueError(
                f'Owned process {meta["role"]} (pid {pid}) not observed in host snapshot'
            )
        leader = leaders_by_pid[pid]
        expected_ticks = meta['expected_start_ticks']
        if leader['start_ticks'] != expected_ticks:
            raise ValueError(
                f'Owned process {meta["role"]} (pid {pid}) start_ticks mismatch: '
                f'observed={leader["start_ticks"]} vs expected={expected_ticks}'
            )

    return {
        'root_pid_ns': lsns_proof['root_ns'],
        'target_pid_ns': target_ns_inode,
        'lsns_evidence': lsns_proof,
        'leaders': leaders_by_pid,
        'tasks': all_tasks,
        'threads_by_pid': threads_by_pid,
        'tasks_by_local_tid': {t['local_tid']: t for t in all_tasks},
        'tasks_by_global_tid': {t['global_tid']: t for t in all_tasks},
    }


def _run_bounded(cmd, timeout_s, max_bytes):
    """Bound both output streams and the entire lifetime of one owned child."""
    import math
    import threading
    import time
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError('timeout_s must be finite and positive')
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('max_bytes must be a positive integer')
    deadline = time.monotonic() + timeout_s
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    except OSError as err:
        if err.errno == 8:
            raise RuntimeError('WSLInterop binary format handler is inactive; cannot execute wsl.exe in this WSL instance') from err
        raise
    output = [bytearray(), bytearray()]
    total = 0
    lock = threading.Lock()
    failed = threading.Event()
    problems = []

    def reader(stream, index):
        nonlocal total
        try:
            while not failed.is_set():
                chunk = stream.read(65536)
                if not chunk:
                    return
                with lock:
                    if total + len(chunk) > max_bytes:
                        problems.append(ValueError('Exporter output exceeded maximum allowed size during read'))
                        failed.set()
                        return
                    output[index].extend(chunk)
                    total += len(chunk)
        except Exception as error:
            with lock:
                problems.append(error)
                failed.set()

    threads = [threading.Thread(target=reader, args=(stream, index), daemon=True)
               for index, stream in enumerate((proc.stdout, proc.stderr))]
    try:
        for thread in threads:
            thread.start()
        while proc.poll() is None or any(thread.is_alive() for thread in threads):
            if failed.is_set():
                raise problems[0]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'wsl --system exporter exceeded {timeout_s}s')
            failed.wait(min(0.02, remaining))
        if problems:
            raise problems[0]
        return proc.returncode, bytes(output[0]), bytes(output[1])
    finally:
        failed.set()
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=2)
        for stream in (proc.stdout, proc.stderr):
            stream.close()
        for thread in threads:
            if thread.ident is not None:
                thread.join(2)


def snapshot_wsl_root_tasks(
    local_ns_inode: Union[int, str, None],
    owned_processes: Mapping[str, Any],
    *,
    distro: str = DEFAULT_DISTRO,
    wsl_path: Optional[Union[str, Path]] = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_output_bytes: int = DEFAULT_MAX_BYTES,
    executor: Optional[Callable[[Sequence[str], float], Tuple[int, bytes, bytes]]] = None,
) -> dict[str, Any]:
    """Execute host-root procfs task snapshot and return strictly verified task mappings.

    Parameters:
      local_ns_inode: Inode of target PID namespace (e.g. 4026532221).
                      Pass None or 'auto' to detect from /proc/self/ns/pid.
      owned_processes: Mapping of role -> {'pid': int, 'start_ticks': int}
                       or local_pid -> start_ticks.
      distro: WSL distro name ('Ubuntu-22.04').
      wsl_path: Path to wsl.exe binary.
      timeout_s: Timeout in seconds for wsl.exe invocation.
      max_output_bytes: Upper bound on accepted output bytes.
      executor: Optional mock callable (cmd, timeout) -> (rc, stdout_bytes, stderr_bytes).

    Returns:
      Validated snapshot dictionary with:
        - root_pid_ns: int
        - target_pid_ns: int
        - lsns_evidence: dict
        - leaders: dict of local_pid -> leader task record (with global_tid, global_tgid, etc.)
        - tasks: full list of task records
        - tasks_by_local_tid: dict mapping local_tid -> task record
        - tasks_by_global_tid: dict mapping global_tid -> task record
    """
    if local_ns_inode is None or local_ns_inode == 'auto':
        target_inode = detect_local_pid_ns_inode()
    elif isinstance(local_ns_inode, bool):
        raise ValueError(f'Invalid local_ns_inode (bool is not an inode): {local_ns_inode}')
    elif isinstance(local_ns_inode, str):
        # Exact full-match digits only: 'abc123' or '12x' must not parse.
        if not re.fullmatch(r'\d+', local_ns_inode):
            raise ValueError(f'Invalid local_ns_inode string: {local_ns_inode}')
        target_inode = int(local_ns_inode)
    elif type(local_ns_inode) is int:
        target_inode = local_ns_inode
    else:
        raise ValueError('local_ns_inode must be a positive integer or decimal string')

    if target_inode <= 0:
        raise ValueError(f'Invalid target namespace inode: {target_inode}')

    owners_map = normalize_owned_processes(owned_processes)
    if not owners_map:
        raise ValueError('owned_processes must not be empty')

    sh_script = build_exporter_sh_script(target_inode)
    b64_script = base64.b64encode(sh_script.encode('utf-8')).decode('ascii')
    cmd_wrapper = f'echo "{b64_script}" | base64 -d | sh'

    wsl_bin = str(wsl_path) if wsl_path is not None else find_wsl_binary()

    cmd = [
        wsl_bin,
        '-d', distro,
        '--system',
        '-u', 'root',
        'sh', '-c', cmd_wrapper,
    ]

    if executor is not None:
        rc, out_bytes, err_bytes = executor(cmd, timeout_s)
    else:
        rc, out_bytes, err_bytes = _run_bounded(cmd, timeout_s, max_output_bytes)

    if rc != 0:
        err_msg = err_bytes.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'wsl --system exporter failed with code {rc}: {err_msg}')

    if len(out_bytes) > max_output_bytes:
        raise ValueError(
            f'Exporter output exceeded maximum allowed size ({len(out_bytes)} > {max_output_bytes})'
        )

    output_text = out_bytes.decode('utf-8', errors='replace')
    return parse_exporter_output(output_text, target_inode, owners_map)
