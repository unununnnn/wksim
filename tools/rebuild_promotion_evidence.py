"""Create review-only evidence catalogs from audited flights; never update admission pins."""
import argparse
import copy
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from Simulator.wksim_runtime import preflight, independent_profile
from tools.audit_independent_profile import audit, read, require, sha


def relative(path):
    return Path(path).resolve().relative_to(REPO).as_posix()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def pin(path):
    return dict(path=relative(path), sha256=sha(path))


def independent(directories, output):
    archive = output / 'flown-source'
    archive.mkdir()
    manifest = dict(mode='retained-source-audit', runs={})
    catalog = dict(schema_version=1, profile=independent_profile.PROFILE_ID, sources={}, runs={})
    for directory in directories:
        directory = Path(directory).resolve()
        relative(directory)
        run, wrapper = read(directory / 'run/result.json'), read(directory / 'report.json')
        stack = run['stack']
        require(stack in ('px4', 'arducopter') and stack not in catalog['runs'], 'One independent run per stack required')
        require(run['run_id'] not in manifest['runs'], 'Distinct independent run IDs required')
        selected, _ = independent_profile.select_config(run['config'])
        require(selected['stack'] == stack, 'Independent configuration stack differs')
        # Verify actual requests/truth/process images before copying current source.
        audit(directory)
        sources = dict(run['runtime_sha256'], **{'tools/validate_independent_profile.py': wrapper['driver_sha256']})
        entry = dict(report_sha256=sha(directory / 'report.json'),
                     formal_result_sha256=sha(directory / 'run/result.json'), sources={})
        for name, expected in sources.items():
            source = (REPO / name).resolve()
            require(source.is_relative_to(REPO) and sha(source) == expected, 'Executed source differs: ' + name)
            destination = archive / 'source' / source.relative_to(REPO)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                require(sha(destination) == expected, 'Flights used different source: ' + name)
            else:
                with destination.open('xb') as stream:
                    stream.write(source.read_bytes())
            entry['sources'][name] = dict(sha256=expected, archive_path=destination.relative_to(archive).as_posix())
            catalog['sources'][relative(destination)] = expected
        manifest['runs'][run['run_id']] = entry
        catalog['runs'][stack] = dict(result=pin(directory / 'run/result.json'), files={
            relative(path): sha(path) for path in sorted(directory.rglob('*')) if path.is_file()})
    require(set(catalog['runs']) == {'px4', 'arducopter'}, 'Both independent stacks required')
    write(archive / 'manifest.json', manifest)
    auditor = REPO / 'tools/audit_independent_profile.py'
    report = dict(status='pass', audit_sha256=sha(auditor),
                  runs=[audit(directory, archive) for directory in directories])
    write(output / 'flight-audit.json', report)
    catalog.update(audit=pin(output / 'flight-audit.json'), audit_source=pin(auditor),
                   archive_manifest=pin(archive / 'manifest.json'))
    write(output / 'independent-profile-evidence.candidate.json', catalog)


def session(results, output):
    index = copy.deepcopy(read(preflight.INDEX))
    evidence = {}
    for path in results:
        path = Path(path).resolve()
        run = read(path)
        stack = run['stack']
        require(stack in ('px4', 'arducopter') and stack not in evidence, 'One session result per stack required')
        expected = preflight.control_sources(dict(promotion_flight=True,
            prometheus_workspace=run['prometheus_workspace']), index, run)
        require(run['prometheus']['implementation_sha256'] == expected, 'Session did not fly the current pinned control build')
        evidence[stack] = dict(result=relative(path), result_sha256=sha(path))
    require(set(evidence) == {'px4', 'arducopter'}, 'Both session stacks required')
    index['control_profiles']['session_v1']['evidence'] = evidence
    # Existing validator enforces six request envelopes, both stacks, fixed firmware,
    # agent/model, protocol, workspace and identical installed control source hashes.
    for stack in evidence:
        preflight.control_profile(index, 'session_v1', stack, lambda *args: None)
    write(output / 'capability-index.candidate.json', index)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--independent', nargs=2, type=Path, metavar=('PX4_DIRECTORY', 'AP_DIRECTORY'))
    parser.add_argument('--session', nargs=2, type=Path, metavar=('PX4_RESULT', 'AP_RESULT'))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    require(args.independent or args.session, 'Supply independent and/or session evidence')
    output = args.output.resolve()
    require(output.is_relative_to(REPO / 'validation'), 'Candidate output must be inside repository validation/')
    inputs = list(args.independent or []) + [p.parent for p in args.session or []]
    require(all(not output.is_relative_to(p.resolve()) for p in inputs), 'Output must be outside input evidence')
    output.mkdir(parents=True, exist_ok=False)
    if args.independent:
        independent(args.independent, output)
    if args.session:
        session(args.session, output)
    print(json.dumps(dict(status='candidate_only', output=str(output), admission_updated=False)))


if __name__ == '__main__':
    main()
