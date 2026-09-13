"""Prepare v3 of the owned-scheduling-snapshot wiring candidate (baseline 08e20642).

v3 closes the remaining runtime-boundary gaps found in main review:

1. Success-path ordering: the baseline closes model workers by hand
   (stdin.close/wait near line 1112) BEFORE the ExitStack unwinds, so LIFO alone
   never guaranteed the after snapshot precedes that teardown. v3 calls the
   after capture ONCE right after the timed segment closes (before
   clock.request(stop) and the manual worker teardown); the ExitStack callback
   stays only as the exception-path fallback, and an explicit once-state
   (after_attempted) prevents any duplicate/overwrite.
2. Targets are frozen once at 'before' with the minimal identity
   (pid/pgid/start_ticks) plus the real manager identity; 'after' reuses the
   frozen file and re-verifies its pinned hash - it never regenerates from the
   mutable result['children'] and never admits new targets.
3. Metadata honesty: a phase enters verified metadata only when its capture
   actually validated (host boot matched, no exception); a raw file left behind
   by a failed validation is retained but marked validated=False; a hash failure
   records metadata_error and fabricates nothing.
4. The helper pin is checked BEFORE import, and the imported module's origin
   must resolve to the pinned path.

Ten marker-delimited blocks at unique anchors; stripping them restores the
baseline byte-for-byte. Evidence only; never applied to the runtime. Switch off
means zero import, zero /proc reads, zero record side effects; no physical gate
or scheduling is changed.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / 'baseline-run_joint_flight-08e20642.py.txt'
CANDIDATE = HERE / 'run_joint_flight-owned-snapshot-candidate-v3.py.txt'
REPORT = HERE / 'prepare-report-v3.json'
BASELINE_SHA = '08e20642f82f9052284f3054ae91c57d5d7e77017fb996e11d748bb98a86db99'
HELPER = Path(__file__).resolve().parents[3] / 'tools/capture_owned_scheduling.py'
HELPER_SHA = hashlib.sha256(HELPER.read_bytes()).hexdigest()
if HELPER_SHA != 'a3f3baddbe6e77bed5727e840ef6a4c7066291ce5f50c706f848e7b1716f8e9e':
    raise ValueError('reviewed helper pin differs; re-review before preparing v3')

MARK_BEGIN = '# --- owned-snapshot-wiring begin %d (remove marked blocks to restore baseline) ---'
MARK_END = '# --- owned-snapshot-wiring end %d ---'


def block(number, indent, body, leading_blank=False):
    lines = [indent + MARK_BEGIN % number]
    if leading_blank:
        lines.append('')
    lines += [indent + line if line else '' for line in body.splitlines()]
    lines.append(indent + MARK_END % number)
    return '\n'.join(lines) + '\n'


BLOCK1 = block(1, '', '''OWNED_SNAPSHOT_HELPER_SHA256 = '%s'
OWNED_SNAPSHOT_HELPER_PARAMS = ('children', 'output', 'phase', 'proc_root')
OWNED_SNAPSHOT_CONFLICTS = ('pause_probe', 'repeat_paused_clock', 'scene_lifecycle',
                            'scene_lease_loss', 'native_state_trace',
                            'probe_land_freshness', 'model_promotion_flight',
                            'early_work_timing', 'planner_release_proof',
                            'rate_spin_cpu_timing')


def validate_owned_snapshot_request(task_profile, requested, timing_probe,
                                    lifecycle_conflicts=False):
    """Gate for --owned-scheduling-snapshot: parent-probe MIXED diagnostics only.

    Raises before check_isolation, any temporary directory, or any child. With
    the switch off there is no import, no /proc read and no record side effect.
    """
    if type(requested) is not bool:
        raise ValueError('owned-scheduling snapshot flag must be a plain bool')
    if not requested:
        return
    if task_profile != MIXED_PROFILE or not timing_probe:
        raise ValueError('--owned-scheduling-snapshot requires the MIXED profile and '
                         'WKSIM_JOINT_RATE_TIMING_PROBE=1 (parent timing probe)')
    if lifecycle_conflicts:
        raise ValueError('--owned-scheduling-snapshot stands alone: no pause/scene/'
                         'DDS-recovery/model-promotion/planner/spin/early-work combination')


def validate_owned_snapshot_helper(helper_sha256, init_parameters=None):
    """Pin check BEFORE import; interface check after origin is verified."""
    if helper_sha256 != OWNED_SNAPSHOT_HELPER_SHA256:
        raise ValueError('capture helper differs from the reviewed pin')
    if init_parameters is not None and not set(OWNED_SNAPSHOT_HELPER_PARAMS) <= set(init_parameters):
        raise ValueError('capture helper interface differs')


def validate_owned_snapshot_helper_origin(imported_file, expected_path):
    """The imported helper module must resolve to the pinned path."""
    if Path(imported_file).resolve() != Path(expected_path).resolve():
        raise ValueError('capture helper imported from an unexpected origin')


def read_boot_id(proc_root):
    """The non-empty current boot id; raises before any target PID is touched."""
    from capture_owned_scheduling import ProcReader
    text = ProcReader(Path(proc_root)).read_text('sys', 'kernel', 'random', 'boot_id')
    boot = text.strip() if text else None
    if not boot:
        raise ValueError('boot_id unavailable: refusing to touch target PIDs')
    return boot''' % HELPER_SHA, leading_blank=True)

BLOCK2 = block(2, '    ', '''owned_snapshot = getattr(args, 'owned_scheduling_snapshot', False)
owned_conflicts = (any(getattr(args, name, False) for name in OWNED_SNAPSHOT_CONFLICTS)
                   or bool(getattr(args, 'dds_loss', None)))
validate_owned_snapshot_request(args.task_profile, owned_snapshot, timing_probe,
                                owned_conflicts)
if owned_snapshot:
    # Pin BEFORE import, then verify import origin and the real interface: a
    # missing, modified or wrong-origin helper never burns an experiment at
    # capture time. With the switch off none of this is imported or read.
    helper_path = REPO / 'tools/capture_owned_scheduling.py'
    validate_owned_snapshot_helper(digest(helper_path))
    import inspect
    import capture_owned_scheduling as owned_helper_module
    validate_owned_snapshot_helper_origin(owned_helper_module.__file__, helper_path)
    from capture_owned_scheduling import OwnedSchedulingCapture
    validate_owned_snapshot_helper(
        digest(helper_path),
        list(inspect.signature(OwnedSchedulingCapture.__init__).parameters))''')

BLOCK3 = block(3, '    ', '''if owned_snapshot:
    result['owned_scheduling'] = dict(classification='diagnostic_only',
                                      full_acceptance=False, initialized=False,
                                      before=None, after=None, boot_id=None,
                                      helper='tools/capture_owned_scheduling.py')''')

BLOCK4 = block(4, '    ', '''if owned_snapshot:
    sources += ['tools/capture_owned_scheduling.py']''')

BLOCK5 = block(5, ' ' * 12, '''if owned_snapshot:
    # One snapshot after all children/model initialization, before the GC
    # freeze and the physics loop; never inside the 8ms pacing loop. The
    # non-empty current boot is checked and pinned before any target PID is
    # read; the after capture never re-accepts a changed boot. The helper was
    # pin-checked, origin-verified and imported above, before any child.
    def owned_snapshot_capture(phase):
        boot = read_boot_id('/proc')
        meta = result['owned_scheduling']
        stored = meta['boot_id']
        if phase == 'before':
            meta['boot_id'] = boot
        elif stored != boot:
            meta['after_error'] = 'boot changed: %r != %r' % (stored, boot)
            return
        targets_path = live / 'owned-scheduling-targets.json'
        if phase == 'before':
            # Frozen once: minimal identity (pid/pgid/start_ticks) plus the real
            # manager identity - never rebuilt from mutable result['children'].
            targets = {role: {'identity': dict(entry['identity'])}
                       for role, entry in result['children'].items()}
            manager_identity = json_identity(os.getpid())
            if manager_identity is None:
                raise ValueError('manager identity unavailable')
            targets['manager'] = {'identity': manager_identity}
            payload = (json.dumps(targets, indent=2, allow_nan=False) + '\\n').encode()
            try:
                with targets_path.open('xb') as stream:  # frozen exclusively
                    stream.write(payload)
            except FileExistsError:
                if targets_path.read_bytes() != payload:
                    raise ValueError('targets file differs from history')
            meta['targets_sha256'] = digest(targets_path)
        else:
            if meta.get('targets_sha256') is None or not targets_path.is_file():
                raise ValueError('frozen targets missing for the after capture')
            if digest(targets_path) != meta['targets_sha256']:
                raise ValueError('frozen targets changed between captures')
        output = live / ('owned-scheduling-%s.json' % phase)
        captured = OwnedSchedulingCapture(targets_path, output, phase=phase).capture()
        if captured['host']['boot_id'] != boot:
            raise ValueError('capture host boot differs from the pinned boot')
        meta[phase] = output.name
        meta[phase + '_validated'] = True  # only a validated capture earns this

    def owned_snapshot_after_once():
        meta = result['owned_scheduling']
        if meta.get('after_attempted'):
            return  # explicit once-state: never duplicate, never overwrite
        meta['after_attempted'] = True
        try:
            owned_snapshot_capture('after')
        except Exception as error:
            # Ordinary capture failure is recorded; cancellation propagates.
            meta['after_error'] = repr(error)

    result['owned_scheduling']['initialized'] = True
    try:
        owned_snapshot_capture('before')
    except Exception as error:
        # An ordinary diagnostic failure is recorded; cancellation
        # (KeyboardInterrupt/SystemExit/GeneratorExit) propagates.
        result['owned_scheduling']['before_error'] = repr(error)''')

BLOCK6 = block(6, ' ' * 12, '''if owned_snapshot:
    # Exception-path fallback only: the success path already called
    # owned_snapshot_after_once() after the timed segment closed. Registered
    # LAST, so on an error unwind ExitStack LIFO runs it before teardown.
    # If physics.connect() raised, this registration never happened and the
    # result honestly keeps after=None.
    resources.callback(owned_snapshot_after_once)''')

BLOCK7 = block(7, ' ' * 8, '''if owned_snapshot:
    meta = result['owned_scheduling']
    try:
        refreshed = {}
        for phase in ('before', 'after'):
            path = live / ('owned-scheduling-%s.json' % phase)
            validated = bool(meta.get(phase + '_validated'))
            if path.is_file():
                refreshed[phase] = dict(file=path.name, sha256=digest(path),
                                        validated=validated)
                if not validated:
                    # Retained raw, never presented as verified evidence.
                    refreshed[phase]['note'] = 'raw file retained; capture did not validate'
            elif validated:
                raise ValueError('validated %s capture file is missing' % phase)
            else:
                refreshed[phase] = None
        helper_sha = result['source_sha256'].get('tools/capture_owned_scheduling.py')
        targets_path = live / 'owned-scheduling-targets.json'
        targets_sha = digest(targets_path) if targets_path.is_file() else None
    except Exception as error:
        # Metadata collection failure is a diagnostic error: nothing new is
        # claimed captured and the business error is never masked.
        meta['metadata_error'] = repr(error)
    else:
        meta.update(refreshed)
        meta['helper_sha256'] = helper_sha
        meta['targets_sha256'] = targets_sha
if owned_snapshot and result['status'] == 'pass':
    result['status'] = 'observed'
''')

BLOCK8 = block(8, '    ', '''runner.add_argument('--owned-scheduling-snapshot', action='store_true',
                    help='Diagnostic only: one read-only thread scheduling snapshot of the '
                         'owned manager and children after init/before GC freeze and physics, '
                         'and one after the timed segment closes (ExitStack fallback on error); '
                         'requires MIXED and the parent timing probe, stands alone; '
                         'never formal evidence')''')

BLOCK9 = block(9, ' ' * 8, '''if args.owned_scheduling_snapshot:
    owned_conflicts = (any(getattr(args, name, False)
                           for name in OWNED_SNAPSHOT_CONFLICTS)
                       or bool(getattr(args, 'dds_loss', None)))
    try:
        validate_owned_snapshot_request(args.task_profile, True,
                                        timing_probe_enabled(), owned_conflicts)
    except ValueError as error:
        parser.error(str(error))''')

BLOCK10 = block(10, ' ' * 12, '''if owned_snapshot:
    # Success path: the after capture runs ONCE here - after the timed segment
    # closed, before clock.request(stop) and before the manual model
    # stdin.close()/wait() teardown below. The once-state makes the ExitStack
    # fallback a no-op on this path.
    owned_snapshot_after_once()''')

ANCHOR1 = "    from rate_spin_cpu_probe import JointRateSpinCpuProbe  # Validate before any native child.\n"
ANCHOR2 = "    validate_spin_cpu_request(args.task_profile, spin_cpu, timing_probe)\n"
ANCHOR3 = ("    if diagnostic_identity is not None:\n"
           "        result['rate_timing_probe'] = dict(diagnostic_identity)\n")
ANCHOR4 = "    result['source_sha256'] = {name:digest(REPO/name) for name in sources}\n"
ANCHOR5 = "            if manager_gc is not None:\n                manager_gc.prepare("
ANCHOR6 = "            physics.connect()\n"
ANCHOR7 = "        result['flight_completed'] = result['status']=='pass'\n"
ANCHOR8 = ("    runner.add_argument('--early-work-timing', action='store_true',\n"
           "                        help='Opt-in diagnostic: bounded early manager work segmentation for the first '\n"
           "                             '10 wall seconds from the first rate anchor (PV/MIXED only; requires '\n"
           "                             'WKSIM_JOINT_CPU_TIMING=1 and WKSIM_JOINT_RATE_TIMING_PROBE=1)')\n")
ANCHOR9 = ("            if (os.environ.get('WKSIM_JOINT_CPU_TIMING') != '1'\n"
           "                    or os.environ.get('WKSIM_JOINT_RATE_TIMING_PROBE') != '1'):\n"
           "                parser.error('--early-work-timing requires WKSIM_JOINT_CPU_TIMING=1 and '\n"
           "                             'WKSIM_JOINT_RATE_TIMING_PROBE=1')\n")
ANCHOR10 = ("            if rate is not None:\n"
            "                rate.check_boundary(clock.tick)\n"
            "                rate.close_segment('completed', clock.tick)\n"
            "                result['rate'] = rate.last_summary\n")

INSERTIONS = (
    (ANCHOR1, BLOCK1, True),
    (ANCHOR2, BLOCK2, True),
    (ANCHOR3, BLOCK3, True),
    (ANCHOR4, BLOCK4, False),
    (ANCHOR5, BLOCK5, False),
    (ANCHOR6, BLOCK6, True),
    (ANCHOR7, BLOCK7, False),
    (ANCHOR8, BLOCK8, True),
    (ANCHOR9, BLOCK9, True),
    (ANCHOR10, BLOCK10, True),
)


def strip_marked(text):
    out = []
    skipping = None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if skipping is None:
            if stripped.startswith('# --- owned-snapshot-wiring begin'):
                skipping = int(stripped.split('begin', 1)[1].strip().split(' ', 1)[0])
            else:
                out.append(line)
        elif stripped == MARK_END % skipping:
            skipping = None
    if skipping is not None:
        raise ValueError('unterminated marked block')
    return ''.join(out)


def main():
    baseline = BASELINE.read_bytes()
    sha = hashlib.sha256(baseline).hexdigest()
    if sha != BASELINE_SHA:
        raise ValueError('baseline SHA differs from the pinned 08e20642 runner')
    text = baseline.decode('utf-8')
    for index, (anchor, insertion, after) in enumerate(INSERTIONS, 1):
        if text.count(anchor) != 1:
            raise ValueError('anchor %d is not unique in the baseline' % index)
        text = text.replace(anchor, anchor + insertion if after else insertion + anchor, 1)
    candidate = text.encode('utf-8')
    restored = strip_marked(candidate.decode('utf-8')).encode('utf-8')
    if restored != baseline:
        raise ValueError('stripping marked blocks does not restore the baseline')
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    with CANDIDATE.open('xb') as stream:
        stream.write(candidate)
    report = {
        'schema': 'wksim.owned-snapshot-wiring-prepare.v3',
        'classification': 'diagnostic_only', 'full_acceptance': False,
        'supersedes': 'run_joint_flight-owned-snapshot-candidate-v2.py.txt (v2 retained)',
        'baseline_sha256': sha,
        'candidate_sha256': candidate_sha,
        'helper_sha256': HELPER_SHA,
        'v3_review_fixes': [
            'success path calls the after capture once after the timed segment closes, '
            'before clock stop and the manual worker teardown; ExitStack callback is the '
            'exception-path fallback under an explicit after_attempted once-state',
            "targets frozen once at 'before' with minimal identity + real manager identity; "
            "'after' reuses the frozen file and re-verifies its pinned hash, never regenerates",
            'only a validated capture enters verified metadata; raw failed-validation files '
            'are retained with validated=false; hash failures record metadata_error',
            'helper pin checked before import; imported module origin must equal the pinned path',
        ],
        'strip_marked_restores_baseline': True,
        'not_applied_to_runtime': True,
    }
    with REPORT.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'candidate_sha256': candidate_sha, 'restores_baseline': True}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
