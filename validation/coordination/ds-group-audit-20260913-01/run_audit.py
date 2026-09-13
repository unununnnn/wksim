"""Reproduce the archived audit artifact for one diagnostic flight.

Runs the independent audit CLI against a read-only WSL archive and stores the
result under ``evidence/``.  Nothing is written into the archive; the archive is
addressed through WSL because it lives on the Ubuntu-22.04 filesystem.

    python run_audit.py
    python run_audit.py --distro Ubuntu-22.04 \
        --archive /root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb \
        --label joint-public-flight-rfw9nmbb
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, 'ds_group_audit.py')
GAP_MAP = os.path.join(HERE, 'gap_map.py')
DEFAULT_ARCHIVE = ('/root/wksim-release-acceptance-fe3/validation/'
                   'joint-public-flight-rfw9nmbb')
STAGING = '/tmp/ds-group-audit-run'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def wsl(distro, command, env=None):
    environment = dict(os.environ)
    if env:
        environment.update(env)
        # WSL only forwards Windows variables listed in WSLENV.
        names = [name for name in env]
        existing = environment.get('WSLENV', '')
        environment['WSLENV'] = '/'.join(part for part in [existing] + names if part)
    return subprocess.run(['wsl', '-d', distro, '-e', 'bash', '-lc', command],
                          capture_output=True, text=True, check=False, env=environment)


def to_wsl_path(path):
    """Map a Windows drive path to its /mnt/<drive> WSL form (WSLPATH is not set here)."""
    drive, rest = os.path.splitdrive(os.path.abspath(path))
    if not drive:
        return None
    return '/mnt/%s%s' % (drive.rstrip(':').lower(), rest.replace('\\', '/'))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--distro', default='Ubuntu-22.04')
    parser.add_argument('--archive', default=DEFAULT_ARCHIVE)
    parser.add_argument('--label', default=None)
    parser.add_argument('--evidence-dir', default=os.path.join(HERE, 'evidence'))
    parser.add_argument('--version', default='v2',
                        help='artifact version suffix; the previous version is never '
                             'overwritten (default: v2)')
    args = parser.parse_args(argv)
    label = args.label or os.path.basename(args.archive.rstrip('/'))
    os.makedirs(args.evidence_dir, exist_ok=True)
    suffix = '' if not args.version else '-%s' % args.version

    # The tool is staged into WSL by its /mnt/<drive> path; nothing is written
    # into the archive and the archive itself stays read-only.
    tool_in_wsl = to_wsl_path(AUDIT)
    gap_in_wsl = to_wsl_path(GAP_MAP)
    if tool_in_wsl is None or gap_in_wsl is None:
        print('could not map the tools into the WSL filesystem')
        return 2
    out_in_wsl = '%s/%s-audit%s.json' % (STAGING, label, suffix)
    gap_out_in_wsl = '%s/%s-gap-map%s.json' % (STAGING, label, suffix)
    staged_tool = '%s/ds_group_audit.py' % STAGING
    staged_gap = '%s/gap_map.py' % STAGING
    script = ('rm -rf {staging} && mkdir -p {staging} && cp {tool} {staged} && '
              'cp {gap} {staged_gap} && '
              'python3 {staged} --archive {archive} --label {label} --out {out} && '
              'python3 {staged_gap} --archive {archive} --audit {out} --out {gap_out}'
              .format(staging=STAGING, tool="'%s'" % tool_in_wsl, staged=staged_tool,
                      gap="'%s'" % gap_in_wsl, staged_gap=staged_gap,
                      archive=args.archive, label=label, out=out_in_wsl,
                      gap_out=gap_out_in_wsl))
    result = wsl(args.distro, script)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode not in (0, 1):
        print('audit run failed with exit %d' % result.returncode)
        return result.returncode

    local_out = os.path.join(args.evidence_dir, '%s-audit%s.json' % (label, suffix))
    copy = wsl(args.distro, 'cat %s' % out_in_wsl)
    if copy.returncode != 0:
        print('could not read the artifact back: %s' % copy.stderr)
        return 2
    with open(local_out, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(copy.stdout)

    local_gap = os.path.join(args.evidence_dir, '%s-gap-map%s.json' % (label, suffix))
    copy_gap = wsl(args.distro, 'cat %s' % gap_out_in_wsl)
    if copy_gap.returncode != 0:
        print('could not read the gap-map artifact back: %s' % copy_gap.stderr)
        return 2
    with open(local_gap, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(copy_gap.stdout)

    with open(local_out, 'r', encoding='utf-8') as handle:
        report = json.load(handle)
    with open(local_gap, 'r', encoding='utf-8') as handle:
        gap_report = json.load(handle)
    manifest = {
        'archive': args.archive,
        'label': label,
        'audit_distro': args.distro,
        'audit_exit_code': result.returncode,
        'verdict': report.get('verdict'),
        'over_budget_groups': report.get('rate', {}).get('over_budget_groups'),
        'reports_emitted': len(report.get('reports', [])),
        'gap_map_verdict': gap_report.get('verdict'),
        'gap_map_finding_counts': gap_report.get('finding_counts'),
        'gap_max_ns': gap_report.get('gap_summary', {}).get('gap_max_ns'),
        'clock_offset_width_ns': gap_report.get('clock_alignment', {}).get('width_ns'),
        'version': args.version,
        'supersedes': ('%s-audit.json / %s-gap-map.json (pre-repair snapshot, preserved)'
                       % (label, label)) if args.version else None,
        'artifact': os.path.relpath(local_out, HERE).replace(os.sep, '/'),
        'artifact_sha256': sha256_file(local_out),
        'gap_map_artifact': os.path.relpath(local_gap, HERE).replace(os.sep, '/'),
        'gap_map_artifact_sha256': sha256_file(local_gap),
        'tool': os.path.basename(AUDIT),
        'tool_sha256': sha256_file(AUDIT),
        'gap_map_tool': os.path.basename(GAP_MAP),
        'gap_map_tool_sha256': sha256_file(GAP_MAP),
    }
    manifest_path = os.path.join(args.evidence_dir,
                                 '%s-audit%s.manifest.json' % (label, suffix))
    with open(manifest_path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
