#!/usr/bin/env python3
"""Strict offline consumer for a wksim self-thread switch stream.

Implements the reader side of docs/coordination/perf-stream-contract-20260913.md:
raw perf record bytes plus the metadata JSON written by the capture side are
validated, decoded into complete switch pairs, optionally intersected with a
separately supplied windows JSON, and written to a NEW output file.

Rules enforced (every violation is an error, never a silent skip):

  metadata  schema/classification/full_acceptance, owner pid and tid, boot and
            clock identity, enable/disable ordering, ring and storage geometry,
            the exact capture config, collector_complete with zero collector
            errors, and every lifecycle boolean;
  bytes     captured_bytes must equal the raw file length exactly; the file must
            be a whole number of exactly 32-byte PERF_RECORD_SWITCH records with
            no leftover bytes;
  records   header type must be SWITCH (LOST, LOST_SAMPLES, SWITCH_CPU_WIDE and
            unknown types are rejected, not skipped); size must be exactly 32;
            misc may only carry SWITCH_OUT and SWITCH_OUT_PREEMPT, and preempt is
            illegal on a switch-in; the identity must be the owner pid AND tid
            and both must be positive; timestamps must strictly increase and lie
            inside the capture's outer clock bounds; the out/in sequence must
            alternate and end closed, with at least one complete pair;
  windows   optional JSON object {schema: wksim.perf_windows.v1, boot_id,
            owner_pid, owner_tid, clock_id: CLOCK_MONOTONIC, windows:[{id,
            start_ns, end_ns}]}. It is bound to the metadata (same boot and
            owner, same clock); ids must be non-empty and unique; each window
            must satisfy 0 <= start_ns < end_ns and lie inside the capture
            bounds. Intersections with observed pair spans use integer
            nanoseconds.

This tool never overwrites an existing output, never opens a perf event and
computes no flight verdict: it emits boundary observations only.
"""
import argparse
import hashlib
import json
import os
import sys

TOOL = 'wksim-perf-stream-consumer'
TOOL_VERSION = '1'
METADATA_SCHEMA = 'wksim.perf_switch_stream.v1'
WINDOWS_SCHEMA = 'wksim.perf_windows.v1'
CLASSIFICATION = 'diagnostic_only'
CLOCK_ID = 'CLOCK_MONOTONIC'
RECORD_TYPE_SWITCH = 14
RECORD_TYPE_LOST = 2
RECORD_TYPE_LOST_SAMPLES = 13
RECORD_TYPE_SWITCH_CPU_WIDE = 15
RECORD_BYTES = 32
HEADER_BYTES = 8
MAX_SAMPLE_ID_BYTES = 24
MISC_SWITCH_OUT = 1 << 13
MISC_SWITCH_OUT_PREEMPT = 1 << 14
RING_PRESSURE_GUARD_BYTES = 4096
EXPECTED_CONFIG = {
    'pid_argument': 0,
    'cpu_argument': -1,
    'inherit': 0,
    'exclude_kernel': 1,
    'context_switch': 1,
    'sample_id_all': 1,
    'sample_type': ['TID', 'TIME', 'CPU'],
}
REQUIRED_METADATA_FIELDS = (
    'schema', 'classification', 'full_acceptance', 'owner_pid', 'owner_tid', 'boot_id',
    'clock_id', 'enable_before_ns', 'enable_after_ns', 'disable_before_ns',
    'disable_after_ns', 'ring_bytes', 'storage_capacity_bytes', 'captured_bytes',
    'reader_policy', 'config', 'collector_complete', 'collector_errors', 'lifecycle',
)
LIFECYCLE_FIELDS = ('disable_ok', 'reader_joined', 'munmap_ok', 'close_ok')
SANITY_MAX_RECORDS = 100_000_000


class ContractError(Exception):
    """A contract violation. Carries a stable machine-readable reason."""

    def __init__(self, reason, detail=''):
        self.reason = reason
        self.detail = detail
        super().__init__('%s%s' % (reason, (': ' + detail) if detail else ''))


class _DuplicateKey(Exception):
    """Raised by the JSON object_pairs_hook when a key repeats."""

    def __init__(self, key):
        self.key = key
        super().__init__(str(key))


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def is_plain_int(value):
    return type(value) is int


def is_int_in_range(value, low, high=None):
    if not is_plain_int(value):
        return False
    if value < low:
        return False
    return high is None or value <= high


def is_power_of_two(value):
    return is_plain_int(value) and value > 0 and (value & (value - 1)) == 0


def sha256_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path):
    if not os.path.isfile(path):
        raise ContractError('metadata_missing', path)
    with open(path, 'rb') as handle:
        blob = handle.read()
    try:
        value = json.loads(blob.decode('utf-8'), object_pairs_hook=_no_duplicate_keys)
    except _DuplicateKey as error:
        raise ContractError('metadata_duplicate_key', repr(error.key))
    except (UnicodeDecodeError, ValueError) as error:
        raise ContractError('metadata_not_json', str(error))
    if not isinstance(value, dict):
        raise ContractError('metadata_not_object')
    return value, sha256_bytes(blob)


def validate_kernel_loss_counter(meta):
    fields = ('kernel_lost_read_ok', 'kernel_lost_read_bytes',
              'kernel_lost_read_errno', 'kernel_lost_count')
    if not any(name in meta for name in fields):
        return False
    if not all(name in meta for name in fields):
        raise ContractError('kernel_loss_counter_fields_missing')
    config = meta['config']
    if type(config.get('read_format')) is not int or config['read_format'] != 16:
        raise ContractError('kernel_loss_counter_format_invalid')
    if meta['kernel_lost_read_ok'] is not True:
        raise ContractError('kernel_loss_counter_unavailable')
    if (type(meta['kernel_lost_read_bytes']) is not int or meta['kernel_lost_read_bytes'] != 16
            or type(meta['kernel_lost_read_errno']) is not int or meta['kernel_lost_read_errno'] != 0):
        raise ContractError('kernel_loss_counter_read_invalid')
    if not is_int_in_range(meta['kernel_lost_count'], 0, (1 << 64) - 1):
        raise ContractError('kernel_loss_counter_value_invalid')
    if meta['kernel_lost_count'] != 0:
        raise ContractError('kernel_loss_counter_nonzero', str(meta['kernel_lost_count']))
    return True


def validate_metadata(meta, raw_len):
    for field in REQUIRED_METADATA_FIELDS:
        if field not in meta:
            raise ContractError('metadata_field_missing', field)
    if meta['schema'] != METADATA_SCHEMA:
        raise ContractError('metadata_schema_mismatch', repr(meta['schema']))
    if meta['classification'] != CLASSIFICATION:
        raise ContractError('metadata_classification_mismatch', repr(meta['classification']))
    if meta['full_acceptance'] is not False:
        raise ContractError('metadata_full_acceptance_not_false', repr(meta['full_acceptance']))
    if not is_int_in_range(meta['owner_pid'], 1):
        raise ContractError('metadata_owner_pid_invalid', repr(meta['owner_pid']))
    if not is_int_in_range(meta['owner_tid'], 1):
        raise ContractError('metadata_owner_tid_invalid', repr(meta['owner_tid']))
    if not isinstance(meta['boot_id'], str) or not meta['boot_id']:
        raise ContractError('metadata_boot_id_invalid', repr(meta['boot_id']))
    if meta['clock_id'] != CLOCK_ID:
        raise ContractError('metadata_clock_id_mismatch', repr(meta['clock_id']))

    bounds = {}
    for field in ('enable_before_ns', 'enable_after_ns', 'disable_before_ns',
                  'disable_after_ns'):
        if not is_int_in_range(meta[field], 0):
            raise ContractError('metadata_clock_bound_invalid', '%s=%r' % (field, meta[field]))
        bounds[field] = meta[field]
    if not (bounds['enable_before_ns'] <= bounds['enable_after_ns']
            <= bounds['disable_before_ns'] <= bounds['disable_after_ns']):
        raise ContractError('metadata_clock_bounds_out_of_order', repr(bounds))
    # Raw records are bounded by the OUTER span (records published during the
    # enable/disable ioctls are legitimate); windows are bounded by the INNER span
    # that is guaranteed enabled.
    bounds['outer_first_ns'] = bounds['enable_before_ns']
    bounds['outer_last_ns'] = bounds['disable_after_ns']
    bounds['inner_first_ns'] = bounds['enable_after_ns']
    bounds['inner_last_ns'] = bounds['disable_before_ns']

    if not is_power_of_two(meta['ring_bytes']):
        raise ContractError('metadata_ring_bytes_not_power_of_two', repr(meta['ring_bytes']))
    if meta['ring_bytes'] < RECORD_BYTES + HEADER_BYTES:
        raise ContractError('metadata_ring_bytes_too_small', repr(meta['ring_bytes']))
    if not is_int_in_range(meta['storage_capacity_bytes'], 1):
        raise ContractError('metadata_storage_capacity_invalid',
                            repr(meta['storage_capacity_bytes']))
    if not is_int_in_range(meta['captured_bytes'], 0):
        raise ContractError('metadata_captured_bytes_invalid', repr(meta['captured_bytes']))
    if meta['captured_bytes'] > meta['storage_capacity_bytes']:
        raise ContractError('captured_bytes_exceeds_storage_capacity',
                            'captured=%r storage=%r' % (meta['captured_bytes'],
                                                        meta['storage_capacity_bytes']))
    if meta['captured_bytes'] != raw_len:
        raise ContractError('captured_bytes_length_mismatch',
                            'metadata=%r raw=%r' % (meta['captured_bytes'], raw_len))
    # reader_policy is the reader thread's actual SCHED_OTHER policy value: the
    # contract requires the integer 0. A string, a float and a bool are all
    # different types and are rejected together with any non-zero integer.
    if type(meta['reader_policy']) is not int or meta['reader_policy'] != 0:
        raise ContractError('metadata_reader_policy_not_sched_other_zero',
                            repr(meta['reader_policy']))

    config = meta['config']
    if not isinstance(config, dict):
        raise ContractError('metadata_config_not_object')
    for key, expected in EXPECTED_CONFIG.items():
        if key not in config:
            raise ContractError('metadata_config_field_missing', key)
        if config[key] != expected or type(config[key]) is not type(expected):
            raise ContractError('metadata_config_mismatch',
                                '%s=%r expected=%r' % (key, config[key], expected))

    bounds['kernel_counter_verified'] = validate_kernel_loss_counter(meta)

    if meta['collector_complete'] is not True:
        raise ContractError('collector_incomplete', repr(meta['collector_complete']))
    errors = meta['collector_errors']
    if not isinstance(errors, list):
        raise ContractError('collector_errors_not_list', repr(type(errors).__name__))
    if errors:
        raise ContractError('collector_errors_present', json.dumps(errors)[:200])

    lifecycle = meta['lifecycle']
    if not isinstance(lifecycle, dict):
        raise ContractError('metadata_lifecycle_not_object')
    for field in LIFECYCLE_FIELDS:
        if field not in lifecycle:
            raise ContractError('metadata_lifecycle_field_missing', field)
        if lifecycle[field] is not True:
            raise ContractError('metadata_lifecycle_not_ok', '%s=%r' % (field, lifecycle[field]))

    return bounds


def read_raw(path):
    if not os.path.isfile(path):
        raise ContractError('raw_missing', path)
    with open(path, 'rb') as handle:
        blob = handle.read()
    return blob, sha256_bytes(blob)


def decode_records(blob, meta, bounds):
    """Decode the published record stream by each record's real header size.

    Every record is classified from its 8-byte header first, so a LOST,
    LOST_SAMPLES or CPU_WIDE record is judged by its own real size (which is not
    a multiple of 32) instead of being forced into a 32-byte slot; the cursor then
    advances by the declared size, so a genuinely sized non-switch record can no
    longer be mistaken for a malformed switch record.

    Raw timestamps are checked against the OUTER capture bounds
    [enable_before_ns, disable_after_ns]: records published during the enable and
    disable ioctl calls are legitimate. Only windows use the inner enabled span.
    """
    if len(blob) == 0:
        raise ContractError('raw_empty')
    owner_pid = meta['owner_pid']
    owner_tid = meta['owner_tid']
    records = []
    seen_out = 0
    seen_in = 0
    expected_out = True
    previous_time = None
    offset = 0
    sequence = 0
    while offset < len(blob):
        remaining = len(blob) - offset
        if remaining < HEADER_BYTES:
            raise ContractError('record_header_truncated',
                                'offset=%d remaining=%d' % (offset, remaining))
        record_type = int.from_bytes(blob[offset:offset + 4], 'little')
        misc = int.from_bytes(blob[offset + 4:offset + 6], 'little')
        size = int.from_bytes(blob[offset + 6:offset + 8], 'little')
        if size < HEADER_BYTES:
            raise ContractError('record_size_below_header',
                                'offset=%d size=%d' % (offset, size))
        if size > remaining:
            raise ContractError('record_size_beyond_stream',
                                'offset=%d size=%d remaining=%d' % (offset, size, remaining))
        chunk = blob[offset:offset + size]

        # Classify by the record's OWN type first. Only a SWITCH record is a
        # 32-byte record; LOST (16/24/32), LOST_SAMPLES (16/24) and CPU_WIDE (40)
        # have their own real sizes, so a non-multiple-of-32 size is not by itself
        # an alignment error.
        if record_type != RECORD_TYPE_SWITCH:
            if record_type == RECORD_TYPE_LOST:
                raise ContractError('record_lost_present',
                                    'offset=%d size=%d' % (offset, size))
            if record_type == RECORD_TYPE_LOST_SAMPLES:
                raise ContractError('record_lost_samples_present',
                                    'offset=%d size=%d' % (offset, size))
            if record_type == RECORD_TYPE_SWITCH_CPU_WIDE:
                raise ContractError('record_cpu_wide_present',
                                    'offset=%d size=%d' % (offset, size))
            raise ContractError('record_unknown_type',
                                'offset=%d type=%d size=%d' % (offset, record_type, size))

        if size != RECORD_BYTES:
            raise ContractError('record_size_not_exact',
                                'offset=%d size=%d expected=%d' % (offset, size, RECORD_BYTES))
        index = sequence
        sequence += 1
        if sequence > SANITY_MAX_RECORDS:
            raise ContractError('record_count_implausible', str(sequence))
        if misc & ~(MISC_SWITCH_OUT | MISC_SWITCH_OUT_PREEMPT):
            raise ContractError('record_misc_bits_unknown',
                                'record=%d misc=%#06x' % (index, misc))
        pid = int.from_bytes(chunk[HEADER_BYTES:HEADER_BYTES + 4], 'little', signed=True)
        tid = int.from_bytes(chunk[HEADER_BYTES + 4:HEADER_BYTES + 8], 'little', signed=True)
        time_ns = int.from_bytes(chunk[HEADER_BYTES + 8:HEADER_BYTES + 16], 'little')
        cpu = int.from_bytes(chunk[HEADER_BYTES + 16:HEADER_BYTES + 20], 'little')
        if pid != owner_pid or tid != owner_tid:
            raise ContractError('record_foreign_identity',
                                'record=%d pid=%d tid=%d' % (index, pid, tid))
        if pid <= 0 or tid <= 0:
            raise ContractError('record_nonpositive_identity',
                                'record=%d pid=%d tid=%d' % (index, pid, tid))
        is_out = bool(misc & MISC_SWITCH_OUT)
        is_preempt = bool(misc & MISC_SWITCH_OUT_PREEMPT)
        if not is_out and is_preempt:
            raise ContractError('record_preempt_on_in', 'record=%d' % index)
        if previous_time is not None and time_ns <= previous_time:
            raise ContractError('record_time_not_increasing',
                                'record=%d time=%d previous=%d' % (index, time_ns, previous_time))
        previous_time = time_ns
        if not (bounds['outer_first_ns'] <= time_ns <= bounds['outer_last_ns']):
            raise ContractError('record_time_outside_capture_bounds',
                                'record=%d time=%d outer=[%d,%d]'
                                % (index, time_ns, bounds['outer_first_ns'],
                                   bounds['outer_last_ns']))
        if is_out:
            if not expected_out:
                raise ContractError('sequence_double_out', 'record=%d' % index)
            expected_out = False
            seen_out += 1
        else:
            if expected_out:
                raise ContractError('sequence_double_in', 'record=%d' % index)
            expected_out = True
            seen_in += 1
        records.append(dict(index=index, kind='out' if is_out else 'in', time_ns=time_ns,
                            cpu=cpu, preempt=is_preempt))
        offset += size
    if expected_out is False:
        raise ContractError('sequence_trailing_out')
    if seen_out == 0 or seen_in == 0 or seen_out != seen_in:
        raise ContractError('sequence_no_complete_pair',
                            'out=%d in=%d' % (seen_out, seen_in))
    return records, seen_out, seen_in


def build_pairs(records):
    pairs = []
    for position in range(0, len(records), 2):
        out_record = records[position]
        in_record = records[position + 1]
        pairs.append(dict(
            sequence=len(pairs),
            out_index=out_record['index'], in_index=in_record['index'],
            out_time_ns=out_record['time_ns'], in_time_ns=in_record['time_ns'],
            duration_ns=in_record['time_ns'] - out_record['time_ns'],
            out_cpu=out_record['cpu'], in_cpu=in_record['cpu'],
            out_preempt=out_record['preempt'],
            cpu_changed=out_record['cpu'] != in_record['cpu'],
        ))
    return pairs


def load_windows(path, meta, bounds):
    if not os.path.isfile(path):
        raise ContractError('windows_missing', path)
    with open(path, 'rb') as handle:
        blob = handle.read()
    try:
        value = json.loads(blob.decode('utf-8'), object_pairs_hook=_no_duplicate_keys)
    except _DuplicateKey as error:
        raise ContractError('windows_duplicate_key', repr(error.key))
    except (UnicodeDecodeError, ValueError) as error:
        raise ContractError('windows_not_json', str(error))
    if not isinstance(value, dict):
        raise ContractError('windows_not_object')
    if value.get('schema') != WINDOWS_SCHEMA:
        raise ContractError('windows_schema_mismatch', repr(value.get('schema')))
    if value.get('boot_id') != meta['boot_id']:
        raise ContractError('windows_boot_mismatch',
                            '%r != %r' % (value.get('boot_id'), meta['boot_id']))
    # Owner identity must be a plain int as well: a float or bool that compares
    # equal to the metadata value must not pass on == alone.
    window_pid = value.get('owner_pid')
    if not is_int_in_range(window_pid, 1) or window_pid != meta['owner_pid']:
        raise ContractError('windows_owner_pid_mismatch', repr(window_pid))
    window_tid = value.get('owner_tid')
    if not is_int_in_range(window_tid, 1) or window_tid != meta['owner_tid']:
        raise ContractError('windows_owner_tid_mismatch', repr(window_tid))
    if value.get('clock_id') != CLOCK_ID:
        raise ContractError('windows_clock_id_mismatch', repr(value.get('clock_id')))
    entries = value.get('windows')
    if not isinstance(entries, list) or not entries:
        raise ContractError('windows_list_invalid', repr(type(entries).__name__))
    windows = []
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractError('windows_entry_not_object')
        window_id = entry.get('id')
        if not isinstance(window_id, str) or not window_id:
            raise ContractError('windows_id_invalid', repr(window_id))
        if window_id in seen_ids:
            raise ContractError('windows_id_duplicate', window_id)
        seen_ids.add(window_id)
        start = entry.get('start_ns')
        end = entry.get('end_ns')
        if not is_int_in_range(start, 0) or not is_int_in_range(end, 0):
            raise ContractError('windows_bounds_invalid', '%s start=%r end=%r'
                                % (window_id, start, end))
        if start >= end:
            raise ContractError('windows_bounds_not_positive', window_id)
        if start < bounds['inner_first_ns'] or end > bounds['inner_last_ns']:
            raise ContractError('windows_outside_capture_bounds',
                                '%s [%d,%d] inner=[%d,%d]'
                                % (window_id, start, end, bounds['inner_first_ns'],
                                   bounds['inner_last_ns']))
        windows.append(dict(id=window_id, start_ns=start, end_ns=end))
    return windows, sha256_bytes(blob)


def intersect_windows(pairs, windows):
    """Integer-nanosecond intersections of each pair span with each window."""
    result = []
    for window in windows:
        overlaps = []
        total = 0
        for pair in pairs:
            start = max(pair['out_time_ns'], window['start_ns'])
            end = min(pair['in_time_ns'], window['end_ns'])
            if end > start:
                duration = end - start
                overlaps.append(dict(sequence=pair['sequence'], start_ns=start, end_ns=end,
                                     duration_ns=duration))
                total += duration
        result.append(dict(id=window['id'], start_ns=window['start_ns'],
                           end_ns=window['end_ns'],
                           window_duration_ns=window['end_ns'] - window['start_ns'],
                           intersecting_pairs=len(overlaps),
                           intersection_total_ns=total,
                           intersections=overlaps))
    return result


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog=TOOL, description='Strict offline switch-stream consumer (read-only inputs).')
    parser.add_argument('--raw', required=True, help='raw perf record bytes from stop')
    parser.add_argument('--metadata', required=True, help='metadata JSON from stop')
    parser.add_argument('--require-kernel-counter', action='store_true',
                        help='reject legacy captures without a valid post-disable loss counter')
    parser.add_argument('--windows', help='optional windows JSON (wksim.perf_windows.v1)')
    parser.add_argument('--output', required=True, help='new output JSON (must not exist)')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if os.path.exists(args.output):
            raise ContractError('output_exists_refusing_overwrite', args.output)
        meta, metadata_sha = load_metadata(args.metadata)
        blob, raw_sha = read_raw(args.raw)
        bounds = validate_metadata(meta, len(blob))
        if args.require_kernel_counter and not bounds['kernel_counter_verified']:
            raise ContractError('kernel_loss_counter_required')
        records, out_count, in_count = decode_records(blob, meta, bounds)
        pairs = build_pairs(records)
        window_completeness = None
        if bounds['kernel_counter_verified']:
            window_completeness = dict(verified_from_ns=bounds['inner_first_ns'],
                                       verified_until_ns=bounds['inner_last_ns'],
                                       method='post_disable_kernel_event_loss_counter',
                                       kernel_lost_count=0,
                                       scope='configured event capture; not other tasks or physical accuracy')
        windows = None
        windows_sha = None
        intersections = None
        if args.windows:
            windows, windows_sha = load_windows(args.windows, meta, bounds)
            intersections = intersect_windows(pairs, windows)
        first_time = records[0]['time_ns']
        last_time = records[-1]['time_ns']
        report = dict(
            schema='wksim.perf_switch_consumer.v1',
            tool=TOOL, tool_version=TOOL_VERSION,
            classification=CLASSIFICATION, full_acceptance=False,
            flight_conclusion=None,
            scope=('decoded switch-pair boundaries and optional window intersections; '
                   'not proof of which task ran, why scheduling occurred or exact CPU '
                   'execution time'),
            inputs=dict(
                raw_path=os.path.abspath(args.raw), raw_sha256=raw_sha,
                raw_bytes=len(blob),
                metadata_path=os.path.abspath(args.metadata), metadata_sha256=metadata_sha,
                windows_path=os.path.abspath(args.windows) if args.windows else None,
                windows_sha256=windows_sha,
            ),
            capture=dict(
                boot_id=meta['boot_id'], owner_pid=meta['owner_pid'],
                owner_tid=meta['owner_tid'], clock_id=meta['clock_id'],
                enable_before_ns=meta['enable_before_ns'],
                enable_after_ns=meta['enable_after_ns'],
                disable_before_ns=meta['disable_before_ns'],
                disable_after_ns=meta['disable_after_ns'],
                ring_bytes=meta['ring_bytes'],
                storage_capacity_bytes=meta['storage_capacity_bytes'],
                captured_bytes=meta['captured_bytes'],
                reader_policy=meta['reader_policy'],
                ring_pressure_guard_bytes=RING_PRESSURE_GUARD_BYTES,
            ),
            decoded=dict(
                records=len(records), switch_out=out_count, switch_in=in_count,
                pairs=len(pairs), first_time_ns=first_time, last_time_ns=last_time,
                observed_span_ns=last_time - first_time,
                pair_duration_total_ns=sum(pair['duration_ns'] for pair in pairs),
                pair_duration_max_ns=max(pair['duration_ns'] for pair in pairs),
                cpus=sorted({record['cpu'] for record in records}),
                preempt_outs=sum(1 for record in records if record['preempt']),
                raw_time_bounds_used=dict(first_ns=bounds['outer_first_ns'],
                                          last_ns=bounds['outer_last_ns'],
                                          kind='outer_enable_before_to_disable_after'),
                window_time_bounds_used=dict(first_ns=bounds['inner_first_ns'],
                                             last_ns=bounds['inner_last_ns'],
                                             kind='inner_enable_after_to_disable_before'),
            ),
            window_completeness=window_completeness,
            stream_completeness_proven=bounds['kernel_counter_verified'],
            stream_completeness_reason=(
                'post-disable PERF_FORMAT_LOST is zero and the complete collector/raw stream passed validation'
                if bounds['kernel_counter_verified'] else
                'legacy capture lacks a validated post-disable kernel loss counter; '
                'pending LOST and stream completeness remain unproven'),
            pairs=pairs,
            windows=intersections,
            notes=[
                'metadata and raw bytes are bound by SHA-256; the raw file length must equal '
                'captured_bytes exactly and must not exceed storage_capacity_bytes',
                'LOST, LOST_SAMPLES, CPU_WIDE, unknown, truncated and unpaired records are '
                'errors, never skipped; non-switch records are classified by their own header '
                'size, not forced into a 32-byte slot',
                'raw record timestamps are checked against the outer span '
                '[enable_before_ns, disable_after_ns]; windows use the inner enabled span '
                '[enable_after_ns, disable_before_ns]',
                'window intersections are boundary observations in integer nanoseconds',
                'stream completeness requires a valid zero post-disable kernel loss counter; '
                'legacy or sentinel-only captures do not prove their final tail',
            ],
        )
        with open(args.output, 'x', encoding='utf-8') as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + '\n')
    except ContractError as error:
        print(json.dumps(dict(ok=False, reason=error.reason, detail=error.detail,
                              tool=TOOL, tool_version=TOOL_VERSION)), file=sys.stderr)
        return 3
    except OSError as error:
        print(json.dumps(dict(ok=False, reason='io_error', detail=str(error), tool=TOOL)),
              file=sys.stderr)
        return 4
    print(json.dumps(dict(ok=True, output=os.path.abspath(args.output), pairs=len(pairs),
                          records=len(records), windows=len(intersections) if intersections
                          else 0, raw_sha256=raw_sha, metadata_sha256=metadata_sha),
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
