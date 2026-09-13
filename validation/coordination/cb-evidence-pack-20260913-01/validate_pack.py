"""Validate a pinned, selected diagnostic pack; never grants flight acceptance."""
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def validate(root, manifest):
    root = Path(root).resolve()
    errors = []
    if manifest.get('classification') != 'diagnostic_only':
        errors.append('manifest classification')
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            errors.append('missing or escaping file: ' + name)
        elif digest(path) != expected:
            errors.append('hash mismatch: ' + name)
    for required in ('result.json', 'group-work-timing.jsonl', 'rate.jsonl.gz'):
        if required not in manifest['files']:
            errors.append('unbound required file: ' + required)
    if errors:
        return {'valid': False, 'full_acceptance': False, 'errors': errors}
    try:
        result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
        summary = result['group_work_timing']
        if result['status'] not in ('failed', 'observed'):
            errors.append('unrecognized diagnostic status')
        if result['flight_completed'] is not False:
            errors.append('diagnostic cannot complete formal flight')
        if summary['classification'] != 'diagnostic_only' or summary['full_acceptance'] is not False:
            errors.append('invalid diagnostic marker')
        reports = [json.loads(line) for line in (root / 'group-work-timing.jsonl').read_text(encoding='utf-8').splitlines()]
        keys = [(r['epoch'], r['segment_id'], r['start_tick']) for r in reports]
        if len(keys) != len(set(keys)):
            errors.append('duplicate report identity')
        if any(r['epoch'] != result['scene_epoch'] or r['classification'] != 'diagnostic_only' or r['full_acceptance'] is not False for r in reports):
            errors.append('report identity or marker mismatch')
        counts = summary['counts']
        if len(reports) != counts['reports_emitted'] or not 0 <= len(reports) <= summary['report_limit'] <= 16:
            errors.append('report cap or count mismatch')
        if counts['reports_emitted'] + counts['reports_dropped'] != counts['over_budget_groups']:
            errors.append('overrun accounting mismatch')
    except (KeyError, TypeError, ValueError, OSError) as exc:
        errors.append('malformed pack: ' + str(exc))
    return {'valid': not errors, 'classification': 'diagnostic_only', 'full_acceptance': False,
            'errors': errors, 'limits': 'Checks selected pack integrity and labels only; no physical, timing, or formal acceptance.'}


if __name__ == '__main__':
    import sys
    root = Path(sys.argv[1])
    result = validate(root, json.loads((root / 'manifest.json').read_text(encoding='utf-8')))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['valid'] else 1)
