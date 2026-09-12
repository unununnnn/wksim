"""CLI output-overwrite protection for the independent planner-release auditor.

These tests use real temporary files and a mocked ``audit`` so no flight,
native runner, simulator, or ROS import is required. They pin the contract
that a retained report (including a symlink) is never overwritten and that the
final write is an exclusive create so a check/write race cannot clobber
evidence. Unlike the PV auditor, this CLI has no raw-root containment rule, so
none is added here; only the overwrite protection is introduced.

Exit-code contract under test:
    0 = audit ran and the verdict is pass
    1 = audit ran and the verdict is failed
    2 = refused before/around the write (unsafe output target) or argparse
        rejected the invocation; no evidence was overwritten and, when the
        audit already ran, the report still reached stdout.
"""
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from tools import audit_planner_release as auditor

REFUSAL_EXIT = 2

PASS_REPORT = dict(status='pass',
                   scope='moving P+V handoff, public BRAKE and two-vehicle LAND only',
                   full_acceptance=False, nominal_pv_acceptance=False,
                   run_id='run-1', epoch='epoch-1', request_id=7)


def expected_render(report):
    """The exact bytes main() writes to the file and prints to stdout."""
    full = dict(report)
    full['auditor_sha256'] = auditor.sha(auditor.__file__)
    return json.dumps(full, indent=2) + '\n'


class CliOutputTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.evidence_root = self.root / 'evidence'
        self.evidence_root.mkdir()

    def invoke(self, output=None, report=PASS_REPORT, side_effect=None, include_output=True):
        """Run main() with a mocked audit and captured argv/stdout/stderr.

        Returns (exit_code, stdout, stderr, audit_mock); a SystemExit raised by
        argparse is surfaced as its integer code.
        """
        argv = ['audit_planner_release.py', str(self.evidence_root)]
        if include_output:
            argv += ['--output', str(output)]
        if side_effect is None:
            side_effect = lambda root: dict(report)
        fake_audit = Mock(side_effect=side_effect)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', argv), \
                patch.object(auditor, 'audit', fake_audit), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                code = auditor.main()
            except SystemExit as error:
                code = error.code
        return code, out.getvalue(), err.getvalue(), fake_audit

    # --- Preserved existing contract ----------------------------------------

    def test_fresh_output_written_verbatim_and_exit_zero(self):
        output = self.root / 'report.json'
        code, out, err, fake_audit = self.invoke(output=output)
        self.assertEqual(code, 0)
        self.assertEqual(output.read_text(), expected_render(PASS_REPORT))
        self.assertEqual(out, expected_render(PASS_REPORT))
        self.assertEqual(err, '')
        fake_audit.assert_called_once()

    def test_failed_audit_exit_one_and_writes_fresh_report(self):
        output = self.root / 'report.json'
        code, out, err, fake_audit = self.invoke(output=output, side_effect=ValueError('boom'))
        self.assertEqual(code, 1)
        fake_audit.assert_called_once()
        data = json.loads(output.read_text())
        self.assertEqual(data['status'], 'failed')
        self.assertIn('boom', data['error'])
        self.assertEqual(data['full_acceptance'], False)
        self.assertIn('auditor_sha256', data)
        self.assertEqual(out, output.read_text())

    def test_missing_output_argument_is_rejected_by_argparse(self):
        """--output is required: omitting it is an argparse error, unchanged."""
        code, out, err, fake_audit = self.invoke(include_output=False)
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertIn('usage', err.lower())
        fake_audit.assert_not_called()

    # --- New protection: never overwrite retained evidence ------------------

    def test_existing_output_preserved_verbatim_and_audit_not_run(self):
        output = self.root / 'report.json'
        sentinel = b'PREVIOUS FAILED REPORT\x00verbatim-bytes\n'
        output.write_bytes(sentinel)
        code, out, err, fake_audit = self.invoke(output=output)
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertEqual(output.read_bytes(), sentinel)
        fake_audit.assert_not_called()
        self.assertIn('refusing to overwrite', err)

    def test_existing_directory_output_is_refused(self):
        output = self.root / 'occupied'
        output.mkdir()
        code, out, err, fake_audit = self.invoke(output=output)
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertTrue(output.is_dir())
        fake_audit.assert_not_called()

    def test_symlink_output_is_refused(self):
        target = self.root / 'retained.json'
        target.write_bytes(b'ORIGINAL BYTES\n')
        link = self.root / 'link.json'
        try:
            os.symlink(str(target), str(link))
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        code, out, err, fake_audit = self.invoke(output=link)
        self.assertEqual(code, REFUSAL_EXIT)
        fake_audit.assert_not_called()
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_bytes(), b'ORIGINAL BYTES\n')

    def test_dangling_symlink_output_is_refused(self):
        missing = self.root / 'missing-target.json'
        link = self.root / 'dangling.json'
        try:
            os.symlink(str(missing), str(link))
        except OSError as error:
            self.skipTest(f'symlink unavailable: {error}')
        self.assertTrue(link.is_symlink())
        self.assertFalse(link.exists())
        code, out, err, fake_audit = self.invoke(output=link)
        self.assertEqual(code, REFUSAL_EXIT)
        fake_audit.assert_not_called()
        self.assertTrue(link.is_symlink())
        self.assertFalse(missing.exists())

    def test_dangling_symlink_probe_is_used_portable(self):
        """A dangling symlink is invisible to exists() but not to lexists().

        Hosts without symlink privilege cannot build a real dangling link, so
        emulate one: the dangling-aware probe reports the name exists while the
        target-following probe reports nothing. main() must refuse before the
        audit and create nothing, proving it does not rely on exists() alone.
        """
        output = self.root / 'report.json'
        real_lexists = os.path.lexists

        def fake_lexists(path):
            return True if Path(path) == output else real_lexists(path)

        with patch.object(os.path, 'lexists', fake_lexists):
            code, out, err, fake_audit = self.invoke(output=output)
        self.assertEqual(code, REFUSAL_EXIT)
        fake_audit.assert_not_called()
        self.assertFalse(output.exists())
        self.assertIn('refusing to overwrite', err)

    def test_check_write_race_does_not_overwrite(self):
        """If the target appears after the pre-audit check, the exclusive
        create must fail rather than clobber the racing writer's content."""
        output = self.root / 'report.json'
        sentinel = b'RACE WINNER - DO NOT CLOBBER\n'

        def create_then_report(root):
            output.write_bytes(sentinel)
            return dict(PASS_REPORT)

        code, out, err, fake_audit = self.invoke(output=output, side_effect=create_then_report)
        self.assertEqual(code, REFUSAL_EXIT)
        self.assertEqual(output.read_bytes(), sentinel)
        fake_audit.assert_called_once()
        self.assertEqual(out, expected_render(PASS_REPORT))
        self.assertIn('refusing to overwrite', err)


if __name__ == '__main__':
    unittest.main()
