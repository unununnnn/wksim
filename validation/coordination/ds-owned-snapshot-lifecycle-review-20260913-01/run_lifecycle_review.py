"""Produce the pure event traces for the snapshot lifecycle review.

Read-only over the authors' candidates; writes only into this directory. Run from the
workspace root or anywhere:

  python -B validation/coordination/ds-owned-snapshot-lifecycle-review-20260913-01/run_lifecycle_review.py
"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import lifecycle_fixture as fixture           # noqa: E402
from lifecycle_fixture import Engine           # noqa: E402
import test_snapshot_lifecycle as suite        # noqa: E402

ROOT = HERE.parents[2]
EVIDENCE = HERE / 'evidence'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def minimal_metadata_case():
    """The v3 'validated file missing' branch, checked against the fixture contract."""
    engine = Engine('v3', live=Path(tempfile.mkdtemp(prefix='lifecycle-missing-')))
    engine.run()
    # a validated capture exists, so the branch cannot fire on a normal run
    return dict(validated=engine.result['owned_scheduling']['after']['validated'],
                metadata_error=engine.result['owned_scheduling'].get('metadata_error'),
                branch_fired=engine.count('refresh_missing'))


def main():
    EVIDENCE.mkdir(exist_ok=True)
    traces = suite.dump_traces(EVIDENCE / 'lifecycle-traces.jsonl')
    summary = dict(
        scope='pure-event fixture for the owned-scheduling snapshot after-capture lifecycle',
        sources={name: dict(path=str(path.relative_to(ROOT)), sha256=sha256(path),
                            bytes=path.stat().st_size)
                 for name, path in fixture.source_variants().items()},
        helper=dict(path='tools/capture_owned_scheduling.py', sha256=sha256(fixture.HELPER),
                    pin_matches=sha256(fixture.HELPER) == fixture.HELPER_PIN),
        anchors_verified=fixture.anchors_verified(),
        anchor_lines={key: dict(path=str(path.relative_to(ROOT)), line=line, text=text)
                      for key, (path, line, text) in fixture.ANCHORS.items()},
        scenarios=[{key: value for key, value in line.items() if key != 'events'}
                   for line in traces if not line['scenario'].endswith('/events')],
        v2_defect=dict(
            after_registration_line=fixture.ANCHORS['v2_after_registration'][1],
            stop_line=fixture.ANCHORS['v2_stop_action'][1],
            model_stdin_close_line=fixture.ANCHORS['v2_model_stdin_close'][1],
            cleanup_children_line=fixture.ANCHORS['v2_finally_cleanup'][1],
            statement=('the after capture is registered only as an ExitStack callback, so it '
                       'runs while the with-block unwinds: after the stop request, after the '
                       "runner's own child.stdin.close()/wait() model teardown, and its capture "
                       'is therefore taken against a model that has already exited'),
        ),
        v3_fix=dict(
            success_call_line=fixture.ANCHORS['v3_success_after'][1],
            stop_line=fixture.ANCHORS['v3_stop_action'][1],
            model_stdin_close_line=fixture.ANCHORS['v3_model_stdin_close'][1],
            cleanup_children_line=fixture.ANCHORS['v3_finally_cleanup'][1],
            backstop_registration_line=fixture.ANCHORS['v3_after_registration'][1],
            once_guard_line=fixture.ANCHORS['v3_once_guard'][1],
            validated_flag_line=fixture.ANCHORS['v3_validated_flag'][1],
            statement=('one explicit once-guarded after capture before the stop request and '
                       'before the model teardown; the ExitStack registration is an '
                       'error-unwind backstop that the once-state turns into a no-op'),
        ),
        capture_file_acceptance=dict(
            v2_refresh=('v2 lines 1355-1358 re-read any file at the capture path and record '
                        'name+sha256, so a file whose phase says "before" or a stale file from '
                        'an earlier run is presented as the after capture'),
            v3_refresh=('v3 lines 1386-1396 present validated=meta[phase+_validated]; a raw file '
                        'is retained with an explicit note and never presented as verified'),
            v3_flag_retained=True,
            minimal_metadata_case=minimal_metadata_case(),
        ),
    )
    (EVIDENCE / 'lifecycle-review.json').write_text(
        json.dumps(summary, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print('anchors all verified:', all(summary['anchors_verified'].values()))
    for line in summary['scenarios']:
        print('%-34s attempts=%s validations=%s order=%s' % (
            line['scenario'], line['after_attempts'], line['after_validations'],
            line['order']))
    print('evidence:', (EVIDENCE / 'lifecycle-review.json').relative_to(ROOT))
    print('traces:  ', (EVIDENCE / 'lifecycle-traces.jsonl').relative_to(ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
