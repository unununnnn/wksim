#!/usr/bin/env python3
"""Pure-Python synthetic tests for perf_stream_consumer.py.

No native code, no compilation, no perf event, no model/ROS. Every fixture is a
synthetic byte string built here; nothing is labeled as flight evidence.

Run:  python -B test_perf_stream_consumer.py
Exit: 0 when every case matches its expectation.
"""
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))

REC_SWITCH = 14
MISC_OUT = 1 << 13
MISC_OUT_PREEMPT = 1 << 14
OWNER_PID = 4242
OWNER_TID = 4243
BOOT = '2e7caa0c-f041-426f-a550-50acd12125c5'
ENABLE_BEFORE = 1_000_000
ENABLE_AFTER = 1_000_100
DISABLE_BEFORE = 9_000_000
DISABLE_AFTER = 9_000_100


def load_consumer():
    spec = importlib.util.spec_from_file_location(
        'perf_stream_consumer', os.path.join(HERE, 'perf_stream_consumer.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def switch_record(misc, time_ns, cpu, pid=OWNER_PID, tid=OWNER_TID, size=32, record_type=REC_SWITCH):
    chunk = bytearray(size)
    chunk[0:4] = record_type.to_bytes(4, 'little')
    chunk[4:6] = misc.to_bytes(2, 'little')
    chunk[6:8] = size.to_bytes(2, 'little')
    chunk[8:12] = (pid & 0xFFFFFFFF).to_bytes(4, 'little')
    chunk[12:16] = (tid & 0xFFFFFFFF).to_bytes(4, 'little')
    chunk[16:24] = time_ns.to_bytes(8, 'little')
    chunk[24:28] = cpu.to_bytes(4, 'little')
    return bytes(chunk)


def raw_stream():
    """Two complete pairs on two CPUs, inside the capture bounds."""
    return b''.join([
        switch_record(MISC_OUT, 2_000_000, 3),
        switch_record(0, 2_500_000, 3),
        switch_record(MISC_OUT | MISC_OUT_PREEMPT, 4_000_000, 7),
        switch_record(0, 4_400_000, 5),
    ])


def framed_record(record_type, size, time_ns=None, cpu=0):
    """A non-switch record with its REAL declared size (may be any multiple of 4)."""
    chunk = bytearray(size)
    chunk[0:4] = record_type.to_bytes(4, 'little')
    chunk[6:8] = size.to_bytes(2, 'little')
    if size >= 16 and time_ns is not None:
        chunk[8:16] = time_ns.to_bytes(8, 'little')
    if cpu:
        chunk[size - 8:size - 4] = cpu.to_bytes(4, 'little')
    return bytes(chunk)


def raw_with_outer_record():
    """A legitimate pair whose first timestamp sits in the enable ioctl window:
    after enable_before_ns but before enable_after_ns. The outer span must accept
    it; the inner span must not."""
    return b''.join([
        switch_record(MISC_OUT, ENABLE_BEFORE + 50, 3),
        switch_record(0, ENABLE_AFTER + 1_000, 3),
    ])


def windows_doc(entries, boot=BOOT, pid=OWNER_PID, tid=OWNER_TID,
                schema='wksim.perf_windows.v1', clock='CLOCK_MONOTONIC'):
    return dict(schema=schema, boot_id=boot, owner_pid=pid, owner_tid=tid, clock_id=clock,
                windows=entries)


def base_metadata(raw_len):
    return dict(
        schema='wksim.perf_switch_stream.v1',
        classification='diagnostic_only',
        full_acceptance=False,
        owner_pid=OWNER_PID,
        owner_tid=OWNER_TID,
        boot_id=BOOT,
        clock_id='CLOCK_MONOTONIC',
        enable_before_ns=ENABLE_BEFORE,
        enable_after_ns=ENABLE_AFTER,
        disable_before_ns=DISABLE_BEFORE,
        disable_after_ns=DISABLE_AFTER,
        ring_bytes=131072,
        storage_capacity_bytes=134217728,
        captured_bytes=raw_len,
        reader_policy=0,
        config=dict(pid_argument=0, cpu_argument=-1, inherit=0, exclude_kernel=1,
                    context_switch=1, sample_id_all=1, sample_type=['TID', 'TIME', 'CPU']),
        collector_complete=True,
        collector_errors=[],
        lifecycle=dict(disable_ok=True, reader_joined=True, munmap_ok=True, close_ok=True),
    )


class Fixture:
    """One throwaway directory holding raw/metadata/windows/output paths."""

    def __init__(self, raw=None, meta=None, windows=None, raw_length_override=None):
        self.dir = tempfile.mkdtemp(prefix='ds-perf-consumer-')
        self.raw_path = os.path.join(self.dir, 'raw.bin')
        self.meta_path = os.path.join(self.dir, 'meta.json')
        self.win_path = os.path.join(self.dir, 'windows.json')
        self.out_path = os.path.join(self.dir, 'out.json')
        blob = raw_stream() if raw is None else raw
        with open(self.raw_path, 'wb') as handle:
            handle.write(blob)
        length = len(blob) if raw_length_override is None else raw_length_override
        document = base_metadata(length) if meta is None else meta
        with open(self.meta_path, 'w', encoding='utf-8') as handle:
            json.dump(document, handle)
        self.has_windows = windows is not None
        if self.has_windows:
            with open(self.win_path, 'w', encoding='utf-8') as handle:
                json.dump(windows, handle)

    def argv(self, with_windows=False):
        args = ['--raw', self.raw_path, '--metadata', self.meta_path, '--output', self.out_path]
        if with_windows:
            args += ['--windows', self.win_path]
        return args

    def write_metadata_text(self, text):
        with open(self.meta_path, 'w', encoding='utf-8') as handle:
            handle.write(text)

    def write_windows_text(self, text):
        with open(self.win_path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        self.has_windows = True

    def output(self):
        with open(self.out_path, encoding='utf-8') as handle:
            return json.load(handle)

    def cleanup(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def mutate_meta(fixture, **changes):
    with open(fixture.meta_path, encoding='utf-8') as handle:
        document = json.load(handle)
    document.update(changes)
    with open(fixture.meta_path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)


def run(module, fixture, with_windows=False):
    stderr = io.StringIO()
    stdout = io.StringIO()
    with redirect_stderr(stderr), redirect_stdout(stdout):
        code = module.main(fixture.argv(with_windows=with_windows))
    payload = None
    text = stderr.getvalue().strip() or stdout.getvalue().strip()
    if text:
        try:
            payload = json.loads(text.splitlines()[-1])
        except ValueError:
            payload = None
    return code, payload, stderr.getvalue(), stdout.getvalue()


CASES = []


def check(name, condition, detail=''):
    CASES.append(dict(name=name, ok=bool(condition), detail=str(detail)))
    print('%-46s %s%s' % (name, 'PASS' if condition else 'FAIL',
                          ('  ' + str(detail)) if (detail and not condition) else ''))


def expect_reject(module, name, fixture, reason, with_windows=False):
    code, payload, _, _ = run(module, fixture, with_windows=with_windows)
    ok = code == 3 and payload is not None and payload.get('reason') == reason
    check(name, ok, 'code=%r payload=%r' % (code, payload))
    fixture.cleanup()


def main():
    module = load_consumer()

    # 1. Success without windows.
    fixture = Fixture()
    code, payload, _, _ = run(module, fixture)
    report = fixture.output()
    check('success_exit_zero', code == 0, 'code=%r' % code)
    check('success_pairs_decoded', report['decoded']['pairs'] == 2, report['decoded'])
    check('success_records_split', report['decoded']['switch_out'] == 2
          and report['decoded']['switch_in'] == 2)
    check('success_pair_durations', [pair['duration_ns'] for pair in report['pairs']]
          == [500000, 400000], report['pairs'])
    check('success_cpu_preserved', [(pair['out_cpu'], pair['in_cpu']) for pair in report['pairs']]
          == [(3, 3), (7, 5)], report['pairs'])
    check('success_preempt_flag_preserved', [pair['out_preempt'] for pair in report['pairs']]
          == [False, True])
    check('success_windows_absent', report['windows'] is None)
    check('raw_sha_matches_file',
          report['inputs']['raw_sha256'] == hashlib.sha256(raw_stream()).hexdigest())
    check('no_flight_conclusion', report['flight_conclusion'] is None
          and report['full_acceptance'] is False)
    check('stream_completeness_not_proven', report['stream_completeness_proven'] is False
          and 'pending LOST' in report['stream_completeness_reason'])
    fixture.cleanup()

    # 2. Success with windows: intersections are integer-nanosecond spans.
    fixture = Fixture(windows=windows_doc([
        dict(id='w1', start_ns=2_200_000, end_ns=2_600_000),
        dict(id='w2', start_ns=4_300_000, end_ns=4_500_000),
        dict(id='w3', start_ns=5_000_000, end_ns=5_100_000),
    ]))
    code, payload, _, _ = run(module, fixture, with_windows=True)
    report = fixture.output()
    check('windows_exit_zero', code == 0, 'code=%r payload=%r' % (code, payload))
    windows = report['windows']
    check('windows_count', len(windows) == 3, windows)
    check('windows_intersection_spans',
          [entry['intersecting_pairs'] for entry in windows] == [1, 1, 0],
          [entry['intersecting_pairs'] for entry in windows])
    check('windows_intersection_durations',
          [entry['intersection_total_ns'] for entry in windows] == [300000, 100000, 0],
          [entry['intersection_total_ns'] for entry in windows])
    check('windows_bind_sha',
          report['inputs']['windows_sha256']
          == hashlib.sha256(open(fixture.win_path, 'rb').read()).hexdigest())

    # 3. Refuse to overwrite an existing output.
    code, payload, _, _ = run(module, fixture, with_windows=True)
    check('refuse_overwrite', code == 3
          and payload.get('reason') == 'output_exists_refusing_overwrite', payload)
    fixture.cleanup()

    # 4. Metadata contract rejections.
    for name, reason, changes in (
        ('reject_schema', 'metadata_schema_mismatch', dict(schema='wksim.other.v1')),
        ('reject_classification', 'metadata_classification_mismatch',
         dict(classification='production')),
        ('reject_full_acceptance', 'metadata_full_acceptance_not_false',
         dict(full_acceptance=True)),
        ('reject_owner_pid', 'metadata_owner_pid_invalid', dict(owner_pid=0)),
        ('reject_owner_tid_type', 'metadata_owner_tid_invalid', dict(owner_tid=True)),
        ('reject_clock_id', 'metadata_clock_id_mismatch', dict(clock_id='CLOCK_REALTIME')),
        ('reject_boot_id', 'metadata_boot_id_invalid', dict(boot_id='')),
        ('reject_bound_order', 'metadata_clock_bounds_out_of_order',
         dict(enable_after_ns=ENABLE_BEFORE - 1)),
        ('reject_ring_bytes', 'metadata_ring_bytes_not_power_of_two', dict(ring_bytes=131070)),
        ('reject_captured_bytes', 'captured_bytes_length_mismatch',
         dict(captured_bytes=31)),
        ('reject_config', 'metadata_config_mismatch', dict(config=dict(
            pid_argument=0, cpu_argument=-1, inherit=0, exclude_kernel=1,
            context_switch=1, sample_id_all=1, sample_type=['TID', 'TIME']))),
        ('reject_collector_complete', 'collector_incomplete',
         dict(collector_complete=False)),
        ('reject_collector_errors', 'collector_errors_present',
         dict(collector_errors=[dict(stage='drain', errno=5)])),
        ('reject_lifecycle', 'metadata_lifecycle_not_ok',
         dict(lifecycle=dict(disable_ok=True, reader_joined=False, munmap_ok=True,
                             close_ok=True))),
        ('reject_reader_policy_string', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy='SCHED_OTHER')),
        ('reject_reader_policy_empty_string', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy='')),
        ('reject_reader_policy_bool_true', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy=True)),
        ('reject_reader_policy_bool_false', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy=False)),
        ('reject_reader_policy_float', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy=0.0)),
        ('reject_reader_policy_nonzero', 'metadata_reader_policy_not_sched_other_zero',
         dict(reader_policy=1)),
        ('reject_captured_over_storage', 'captured_bytes_exceeds_storage_capacity',
         dict(storage_capacity_bytes=32)),
    ):
        fixture = Fixture()
        mutate_meta(fixture, **changes)
        expect_reject(module, name, fixture, reason)

    # reader_policy as the integer 0 is the accepted form (D's fix).
    fixture = Fixture()
    mutate_meta(fixture, reader_policy=0)
    code, payload, _, _ = run(module, fixture)
    check('accept_reader_policy_plain_zero', code == 0, 'code=%r payload=%r' % (code, payload))
    fixture.cleanup()

    # Duplicate JSON keys in metadata must be rejected, not last-wins.
    fixture = Fixture()
    fixture.write_metadata_text(
        json.dumps(base_metadata(len(raw_stream())))[:-1] + ', "reader_policy": 0}')
    expect_reject(module, 'reject_metadata_duplicate_key', fixture, 'metadata_duplicate_key')

    # Duplicate JSON keys in the windows document must be rejected too.
    fixture = Fixture()
    fixture.write_windows_text(
        json.dumps(windows_doc([dict(id='w1', start_ns=2_200_000, end_ns=2_600_000)]))[:-1]
        + ', "boot_id": "%s"}' % BOOT)
    code, payload, _, _ = run(module, fixture, with_windows=True)
    check('reject_windows_duplicate_key', code == 3
          and payload is not None and payload.get('reason') == 'windows_duplicate_key',
          'code=%r payload=%r' % (code, payload))
    fixture.cleanup()

    # Missing metadata field.
    fixture = Fixture()
    with open(fixture.meta_path, encoding='utf-8') as handle:
        document = json.load(handle)
    del document['reader_policy']
    with open(fixture.meta_path, 'w', encoding='utf-8') as handle:
        json.dump(document, handle)
    expect_reject(module, 'reject_missing_field', fixture, 'metadata_field_missing')

    # 5. Raw byte contract rejections.
    bad_switch_size = b''.join([
        switch_record(MISC_OUT, 2_000_000, 3, size=40),
        switch_record(0, 2_100_000, 3, size=40),
    ])
    expect_reject(module, 'reject_record_size', Fixture(raw=bad_switch_size),
                  'record_size_not_exact')

    # Genuine LOST / LOST_SAMPLES / CPU_WIDE records carry their REAL sizes, which
    # are not 32-byte records. Classification must come from the header, and the
    # cursor must advance by the real size so the following switch is still read.
    genuine_lost = framed_record(2, 16, time_ns=2_050_000)
    expect_reject(module, 'reject_lost_real_size16',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3) + genuine_lost
                          + switch_record(0, 2_100_000, 3)),
                  'record_lost_present')
    expect_reject(module, 'reject_lost_real_size24',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + framed_record(2, 24, time_ns=2_050_000)
                          + switch_record(0, 2_100_000, 3)),
                  'record_lost_present')
    expect_reject(module, 'reject_lost_samples_real_size16',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + framed_record(13, 16, time_ns=2_050_000)
                          + switch_record(0, 2_100_000, 3)),
                  'record_lost_samples_present')
    expect_reject(module, 'reject_cpu_wide_real_size40',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + framed_record(15, 40, time_ns=2_050_000)
                          + switch_record(0, 2_100_000, 3)),
                  'record_cpu_wide_present')
    # A LOST record with a size that is not a multiple of 32 is still a LOST
    # record: classification by type comes first, so the reason is the LOST
    # branch, not a generic alignment error.
    expect_reject(module, 'reject_lost_size_not_multiple',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + framed_record(2, 20, time_ns=2_050_000)
                          + b'\x00' * 12
                          + switch_record(0, 2_100_000, 3)),
                  'record_lost_present')

    lost = bytearray(32)
    lost[0:4] = (2).to_bytes(4, 'little')
    lost[6:8] = (32).to_bytes(2, 'little')
    expect_reject(module, 'reject_lost_record',
                  Fixture(raw=bytes(lost) + switch_record(0, 2_100_000, 3)),
                  'record_lost_present')
    lost_samples = bytearray(32)
    lost_samples[0:4] = (13).to_bytes(4, 'little')
    lost_samples[6:8] = (32).to_bytes(2, 'little')
    expect_reject(module, 'reject_lost_samples_record',
                  Fixture(raw=bytes(lost_samples) + switch_record(0, 2_100_000, 3)),
                  'record_lost_samples_present')

    cpu_wide = bytearray(32)
    cpu_wide[0:4] = (15).to_bytes(4, 'little')
    cpu_wide[6:8] = (32).to_bytes(2, 'little')
    expect_reject(module, 'reject_cpu_wide_record',
                  Fixture(raw=bytes(cpu_wide) + switch_record(MISC_OUT, 2_100_000, 3)),
                  'record_cpu_wide_present')

    unknown = bytearray(32)
    unknown[0:4] = (77).to_bytes(4, 'little')
    unknown[6:8] = (32).to_bytes(2, 'little')
    expect_reject(module, 'reject_unknown_record',
                  Fixture(raw=bytes(unknown) + switch_record(MISC_OUT, 2_100_000, 3)),
                  'record_unknown_type')

    expect_reject(module, 'reject_leftover_bytes',
                  Fixture(raw=raw_stream() + b'\x01\x02\x03'),
                  'record_header_truncated')

    expect_reject(module, 'reject_empty_raw', Fixture(raw=b''), 'raw_empty')

    expect_reject(module, 'reject_foreign_tid',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3, tid=OWNER_TID + 1)
                          + switch_record(0, 2_100_000, 3)),
                  'record_foreign_identity')

    expect_reject(module, 'reject_time_regression',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + switch_record(0, 1_900_000, 3)),
                  'record_time_not_increasing')

    expect_reject(module, 'reject_double_out',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + switch_record(MISC_OUT, 2_100_000, 3)),
                  'sequence_double_out')

    expect_reject(module, 'reject_leading_in',
                  Fixture(raw=switch_record(0, 2_000_000, 3)
                          + switch_record(MISC_OUT, 2_100_000, 3)),
                  'sequence_double_in')

    expect_reject(module, 'reject_trailing_out',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + switch_record(0, 2_100_000, 3)
                          + switch_record(MISC_OUT, 2_200_000, 3)),
                  'sequence_trailing_out')

    expect_reject(module, 'reject_preempt_on_in',
                  Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                          + switch_record(MISC_OUT_PREEMPT, 2_100_000, 3)),
                  'record_preempt_on_in')

    expect_reject(module, 'reject_time_before_enable',
                  Fixture(raw=switch_record(MISC_OUT, ENABLE_BEFORE - 1, 3)
                          + switch_record(0, ENABLE_AFTER + 1, 3)),
                  'record_time_outside_capture_bounds')

    expect_reject(module, 'reject_time_after_disable',
                  Fixture(raw=switch_record(MISC_OUT, DISABLE_AFTER + 1, 3)
                          + switch_record(0, DISABLE_AFTER + 2, 3)),
                  'record_time_outside_capture_bounds')

    expect_reject(module, 'reject_unknown_misc_bits',
                  Fixture(raw=switch_record(MISC_OUT | (1 << 3), 2_000_000, 3)
                          + switch_record(0, 2_100_000, 3)),
                  'record_misc_bits_unknown')

    # OUTER bounds: a record published inside the enable ioctl window
    # (enable_before_ns .. enable_after_ns) is legitimate and must be accepted;
    # one published before enable_before_ns must still be rejected.
    fixture = Fixture(raw=raw_with_outer_record())
    code, payload, _, _ = run(module, fixture)
    report = fixture.output()
    check('accept_record_in_enable_ioctl_window', code == 0,
          'code=%r payload=%r' % (code, payload))
    check('outer_bounds_recorded_in_output',
          report['decoded']['raw_time_bounds_used']
          == dict(first_ns=ENABLE_BEFORE, last_ns=DISABLE_AFTER,
                  kind='outer_enable_before_to_disable_after'),
          report['decoded']['raw_time_bounds_used'])
    check('windows_use_inner_bounds_in_output',
          report['decoded']['window_time_bounds_used']
          == dict(first_ns=ENABLE_AFTER, last_ns=DISABLE_BEFORE,
                  kind='inner_enable_after_to_disable_before'),
          report['decoded']['window_time_bounds_used'])
    check('outer_record_first_time_kept',
          report['pairs'][0]['out_time_ns'] == ENABLE_BEFORE + 50, report['pairs'][0])
    fixture.cleanup()

    # A windows entry that reaches into the enable ioctl window is outside the
    # guaranteed-enabled inner span and must be rejected.
    fixture = Fixture(raw=raw_with_outer_record(),
                      windows=windows_doc([
                          dict(id='w_outer', start_ns=ENABLE_BEFORE + 10,
                               end_ns=ENABLE_AFTER + 500)]))
    expect_reject(module, 'reject_window_reaching_enable_ioctl', fixture,
                  'windows_outside_capture_bounds', with_windows=True)

    # 6. Windows contract rejections.
    for name, reason, document in (
        ('reject_windows_schema', 'windows_schema_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], schema='other')),
        ('reject_windows_boot', 'windows_boot_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], boot='other')),
        ('reject_windows_owner_pid', 'windows_owner_pid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], pid=1)),
        ('reject_windows_owner_tid', 'windows_owner_tid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], tid=1)),
        ('reject_windows_owner_pid_float', 'windows_owner_pid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)],
                     pid=float(OWNER_PID))),
        ('reject_windows_owner_tid_float', 'windows_owner_tid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)],
                     tid=float(OWNER_TID))),
        ('reject_windows_owner_pid_bool', 'windows_owner_pid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], pid=True)),
        ('reject_windows_owner_tid_bool', 'windows_owner_tid_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)], tid=False)),
        ('reject_windows_clock', 'windows_clock_id_mismatch',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000)],
                     clock='CLOCK_REALTIME')),
        ('reject_windows_empty', 'windows_list_invalid', windows_doc([])),
        ('reject_windows_bounds', 'windows_bounds_not_positive',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_000_000)])),
        ('reject_windows_outside', 'windows_outside_capture_bounds',
         windows_doc([dict(id='w', start_ns=ENABLE_BEFORE - 10, end_ns=2_100_000)])),
        ('reject_windows_duplicate_id', 'windows_id_duplicate',
         windows_doc([dict(id='w', start_ns=2_000_000, end_ns=2_100_000),
                      dict(id='w', start_ns=3_000_000, end_ns=3_100_000)])),
        ('reject_windows_id_type', 'windows_id_invalid',
         windows_doc([dict(id=7, start_ns=2_000_000, end_ns=2_100_000)])),
        ('reject_windows_bool_bounds', 'windows_bounds_invalid',
         windows_doc([dict(id='w', start_ns=True, end_ns=2_100_000)])),
    ):
        expect_reject(module, name, Fixture(windows=document), reason, with_windows=True)

    # 7. Rejection determinism: the same bad input gives the same reason twice.
    fixture = Fixture(raw=switch_record(MISC_OUT, DISABLE_BEFORE + 1, 3)
                      + switch_record(0, DISABLE_BEFORE + 2, 3))
    code, payload, _, _ = run(module, fixture)
    check('accept_record_in_disable_ioctl_window', code == 0, (code, payload))
    fixture.cleanup()

    fixture = Fixture(raw=switch_record(MISC_OUT, 2_000_000, 3)
                      + switch_record(MISC_OUT, 2_100_000, 3))
    first = run(module, fixture)[1]
    second = run(module, fixture)[1]
    check('rejection_is_deterministic', first == second and first.get('reason')
          == 'sequence_double_out', (first, second))
    fixture.cleanup()

    failed = [case for case in CASES if not case['ok']]
    print('\n%d checks, %d failed' % (len(CASES), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
