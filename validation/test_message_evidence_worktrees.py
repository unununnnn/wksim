"""Actual Git metadata checks for sealed evidence shared by one repository's worktrees."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import joint_message_candidate as candidate


class WorktreeEvidenceTests(unittest.TestCase):
    def test_same_repository_worktree_allowed_foreign_and_nested_roots_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            repo, worktree, other = (base / name for name in ('repo', 'worktree', 'other'))
            def git(*args):
                subprocess.run(['git', *map(str, args)], check=True, capture_output=True)
            git('init', repo)
            git('-C', repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '--allow-empty', '-m', 'fixture')
            git('-C', repo, 'worktree', 'add', '--detach', worktree)
            git('init', other)
            evidence = repo / 'validation' / 'prometheus-ros2-fixture'
            foreign = other / 'validation' / 'prometheus-ros2-fixture'
            nested = repo / 'arbitrary' / 'validation' / 'prometheus-ros2-fixture'
            for path in (evidence, foreign, nested): path.mkdir(parents=True)
            with patch.object(candidate, 'REPO', worktree):
                self.assertEqual(candidate.evidence_path(evidence), evidence)
                for invalid in (foreign, nested):
                    with self.subTest(path=invalid), self.assertRaises(ValueError):
                        candidate.evidence_path(invalid)
            # The original local-evidence behavior remains unchanged.
            with patch.object(candidate, 'REPO', repo):
                self.assertEqual(candidate.evidence_path(evidence), evidence)


if __name__ == '__main__':
    unittest.main()
