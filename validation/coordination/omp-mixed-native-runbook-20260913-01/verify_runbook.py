"""Read-only preflight checker for the OMP MIXED native perf runbook.

Pure Python standard library, unittest-based. Reads only files inside this
repository. It never starts or stops a process, never loads native code,
never touches WSL, ROS, firmware, models, UE or MATLAB, and writes nothing.
Exit code 0 means every check passed; failures are ordinary unittest failures.

Run: python -B validation/coordination/omp-mixed-native-runbook-20260913-01/verify_runbook.py
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNBOOK = json.loads((HERE / 'runbook.json').read_text(encoding='utf-8'))

HEX64 = re.compile(r'^[0-9a-f]{64}$')
MIXED_TASK = 'xy_velocity_z_position_yaw_v1'
PERF_LIBRARY_PATH = '/root/wksim-perf-python-admission-apup9qju/libwksim_perf_stream.so'
PERF_LIBRARY_SHA = '37d9651282bce0da059828056796683b94e780461f7918e60c3e1e77e2130020'


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(argv):
    """Map '--flag' to its following value for value flags; True for bare flags."""
    result = {}
    index = 0
    while index < len(argv):
        token = argv[index]
        assert token.startswith('--'), token
        if index + 1 < len(argv) and not argv[index + 1].startswith('--'):
            result[token] = argv[index + 1]
            index += 2
        else:
            result[token] = True
            index += 1
    return result


class RunbookJsonShapeTests(unittest.TestCase):
    def test_schema_and_classification(self):
        self.assertEqual(RUNBOOK['schema'], 'wksim.omp_mixed_native_runbook.v1')
        self.assertEqual(RUNBOOK['classification'], 'diagnostic_only')
        self.assertIs(RUNBOOK['formal_evidence'], False)

    def test_all_sha256_fields_well_formed(self):
        def walk(node, trail=()):
            if isinstance(node, dict):
                for key, value in node.items():
                    if (key.endswith('sha256') or key == 'sha256') and value is not None:
                        if isinstance(value, str):
                            self.assertRegex(value, HEX64, msg='.'.join(trail + (key,)))
                        elif isinstance(value, dict):
                            for inner_key, inner in value.items():
                                self.assertRegex(inner, HEX64,
                                                 msg='.'.join(trail + (key, inner_key)))
                    else:
                        walk(value, trail + (key,))
            elif isinstance(node, list):
                for item in node:
                    walk(item, trail)
        walk(RUNBOOK)

    def test_required_sections_present(self):
        for key in ('authoring_host', 'linux_target', 'identity', 'precheck', 'environment',
                    'main_command', 'runner_lifecycle', 'post_run', 'failure_classification',
                    'source_sha256', 'gaps'):
            self.assertIn(key, RUNBOOK)
        self.assertGreaterEqual(len(RUNBOOK['gaps']), 1)


class RepoSourcePinTests(unittest.TestCase):
    def test_every_pinned_repo_file_matches(self):
        for name, expected in RUNBOOK['source_sha256'].items():
            path = REPO / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(sha256(path), expected, name)


class IdentityBindingTests(unittest.TestCase):
    """Runbook identities must equal the authoritative constants in repo source."""

    def test_manifest_shas_match_ap_mixed_candidate_constants(self):
        tree = ast.parse((REPO / 'tools/ap_mixed_candidate.py').read_text(encoding='utf-8'))
        constants = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name):
                try:
                    constants[node.targets[0].id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    pass
        identity = RUNBOOK['identity']
        self.assertEqual(identity['ap_mixed_manifest']['sha256'], constants['FINAL_AP_SHA'])
        self.assertEqual(identity['control_manifest']['sha256'], constants['FINAL_CONTROL_SHA'])
        self.assertEqual(identity['message_manifest']['sha256'], constants['FINAL_MESSAGE_SHA'])

    def test_px4_and_model_match_profile_catalog(self):
        catalog = json.loads((REPO / 'Simulator/wksim_runtime/joint-profiles.json')
                             .read_text(encoding='utf-8'))
        rows = {row['id']: row for row in catalog['profiles']}
        legacy = rows['joint_quad_dds_v1']
        mixed = rows['joint_quad_dds_mixed_pv_v1']
        identity = RUNBOOK['identity']
        self.assertEqual(identity['px4_manifest']['path'], mixed['manifests']['px4']['path'])
        self.assertEqual(identity['px4_manifest']['sha256'], mixed['manifests']['px4']['sha256'])
        self.assertEqual(identity['px4_manifest']['path'], legacy['manifests']['px4']['path'])
        self.assertEqual(identity['model_library']['path'], legacy['model_library'])
        self.assertEqual(mixed['manifest_kinds'],
                         {'ap': 'ap_mixed_v1', 'px4': 'wksim_build_v1', 'control': 'joint_control_v1'})

    def test_perf_library_pin(self):
        library = RUNBOOK['identity']['perf_library']
        self.assertEqual(library['path'], PERF_LIBRARY_PATH)
        self.assertEqual(library['sha256'], PERF_LIBRARY_SHA)
        recorder = RUNBOOK['source_sha256'][
            'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c']
        header = RUNBOOK['source_sha256'][
            'validation/coordination/ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h']
        self.assertEqual(library['source_sha256']['wksim_perf_stream.c'], recorder)
        self.assertEqual(library['source_sha256']['wksim_perf_stream.h'], header)

    def test_historical_identities_not_used(self):
        current = {RUNBOOK['identity'][key]['sha256'] for key in
                   ('ap_mixed_manifest', 'control_manifest', 'message_manifest')}
        argv_text = ' '.join(RUNBOOK['main_command']['argv'])
        for stale in ('25edbf81', 'a6a17b42', '3d04d53a', 'd9fdfc74'):
            self.assertNotIn(stale, argv_text)
        self.assertEqual(len(current), 3)


class MainCommandTests(unittest.TestCase):
    def setUp(self):
        self.command = RUNBOOK['main_command']
        self.flags = pairs(self.command['argv'])
        self.runner_source = (REPO / 'tools/run_joint_flight.py').read_text(encoding='utf-8')

    def test_argv_uses_only_real_runner_flags(self):
        for flag in self.flags:
            name = flag[2:]
            literal = ("'--" + name + "'") in self.runner_source
            loop_built = ("'" + name + "'") in self.runner_source
            self.assertTrue(literal or loop_built, flag)

    def test_task_profile_is_mixed(self):
        self.assertEqual(self.flags['--task-profile'], MIXED_TASK)
        task_source = (REPO / 'tools/mixed_control_task.py').read_text(encoding='utf-8')
        self.assertIn("PROFILE = 'xy_velocity_z_position_yaw_v1'", task_source)

    def test_perf_pair_pinned_and_adjacent(self):
        argv = self.command['argv']
        index = argv.index('--perf-library')
        self.assertEqual(argv[index + 1], PERF_LIBRARY_PATH)
        self.assertEqual(argv[index + 2], '--perf-library-sha256')
        self.assertEqual(argv[index + 3], PERF_LIBRARY_SHA)

    def test_manifest_pairs_match_identity(self):
        identity = RUNBOOK['identity']
        for flag_base, key in (('--ap-mixed', 'ap_mixed_manifest'),
                               ('--control', 'control_manifest'),
                               ('--message', 'message_manifest')):
            self.assertEqual(self.flags[flag_base + '-manifest'], identity[key]['path'])
            self.assertEqual(self.flags[flag_base + '-sha256'], identity[key]['sha256'])

    def test_forbidden_flags_absent(self):
        for flag in self.command['forbidden_flags']:
            self.assertNotIn(flag, self.flags)
        self.assertNotIn('--px4-manifest', self.flags)
        self.assertTrue(self.flags.get('--async-model-evidence') is True)

    def test_every_forbidden_flag_is_documented_as_absent_or_nonexistent(self):
        retired = ('--manager-gc-freeze', '--early-work-timing', '--owned-scheduling-snapshot')
        for flag in retired:
            self.assertIn(flag, self.command['forbidden_flags'])
            self.assertNotIn("'" + flag[2:] + "'", self.runner_source)

    def test_timeout_signals_own_group_only(self):
        timeout = self.command['timeout']
        self.assertEqual(timeout['signal'], 'TERM')
        self.assertEqual(timeout['scope'], 'own process group only')
        self.assertGreater(timeout['seconds'], self.command['internal_bounds']['wall_limit_seconds'])
        self.assertGreater(timeout['kill_after_seconds'], 0)


class PrecheckProtocolTests(unittest.TestCase):
    def test_markers_match_executed_precedent(self):
        precedent = REPO / ('validation/coordination/'
                            'three-deepseek-main-acceptance-20260913-01/precheck.py')
        tree = ast.parse(precedent.read_text(encoding='utf-8'))
        markers = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'markers'
                    for target in node.targets):
                markers = list(ast.literal_eval(node.value))
        self.assertIsNotNone(markers)
        self.assertEqual(RUNBOOK['precheck']['markers'], markers)

    def test_embedded_script_is_the_precheck_script(self):
        script = RUNBOOK['precheck']['script']
        tree = ast.parse(script)
        markers = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == 'markers'
                    for target in node.targets):
                markers = list(ast.literal_eval(node.value))
        self.assertEqual(markers, RUNBOOK['precheck']['markers'])
        self.assertIn('/proc/sys/kernel/random/boot_id', script)
        self.assertIn('/proc/uptime', script)

    def test_distros_freshness_and_empty_found(self):
        precheck = RUNBOOK['precheck']
        self.assertEqual(precheck['distros'], ['Ubuntu-22.04', 'RflySim-20.04'])
        self.assertEqual(precheck['freshness_seconds'], 60)
        self.assertIs(precheck['found_must_be_empty'], True)
        self.assertIs(precheck['same_boot_required'], True)
        self.assertEqual(precheck['invoke_per_distro'][0], 'wsl.exe')


class InvariantTests(unittest.TestCase):
    def test_rate_invariants_unchanged_in_source(self):
        rate = (REPO / 'Simulator/wksim_runtime/joint_rate.py').read_text(encoding='utf-8')
        self.assertIn('LATE_LIMIT_NS=100_000_000', rate)
        self.assertIn('RATES=(0.5,1.0)', rate)
        self.assertIn('max(ideal', rate)
        clock = (REPO / 'Simulator/wksim_runtime/scene_clock.py').read_text(encoding='utf-8')
        self.assertIn('STEP_NS', clock)
        self.assertIn('1_000_000', clock)
        self.assertIn('MACRO_TICKS', clock)

    def test_finalize_runs_before_cleanup_children(self):
        source = (REPO / 'tools/run_joint_flight.py').read_text(encoding='utf-8')
        finalize = source.index('\n            finalize_perf_capture(result, live, perf_capture, rate)')
        cleanup = source.index('\n        cleanup_children(result, children, child_specs,')
        self.assertLess(finalize, cleanup)

    def test_marker_lookup_inside_try_and_synthesized(self):
        """c3d4916 (OMP review P2-1): no KeyError may escape the finally."""
        source = (REPO / 'tools/run_joint_flight.py').read_text(encoding='utf-8')
        body = source[source.index('def finalize_perf_capture'):
                      source.index('def candidate_environment')]
        try_at = body.index('\n    try:')
        lookup = body.index("marker = result.get('perf_switch_capture')")
        except_at = body.index('except BaseException')
        synth = body.index("result['perf_switch_capture'] = marker")
        self.assertLess(try_at, lookup)
        self.assertLess(except_at, synth)
        self.assertIn('marker is missing or malformed', body)

    def test_perf_capture_sources_pinned_in_runner(self):
        source = (REPO / 'tools/run_joint_flight.py').read_text(encoding='utf-8')
        for name in ('Simulator/wksim_runtime/perf_capture.py',
                     'Simulator/wksim_runtime/evidence.py',
                     'ds-perf-stream-recorder-20260913-01/wksim_perf_stream.c',
                     'ds-perf-stream-recorder-20260913-01/wksim_perf_stream.h',
                     'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'):
            self.assertIn(name, source)

    def test_formal_gate_rejects_perf_marker(self):
        profile = (REPO / 'Simulator/wksim_runtime/joint_profile.py').read_text(encoding='utf-8')
        self.assertIn("'rate_timing_probe', 'group_work_timing', 'perf_switch_capture'", profile)
        self.assertIn("'Formal mixed/PV evidence cannot include '+marker", profile)

    def test_adapter_kernel_and_owner_contract(self):
        adapter = (REPO / 'Simulator/wksim_runtime/perf_capture.py').read_text(encoding='utf-8')
        self.assertIn("TESTED_KERNEL_RELEASE = '6.6.87.2-microsoft-standard-WSL2'", adapter)
        self.assertIn('threading.get_native_id', adapter)
        self.assertIn(RUNBOOK['linux_target']['kernel_release'], adapter)


class ConsumerCommandTests(unittest.TestCase):
    def setUp(self):
        self.consumer = RUNBOOK['post_run']['consumer']
        self.argv = self.consumer['argv']

    def test_consumer_source_identity(self):
        path = REPO / ('validation/coordination/'
                       'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py')
        self.assertIn(str(path.relative_to(REPO)).replace('\\', '/'), self.argv[2])
        self.assertEqual(sha256(path), RUNBOOK['source_sha256'][
            'validation/coordination/ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'])

    def test_consumer_flags(self):
        self.assertIn('--require-kernel-counter', self.argv)
        windows = self.argv.index('--windows')
        self.assertTrue(self.argv[windows + 1].endswith('/perf-windows.json'))
        output = self.argv.index('--output')
        self.assertTrue(self.argv[output + 1].endswith('/perf-decoded.json'))
        self.assertTrue(self.consumer['output_must_not_exist'])

    def test_consumer_actually_implements_flags(self):
        source = (REPO / 'validation/coordination/'
                  'ds-perf-stream-consumer-20260913-01/perf_stream_consumer.py'
                  ).read_text(encoding='utf-8')
        self.assertIn("'--require-kernel-counter'", source)
        self.assertIn("'--windows'", source)
        self.assertIn('kernel_loss_counter_nonzero', source)

    def test_exit_code_documentation(self):
        self.assertEqual(set(self.consumer['exit_codes']), {'0', '3', '4'})

    def test_audit_order_consumer_first(self):
        order = RUNBOOK['post_run']['audit_order']
        self.assertIn('consumer', order[0])
        self.assertIn('audit_mixed_control', order[1])


class EnvironmentTests(unittest.TestCase):
    def test_timing_probes_must_be_unset(self):
        unset = RUNBOOK['environment']['must_be_unset']
        self.assertIn('WKSIM_JOINT_RATE_TIMING_PROBE', unset)
        self.assertIn('WKSIM_JOINT_CPU_TIMING', unset)
        probe = (REPO / 'Simulator/wksim_runtime/joint_rate_probe.py').read_text(encoding='utf-8')
        self.assertIn('WKSIM_JOINT_RATE_TIMING_PROBE', probe)


class RunbookMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.text = (HERE / 'runbook.md').read_text(encoding='utf-8')

    def test_markdown_carries_the_pins(self):
        for needle in (PERF_LIBRARY_PATH, PERF_LIBRARY_SHA, MIXED_TASK,
                       '--require-kernel-counter', '--windows', 'perf-decoded.json',
                       '1e6250eff8873d6b2e52017b613c223ac29f8260fdf92aac2cf0c7cdcc6ce94c',
                       '6fe8c0b30775a9ba83407302f602d0785876d307e5f1cb746afa3bf316cf5e7e',
                       '29969da0702451e3fc6f1de40bc301a67284c4e7d5fae8f88c64773d27a96219',
                       'd7e905b35250d184e185ada70e3fe43f0223f1c605832d81c3c58eeb123d4cb6',
                       'perf_switch_capture', '100ef1a', '386f713', 'c3d4916'):
            self.assertIn(needle, self.text)

    def test_markdown_documents_gaps_and_stop(self):
        self.assertIn('缺口', self.text)
        self.assertIn('停止', self.text)


class GitStateTests(unittest.TestCase):
    """HEAD moves under parallel sessions; runtime truth is pinned by file SHA."""

    def test_head_resolves_and_drift_is_only_reported(self):
        head = (REPO / '.git/HEAD').read_text(encoding='utf-8').strip()
        if head.startswith('ref:'):
            ref = head.split(' ', 1)[1]
            ref_path = REPO / '.git' / ref
            if ref_path.is_file():
                commit = ref_path.read_text(encoding='utf-8').strip()
            else:
                packed = (REPO / '.git/packed-refs').read_text(encoding='utf-8')
                commit = next(line.split(' ', 1)[0] for line in packed.splitlines()
                              if line.endswith(' ' + ref))
        else:
            commit = head
        self.assertRegex(commit, re.compile(r'^[0-9a-f]{40}$'))
        recorded = RUNBOOK['authoring_host']
        self.assertRegex(recorded['head_at_dispatch'], re.compile(r'^[0-9a-f]{40}$'))
        self.assertRegex(recorded['head_at_authoring'], re.compile(r'^[0-9a-f]{40}$'))
        self.assertEqual(recorded['architecture_ancestor_exit_code'], 0)
        if commit != recorded['head_at_authoring']:
            print(f'NOTE: HEAD drifted to {commit} since authoring; '
                  'file-SHA pins remain the authoritative gate')


if __name__ == '__main__':
    unittest.main(verbosity=2)
