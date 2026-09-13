"""v3 fixture verification for the owned-snapshot wiring candidate (never applied).

Only the v3 review points are tested, against the REAL candidate blocks
(AST-extracted and executed with scripted seams; a real ExitStack drives the
fallback). No flight/model/ROS/build/native; nothing is scheduled.
"""
import ast
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import prepare_candidate_v3 as prep  # noqa: E402

CANDIDATE = HERE / 'run_joint_flight-owned-snapshot-candidate-v3.py.txt'


def candidate_text():
    return CANDIDATE.read_text(encoding='utf-8')


def extract_if_with_function(name):
    parsed = ast.parse(candidate_text())
    for node in ast.walk(parsed):
        if isinstance(node, ast.If) and any(
                isinstance(sub, ast.FunctionDef) and sub.name == name
                for sub in ast.walk(node)):
            return node
    raise AssertionError(name)


def extract_if_containing(marker):
    parsed = ast.parse(candidate_text())
    for node in ast.walk(parsed):
        if isinstance(node, ast.If):
            segment = ast.get_source_segment(candidate_text(), node)
            if segment and marker in segment:
                return node
    raise AssertionError(marker)


def extract_function(name):
    parsed = ast.parse(candidate_text())
    nodes = [node for node in ast.walk(parsed)
             if isinstance(node, ast.FunctionDef) and node.name == name]
    assert len(nodes) == 1, name
    return nodes[0]


def marked_block(number):
    text = candidate_text()
    begin = '# --- owned-snapshot-wiring begin %d' % number
    end = '# --- owned-snapshot-wiring end %d' % number
    return text[text.index(begin):text.index(end)]


class Seam:
    """Scripted seams for the real extracted v3 closures."""

    def __init__(self, tmp, boots=('boot-1',)):
        self.tmp = Path(tmp)
        self.boots = list(boots)
        self.log = []
        self.capture_calls = []
        self.current_boot = 'boot-1'
        self.result = {
            'owned_scheduling': dict(boot_id=None, before=None, after=None),
            'children': {'arducopter-fc': {'identity': {'pid': 41, 'pgid': 41,
                                                        'start_ticks': 500},
                                           'argv': ['fc'], 'cwd': '/x'},
                         'px4-fc': {'identity': {'pid': 42, 'pgid': 42,
                                                 'start_ticks': 600}}},
            'source_sha256': {'tools/capture_owned_scheduling.py': prep.HELPER_SHA},
        }
        self.namespace = self._namespace()

    def _namespace(self):
        seam = self

        def read_boot_id(root):
            seam.log.append('boot')
            return seam.boots[0] if seam.boots else 'boot-1'

        def json_identity(pid):
            return {'pid': 55, 'pgid': 55, 'start_ticks': 777}

        def digest(path):
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()

        class StubCapture:
            def __init__(self, children, output, phase='unspecified', proc_root='/proc'):
                assert Path(children).is_file()
                self.output = Path(output)
                self.phase = phase

            def capture(self):
                seam.log.append('capture:' + self.phase)
                seam.capture_calls.append(self.phase)
                with self.output.open('xb') as stream:
                    stream.write(json.dumps({'host': {'boot_id': seam.current_boot}}).encode())
                return {'host': {'boot_id': seam.current_boot}}

        return dict(json=json, os=__import__('os'), sys=sys, Path=Path,
                    ValueError=ValueError, FileExistsError=FileExistsError,
                    Exception=Exception, read_boot_id=read_boot_id,
                    json_identity=json_identity, digest=digest,
                    live=self.tmp, result=self.result, REPO=self.tmp,
                    __file__='run_joint_flight.py',
                    OwnedSchedulingCapture=StubCapture)

    def exec_block5(self):
        namespace = dict(self.namespace)
        namespace['owned_snapshot'] = True
        node = extract_if_with_function('owned_snapshot_capture')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
             namespace)
        self.namespace.update({k: namespace[k] for k in
                               ('owned_snapshot_capture', 'owned_snapshot_after_once')})
        return namespace


class ShapeTests(unittest.TestCase):
    def test_strip_restores_baseline(self):
        restored = prep.strip_marked(candidate_text()).encode('utf-8')
        self.assertEqual(hashlib.sha256(restored).hexdigest(), prep.BASELINE_SHA)

    def test_ten_balanced_blocks_and_valid_python(self):
        text = candidate_text()
        self.assertEqual(text.count('# --- owned-snapshot-wiring begin'), 10)
        self.assertEqual(text.count('# --- owned-snapshot-wiring end'), 10)
        ast.parse(text)

    def test_anchors_unique(self):
        text = prep.BASELINE.read_text(encoding='utf-8')
        for index, (anchor, _, _) in enumerate(prep.INSERTIONS, 1):
            self.assertEqual(text.count(anchor), 1, 'anchor %d' % index)

    def test_pin_checked_before_import_in_block2(self):
        block2 = marked_block(2)
        self.assertLess(block2.index('validate_owned_snapshot_helper(digest(helper_path))'),
                        block2.index('import capture_owned_scheduling'))
        self.assertIn('validate_owned_snapshot_helper_origin', block2)


class SuccessPathOrderTests(unittest.TestCase):
    """Point 1: real success-path order and exception-path fallback."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.seam = Seam(self.tmp.name)

    def exec_block6(self, namespace, resources):
        namespace = dict(namespace)
        namespace['resources'] = resources
        node = extract_if_with_function('owned_snapshot_after_once')
        # block6 holds only the registration; the def lives in block5
        node = extract_if_containing('resources.callback(owned_snapshot_after_once)')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
             namespace)

    def exec_block10(self, namespace):
        node = extract_if_containing('Success path: the after capture runs ONCE here')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
             namespace)

    def test_success_path_captures_once_before_unwind(self):
        namespace = self.seam.exec_block5()
        self.assertEqual(self.seam.log, ['boot', 'capture:before'])
        stack = ExitStack()
        stack.callback(lambda: self.seam.log.append('worker-teardown'))
        self.exec_block6(namespace, stack)   # fallback registered (last)
        self.exec_block10(namespace)         # explicit success-path call
        self.assertEqual(self.seam.log,
                         ['boot', 'capture:before', 'boot', 'capture:after'])
        with stack:                          # unwind: fallback must be a no-op
            pass
        self.assertEqual(self.seam.log,
                         ['boot', 'capture:before', 'boot', 'capture:after',
                          'worker-teardown'])
        meta = self.seam.result['owned_scheduling']
        self.assertTrue(meta['after_attempted'])
        self.assertEqual(meta['after'], 'owned-scheduling-after.json')
        self.assertTrue(meta['after_validated'])

    def test_exception_path_fallback_captures_once(self):
        namespace = self.seam.exec_block5()
        stack = ExitStack()
        self.exec_block6(namespace, stack)
        with self.assertRaisesRegex(RuntimeError, 'business'):
            with stack:
                raise RuntimeError('business')  # explicit call never happened
        self.assertEqual(self.seam.capture_calls, ['before', 'after'])
        self.assertTrue(self.seam.result['owned_scheduling']['after_attempted'])

    def test_connect_failure_leaves_after_honestly_absent(self):
        self.seam.exec_block5()  # block6 never runs: physics.connect() raised
        meta = self.seam.result['owned_scheduling']
        self.assertIsNone(meta['after'])
        self.assertNotIn('after_attempted', meta)
        self.assertEqual(self.seam.capture_calls, ['before'])

    def test_once_guard_never_duplicates(self):
        namespace = self.seam.exec_block5()
        self.exec_block10(namespace)
        self.exec_block10(namespace)  # second explicit call is a no-op
        self.assertEqual(self.seam.capture_calls, ['before', 'after'])


class FrozenTargetsTests(unittest.TestCase):
    """Point 2: targets frozen once at before; after reuses and re-verifies."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.seam = Seam(self.tmp.name)

    def test_targets_hold_minimal_identity_only(self):
        namespace = self.seam.exec_block5()
        targets = json.loads(Path(self.tmp.name, 'owned-scheduling-targets.json').read_text())
        for role, entry in targets.items():
            self.assertEqual(sorted(entry), ['identity'])
            self.assertEqual(sorted(entry['identity']),
                             ['pgid', 'pid', 'start_ticks'])
        self.assertEqual(targets['manager']['identity'],
                         {'pid': 55, 'pgid': 55, 'start_ticks': 777})
        # mutate the mutable source: after must not admit new targets
        self.seam.result['children']['late-role'] = {'identity': {'pid': 99,
                                                     'pgid': 99, 'start_ticks': 1}}
        before_bytes = Path(self.tmp.name, 'owned-scheduling-targets.json').read_bytes()
        namespace['owned_snapshot_after_once']()
        self.assertEqual(Path(self.tmp.name, 'owned-scheduling-targets.json').read_bytes(),
                         before_bytes)  # frozen bytes reused unchanged
        self.assertEqual(self.seam.result['owned_scheduling']['after'],
                         'owned-scheduling-after.json')
        self.assertIn('after_validated', self.seam.result['owned_scheduling'])

    def test_frozen_targets_tamper_blocks_after(self):
        namespace = self.seam.exec_block5()
        Path(self.tmp.name, 'owned-scheduling-targets.json').write_text('{"tampered": 1}')
        namespace['owned_snapshot_after_once']()
        meta = self.seam.result['owned_scheduling']
        self.assertIn('frozen targets changed', meta['after_error'])
        self.assertIsNone(meta['after'])
        self.assertNotIn('after_validated', meta)
        self.assertFalse(Path(self.tmp.name, 'owned-scheduling-after.json').exists())


class MetadataHonestyTests(unittest.TestCase):
    """Point 3: only validated captures enter verified metadata."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def exec_block7(self, meta, digest_impl):
        live = Path(self.tmp.name)
        namespace = {'owned_snapshot': True, 'Exception': Exception, 'Path': Path,
                     'result': {'owned_scheduling': meta, 'source_sha256': {},
                                'status': 'failed'},
                     'live': live, 'digest': digest_impl}
        node = extract_if_containing('metadata_error')
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
             namespace)
        return meta

    def test_validated_capture_enters_verified_metadata(self):
        Path(self.tmp.name, 'owned-scheduling-before.json').write_text('{}')
        meta = self.exec_block7(
            dict(before='owned-scheduling-before.json', before_validated=True,
                 after=None),
            lambda path: 'sha:' + Path(path).name)
        self.assertEqual(meta['before']['validated'], True)
        self.assertEqual(meta['before']['sha256'], 'sha:owned-scheduling-before.json')
        self.assertIsNone(meta['after'])
        self.assertNotIn('metadata_error', meta)

    def test_raw_unvalidated_file_retained_but_marked(self):
        Path(self.tmp.name, 'owned-scheduling-after.json').write_text('{"partial": true}')
        meta = self.exec_block7(dict(before=None, after='owned-scheduling-after.json'),
                                lambda path: 'sha:' + Path(path).name)
        self.assertEqual(meta['after']['validated'], False)
        self.assertIn('did not validate', meta['after']['note'])
        self.assertIsNone(meta['before'])

    def test_validated_but_missing_file_is_a_metadata_error(self):
        meta = self.exec_block7(dict(before='owned-scheduling-before.json',
                                     before_validated=True, after=None),
                                lambda path: 'sha:x')
        self.assertIn('missing', meta['metadata_error'])

    def test_hash_failure_fabricates_nothing(self):
        Path(self.tmp.name, 'owned-scheduling-before.json').write_text('{}')
        meta_in = dict(before='owned-scheduling-before.json', before_validated=True,
                       after=None)
        meta = self.exec_block7(meta_in, lambda path: 1 / 0)
        self.assertIn('metadata_error', meta)
        self.assertEqual(meta['before'], 'owned-scheduling-before.json')  # untouched
        self.assertNotIn('targets_sha256', meta)


class HelperPinTests(unittest.TestCase):
    """Point 4: pin before import; origin must equal the pinned path."""

    @classmethod
    def setUpClass(cls):
        cls.ns = {'ValueError': ValueError, 'Path': Path}
        for name in ('validate_owned_snapshot_helper',
                     'validate_owned_snapshot_helper_origin'):
            node = extract_function(name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
                 cls.ns)
        consts = [node for node in ast.parse(candidate_text()).body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id.startswith('OWNED_SNAPSHOT')
                          for t in node.targets)]
        for node in consts:
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<candidate>', 'exec'),
                 cls.ns)

    def test_pin_before_interface(self):
        with self.assertRaisesRegex(ValueError, 'reviewed pin'):
            self.ns['validate_owned_snapshot_helper']('0' * 64)
        sha = self.ns['OWNED_SNAPSHOT_HELPER_SHA256']
        with self.assertRaisesRegex(ValueError, 'interface differs'):
            self.ns['validate_owned_snapshot_helper'](sha, ['self', 'children'])
        self.assertIsNone(self.ns['validate_owned_snapshot_helper'](
            sha, ['self', 'children', 'output', 'phase', 'proc_root']))

    def test_origin_must_equal_pinned_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            expected = Path(tmp) / 'tools' / 'capture_owned_scheduling.py'
            expected.parent.mkdir()
            expected.write_text('# pinned\n')
            self.assertIsNone(self.ns['validate_owned_snapshot_helper_origin'](
                str(expected), str(expected)))
            other = Path(tmp) / 'elsewhere' / 'capture_owned_scheduling.py'
            other.parent.mkdir()
            other.write_text('# other\n')
            with self.assertRaisesRegex(ValueError, 'unexpected origin'):
                self.ns['validate_owned_snapshot_helper_origin'](str(other), str(expected))


if __name__ == '__main__':
    unittest.main(verbosity=2)
