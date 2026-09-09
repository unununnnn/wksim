"""Read-only captured timing attribution; never a live performance acceptance."""
import argparse
from bisect import bisect_left
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from replay_joint_rate_timing import replay


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('cases', nargs='+')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(Path(__file__).resolve().parent):
        raise ValueError('Output must be a new directory inside this evidence package')
    out.mkdir(exist_ok=False)
    hashes = {}
    reports = []
    for name in args.cases:
        case = (ROOT / 'validation' / name).resolve(strict=True)
        if not case.is_relative_to(ROOT / 'validation') or out.is_relative_to(case):
            raise ValueError('Input/output boundary violation')
        epochs = list((case / 'run/epochs').iterdir())
        if len(epochs) != 1:
            raise ValueError('Expected one retained epoch')
        epoch = epochs[0]
        paths = [case / p for p in ('flow.json', 'wrapper.json', 'experiment.json')]
        paths += [epoch / p for p in ('rate.jsonl', 'wire.jsonl', 'result.json', 'preflight.json')]
        hashes.update({str(p.relative_to(ROOT)): digest(p) for p in paths})
        rate = replay(epoch / 'rate.jsonl')
        save(out / (name + '-replay.json'), rate)
        ends = []
        with (epoch / 'rate.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                if row['kind'] == 'rate_group_end' and row['requested_rate'] == 1:
                    ends.append(row)
        if not ends:
            raise ValueError('No measured 1x segment')
        stages = []
        gc_rows = []
        # Preserve exact selected raw lines, with original 1-based line numbers.
        with (epoch / 'wire.jsonl').open(encoding='utf-8') as stream, (out / (name + '-diagnostics.jsonl')).open('x', encoding='utf-8') as raw:
            for line_number, line in enumerate(stream, 1):
                if '"kind":"diagnostic_' not in line:
                    continue
                row = json.loads(line)
                if ends[0]['start_tick'] < row['tick'] <= ends[-1]['end_tick']:
                    raw.write(json.dumps(dict(line_number=line_number, row=row), separators=(',', ':')) + '\n')
                    if row['kind'] == 'diagnostic_step_cpu_timing':
                        stages.append(row)
                    elif row['kind'] == 'diagnostic_gc_timing':
                        gc_rows.append(row)
        ticks = [row['tick'] for row in stages]
        groups = []
        for i, row in enumerate(ends):
            samples = stages[bisect_left(ticks, row['start_tick'] + 1):bisect_left(ticks, row['end_tick'] + 1)]
            duration = row['actual_end_ns'] - row['actual_start_ns']
            measured = {}
            for stage in ('health_and_models', 'encode_send', 'native_inputs'):
                wall = sum(r['stages'][stage]['wall_ns'] for r in samples)
                cpu = sum(r['stages'][stage]['thread_cpu_ns'] for r in samples)
                measured[stage] = dict(wall_ns=wall, thread_cpu_ns=cpu, non_thread_cpu_ns=wall-cpu) if samples else None
            following = ends[i+1] if i+1 < len(ends) and ends[i+1]['segment_id'] == row['segment_id'] else None
            increment = None if following is None else following['actual_start_ns'] - row['actual_start_ns'] - 4_000_000
            excess = max(0, duration - 4_000_000)
            if increment is not None and increment < excess:
                raise ValueError('Captured phase contradicts measured group excess')
            groups.append(dict(start_tick=row['start_tick'], end_tick=row['end_tick'], duration_ns=duration,
                segment_id=row['segment_id'], actual_start_ns=row['actual_start_ns'], actual_end_ns=row['actual_end_ns'],
                start_phase_ns=row['actual_start_ns']-row['ideal_start_ns'], excess_ns=excess,
                next_phase_increment_ns=increment,
                residual_release_ns=None if increment is None else increment-excess,
                diagnostic_ticks=[r['tick'] for r in samples], sampled_stages=measured))
        with (out / (name + '-groups.json.gz')).open('xb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as packed:
                packed.write((json.dumps(groups, separators=(',', ':')) + '\n').encode())
        report = dict(case=name, epoch=epoch.name, replay=rate['replay'], rejection=rate['rejection'],
            segments=[s for s in rate['segments'] if s['rate'] == 1],
            diagnostic_sample_count=len(stages), gc_events=gc_rows,
            top_groups=sorted(groups, key=lambda g:g['excess_ns'], reverse=True)[:10],
            stage_totals={stage: {field:sum(g['sampled_stages'][stage][field] for g in groups if g['sampled_stages'][stage] is not None)
                for field in ('wall_ns', 'thread_cpu_ns', 'non_thread_cpu_ns')}
                for stage in ('health_and_models', 'encode_send', 'native_inputs')} if stages else None,
            limitation='Step diagnostics are sampled (>2ms or tick%250=0), not population medians. Non-thread-CPU includes IPC/socket waits and descheduling; no Windows kernel attribution.')
        reports.append(report)
    benchmark = ROOT / 'validation/rate-release-efficiency-20260909/benchmark.json'
    old_timer = ROOT / 'validation/rate-release-efficiency-20260909/before.py'
    timer = ROOT / 'Simulator/wksim_runtime/joint_rate.py'
    for path in (benchmark, old_timer, timer, ROOT / 'tools/replay_joint_rate_timing.py', Path(__file__).resolve()):
        hashes[str(path.relative_to(ROOT))] = digest(path)
    result = dict(schema_version=1, scope='captured timing diagnosis only', performance_pass=False,
        argv=sys.argv, python=sys.version, head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        timer_restored_byte_identical=digest(timer)==digest(old_timer),
        excluded_timer_experiment=json.loads(benchmark.read_text()), cases=reports)
    save(out / 'profile.json', result)
    # Recheck inputs after streaming, so concurrent source/evidence changes reject this profile.
    for path, expected in hashes.items():
        if digest(ROOT / path) != expected:
            raise ValueError('Input changed during analysis: ' + path)
    save(out / 'input-sha256.json', hashes)
    print(json.dumps(dict(output=str(out), cases=[dict(case=r['case'], rejection=r['rejection'], samples=r['diagnostic_sample_count']) for r in reports], performance_pass=False)))


if __name__ == '__main__':
    main()
