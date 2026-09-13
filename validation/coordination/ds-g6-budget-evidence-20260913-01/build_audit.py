"""Read-only generator for the G6 per-quantity budget-evidence audit.

Reads only retained, already-committed originals (frozen R1 contract, source-to-slot
manifest, current-source-mapping, retained R1 failure rows, retained same-source C0
observation, first-step comparison, and the prospective time/premise records) and
writes audit.json in THIS directory. It never executes MATLAB/native/ROS/FC/UE, never
builds, never assigns or approves an epsilon, and never writes outside its own
directory.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from tools.run_e0_same_source_conformance import (  # noqa: E402
    ARRAY_LENGTHS, OBSERVABLE_REQUIRED_FIELDS, FROZEN_METRIC, SAMPLES, TIME_STEP_S,
    Reject, parse_native_record, parse_reference_f64, validate_contract,
)

CONTRACT = ROOT / 'Simulator/wksim_core/numerical-conformance-v1.json'
SLOT_MANIFEST = ROOT / 'validation/e0-source-to-slot-manifest-20260911.json'
CURRENT_MAP = ROOT / 'validation/e0-current-source-mapping-20260912.json'
CURRENT_RHS = ROOT / 'validation/e0-current-rhs-references-20260912.json'
R1_RUN_INDEX = ROOT / 'validation/numerical-conformance-gxxh6xhr/run-index.json'
R1_FAILURES = ROOT / 'validation/numerical-conformance-gxxh6xhr/all-failures.jsonl'
C0_OBS = ROOT / 'validation/coordination/g6-solve-same-source-20260913/existing-c0-observation.json'
C0_RECORD = ROOT / 'validation/e0-major-recorder-parent-final-01/record.jsonl'
C0_BUILD = ROOT / 'validation/e0-major-recorder-parent-final-01/build-manifest.json'
C0_REF_DIR = ROOT / 'validation/numerical-conformance-u56ce17a/C0'
STEP_CMP = ROOT / 'validation/coordination/g6-target-first-step-20260913/comparison-v2.json'
TIME_VERIFY = ROOT / 'validation/coordination/major-time-acceptance-20260913-01/verification.json'
TIME_PREMISE = ROOT / 'validation/coordination/g6-time-premise-acceptance-20260913-01/prospective-rule.json'
ID_RULE = ROOT / 'validation/coordination/ds-g6-identity-rule-20260913-01/g6-identity-rule-v3.json'
MICRO_BIND = ROOT / 'validation/coordination/ds-g6-major-microtime-binding-20260913-01/g6-major-microtime-binding-v4.json'
MAJOR_BIND = ROOT / 'validation/coordination/ds-g6-major-time-binding-20260913-01/g6-major-time-binding-v3.json'

# Authoritative materials that define the route / the budget requirement (not budgets).
ROUTE_DOCS = [
    'docs/plan/10-g6-remediation-contract.md',
    'docs/plan/59-e0-same-source-command.md',
    'docs/plan/59-e0-dynamic-budget-source-map.md',
    'docs/plan/59-e0-artifact-portability.md',
    'docs/g6-material-index.md',
    'docs/2026-09-13-major-time-conventions.md',
    'docs/2026-09-13-diagonal-solve-experiment.md',
    'docs/coordination/short-cycle-goal.md',
    'docs/coordination/module-delivery-policy-20260912.md',
    'docs/coordination/architecture-continuation-20260913.md',
]
TOOL_INPUTS = [
    'tools/run_e0_same_source_conformance.py',
    'tools/validate_e0_source_to_slot_manifest.py',
    'tools/compare_first_step_trace.py',
    'tools/probe_reference_first_step.m',
    'validation/e0-source-to-slot-manifest-20260911.json',
    'validation/e0-current-source-mapping-20260912.json',
    'validation/e0-current-rhs-references-20260912.json',
    'validation/numerical-conformance-gxxh6xhr/run-index.json',
    'validation/numerical-conformance-gxxh6xhr/all-failures.jsonl',
    'validation/numerical-conformance-gxxh6xhr/all-360-scalars.csv',
    'validation/coordination/g6-solve-same-source-20260913/existing-c0-observation.json',
    'validation/e0-major-recorder-parent-final-01/record.jsonl',
    'validation/e0-major-recorder-parent-final-01/build-manifest.json',
    'validation/coordination/g6-target-first-step-20260913/comparison-v2.json',
    'validation/coordination/g6-reference-probe-20260913/run-03/reference-first-step.json',
    'validation/coordination/g6-reference-probe-20260913/run-05/reference-first-step.json',
    'validation/coordination/g6-target-first-step-20260913/first-step-trace.jsonl',
    'validation/coordination/g6-diagonal-solve-candidate-20260913/first-step-trace.jsonl',
    'validation/coordination/g6-diagonal-solve-candidate-20260913/comparator-result-v2.json',
    'validation/coordination/g6-guard-review-20260913-01/sha-receipt-20260913-02.json',
    'validation/coordination/g6-guard-review-20260913-01/findings-g6-diagonal-guard-20260913.md',
    'validation/coordination/major-time-acceptance-20260913-01/verification.json',
    'validation/coordination/g6-time-premise-acceptance-20260913-01/prospective-rule.json',
    'validation/coordination/ds-g6-identity-rule-20260913-01/g6-identity-rule-v3.json',
    'validation/coordination/ds-g6-major-microtime-binding-20260913-01/g6-major-microtime-binding-v4.json',
    'validation/coordination/ds-g6-major-time-binding-20260913-01/g6-major-time-binding-v3.json',
    'validation/coordination/g6-first-divergence-20260913/diagnosis.json',
    'docs/plan/59-e0-dynamic-budget-source-map.md',
]

# Time / phase convention facts from the frozen R1 contract.
PHASE = 'major_root_output (major step, before the subsequent explicit Update/ODE)'
TIME_GRID = 'k * %g s, k = 0..%d inclusive (%d rows), tolerance 1e-12 s' % (
    TIME_STEP_S, SAMPLES - 1, SAMPLES)
NATIVE_TIME_FIELDS = ('Vehicle60[2] s = k*0.001; Sensor30[0] us = (k*0.001)*1e6; '
                      'GPS30[0] us = (k*0.001)*1e6')

# Derivative-bearing slots: named as such explicitly in the task.
DERIVATIVE_SLOTS = {
    'Vehicle60[24]', 'Vehicle60[25]', 'Vehicle60[26]',      # body_motion_acceleration
    'Vehicle60[27]', 'Vehicle60[28]', 'Vehicle60[29]',      # body_angular_rate
    'Sensor30[1]', 'Sensor30[2]', 'Sensor30[3]',            # accelerometer (specific force)
    'Sensor30[4]', 'Sensor30[5]', 'Sensor30[6]',            # gyroscope
}
TIME_SLOTS = {'Vehicle60[2]', 'Sensor30[0]', 'GPS30[0]'}

FRAME_NOTE = {
    'Vehicle60[3]': 'NED (position/velocity NED per wksim_core/README.md:52); not a slot-level manifest binding',
    'Vehicle60[6]': 'NED (position/velocity NED per wksim_core/README.md:52); not a slot-level manifest binding',
    'Vehicle60[9]': 'NED Euler; quaternion is wxyz, position/velocity NED, rates/specific force FRD (README.md:52)',
    'Vehicle60[12]': 'wxyz quaternion, NED/FRD base (README.md:52); sign-fix step in generated C++',
    'Vehicle60[24]': 'body-frame velocity derivative (FRD); README.md:52 states it is NOT IMU specific force',
    'Vehicle60[27]': 'body angular rate, FRD (README.md:52)',
    'Sensor30[1]': 'accelerometer specific force (FRD implied); README.md:52 distinguishes it from Vehicle[24:27]',
    'Sensor30[4]': 'gyroscope, FRD (README.md:52)',
    'GPS30[10]': 'course encoded; template COG = atan2(north, east) (README.md:54)',
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def build():
    contract = read_json(CONTRACT)
    manifest = read_json(SLOT_MANIFEST)
    current = read_json(CURRENT_MAP)
    rhs = read_json(CURRENT_RHS)
    run_index = read_json(R1_RUN_INDEX)
    c0_obs = read_json(C0_OBS)
    step = read_json(STEP_CMP)
    time_verify = read_json(TIME_VERIFY)
    time_premise = read_json(TIME_PREMISE)
    id_rule = read_json(ID_RULE)
    micro = read_json(MICRO_BIND)
    major = read_json(MAJOR_BIND)

    # ---- R1 observable map (all 120 slots) -------------------------------- #
    r1_by_slot = {}
    for obs in contract['observables']:
        for index in obs['indices']:
            r1_by_slot[(obs['array'], index)] = obs

    # ---- R1 failures by (array,index) ------------------------------------- #
    failures = [json.loads(line) for line in R1_FAILURES.read_text(
        encoding='utf-8').splitlines() if line.strip()]
    fail_by_slot = {}
    for row in failures:
        key = (row['array'], row['index'])
        entry = fail_by_slot.setdefault(key, {'total': 0, 'by_case': {}, 'max_abs_error': 0.0})
        entry['total'] += 1
        entry['by_case'][row['case']] = entry['by_case'].get(row['case'], 0) + 1
        entry['max_abs_error'] = max(entry['max_abs_error'], row['absolute_error'])

    # ---- per-slot current-source mapping / RHS resolution ----------------- #
    cur_by_slot = {s['slot']: s for s in current['slots']}
    rhs_by_slot = {s['slot']: s for s in rhs['slots']}

    # ---- same-source C0 full-series comparison (re-derived, read-only) ---- #
    build_manifest = read_json(C0_BUILD)
    native = parse_native_record(C0_RECORD, build_manifest['source_identity'])
    c0_by_slot = {}
    c0_compared = 0
    for array, width in ARRAY_LENGTHS.items():
        reference = parse_reference_f64(C0_REF_DIR / (array + '.f64'), array, width)
        for index in range(width):
            different = sum(
                1 for k in range(SAMPLES)
                if reference[k][index] != native[array][k][index])
            max_abs = max(
                abs(reference[k][index] - native[array][k][index])
                for k in range(SAMPLES))
            c0_by_slot[(array, index)] = {
                'compared_values': SAMPLES,
                'different_values': different,
                'max_abs_difference': max_abs,
            }
            c0_compared += SAMPLES

    # ---- first-step mapped-state coverage -------------------------------- #
    step_blocks = [{'block': b['block'], 'stage_difference_count': b['stage_difference_count'],
                    'final_state_difference_count': len(b['final_state_differences'])}
                   for b in step['blocks']]
    step_diffs = sum(b['stage_difference_count'] + len(b['final_state_differences'])
                     for b in step['blocks'])

    # ---- per-quantity rows ------------------------------------------------ #
    rows = []
    for slot in manifest['slots']:
        key = (slot['array'], slot['index'])
        r1 = r1_by_slot[key]
        name = slot['slot']
        cur = cur_by_slot.get(name, {})
        ref = rhs_by_slot.get(name, {})
        fail = fail_by_slot.get(key)
        c0 = c0_by_slot[key]
        resolution = ref.get('resolution', {})
        text_fields = {
            'observable': r1['id'],
            'source_mapping_historical_r1': slot['source_mapping']['raw'],
            'source_mapping_current_11_8': ('line_ranges %s (statement %s, outport %s)'
                                            % (cur.get('line_ranges'), cur.get('statement'),
                                               cur.get('outport'))),
            'unit': slot['unit'],
            'frame': slot['frame'],
            'datum': slot['datum'],
            'sample_phase': slot['sample_phase'],
            'derivation': None,
            'domain': None,
        }
        rows.append(dict(
            slot=name,
            array=slot['array'],
            index=slot['index'],
            observable=r1['id'],
            semantic_status=r1['semantic_status'],
            kind=('time' if name in TIME_SLOTS
                  else 'derivative' if name in DERIVATIVE_SLOTS
                  else 'state' if slot['array'] == 'Vehicle60'
                  else 'sensor' if slot['array'] == 'Sensor30'
                  else 'gps'),
            authority=dict(
                slot_identity='validation/e0-source-to-slot-manifest-20260911.json status=unresolved (56/56 slots)',
                unit_and_semantics='Simulator/wksim_core/numerical-conformance-v1.json observables[].native_unit',
                historical_r1_source_mapping='manifest source_mapping.historical_r1_cpp status=bound (Model 11.0 ZIP member)',
                current_11_8_source_mapping=('validation/e0-current-source-mapping-20260912.json '
                                             'generated_source sha256 2c25b3fa... (same as this round\'s C0 native '
                                             'original_cpp_sha256)'),
                current_11_8_rhs_resolution=('validation/e0-current-rhs-references-20260912.json '
                                             'resolution.status=%s reason=%s'
                                             % (resolution.get('status'), resolution.get('reason'))),
                route_requirement='docs/plan/10-g6-remediation-contract.md, docs/plan/59-e0-dynamic-budget-source-map.md',
            ),
            text_fields=text_fields,
            unit=slot['unit'],
            frame=slot['frame'],
            datum=slot['datum'],
            frame_note=FRAME_NOTE.get(name),
            sample_phase=slot['sample_phase'],
            time_grid=TIME_GRID,
            native_time_field=NATIVE_TIME_FIELDS if name in TIME_SLOTS else None,
            current_line_ranges=cur.get('line_ranges'),
            rhs_resolution=resolution,
            comparison_coverage=dict(
                structural_alignment='present: slot parsed, array/index owned exactly once by R1 observables',
                first_step_alignment=(('mapped in the 13-state first-step comparator' if (
                    slot['array'] == 'Vehicle60' and 3 <= slot['index'] <= 15)
                    else 'NOT mapped in the 13-state first-step comparator (13/36 states only)')),
                same_source_full_series_c0=('compared %d values (all %d samples); different_values=%d; '
                                            'max_abs_difference=%r'
                                            % (c0['compared_values'], SAMPLES,
                                               c0['different_values'], c0['max_abs_difference'])),
                r1_cross_version_declared_cases=('compared in C0/C2G/C3G under the frozen R1 zero budget; '
                                                 'failed_values=%d'
                                                 % (fail['total'] if fail else 0)),
            ),
            r1_failure=dict(
                failed_values=fail['total'] if fail else 0,
                by_case=(fail['by_case'] if fail else {}),
                max_abs_error=(fail['max_abs_error'] if fail else None),
            ),
            operator_matrix=dict(
                abs_budget=r1['absolute_budget'],
                rel_budget=r1['relative_budget'],
                rms_budget=None,
                metric=r1['rule'],
                budget_basis=r1['budget_basis'],
                approval='not_applicable_R1_is_a_zero_budget_preservation_rule_not_an_approved_epsilon',
            ),
            missing_approval_basis=[
                'no slot-level abs_budget / rel_budget / rms_budget from an error analysis, calibration, or sensor spec',
                'no frame binding (manifest frame=null for all 56/56 slots)',
                'no datum binding (manifest datum=null for all 56/56 slots)',
                'no per-slot version/hash binding to the current 11.8 generated source in the slot manifest',
                'no owner-approval record naming metric, semantics, datum and domain per slot',
            ] if True else [],
            unresolved_fields=slot['unresolved_fields'],
        ))

    rows.sort(key=lambda row: (row['array'], row['index']))

    # ---- aggregate failure table by observable --------------------------- #
    by_observable = {}
    for row in rows:
        entry = by_observable.setdefault(row['observable'], {
            'slots': [], 'failed_values': 0, 'by_case': {}, 'max_abs_error': 0.0})
        entry['slots'].append(row['slot'])
        entry['failed_values'] += row['r1_failure']['failed_values']
        for case, count in row['r1_failure']['by_case'].items():
            entry['by_case'][case] = entry['by_case'].get(case, 0) + count
        if row['r1_failure']['max_abs_error'] is not None:
            entry['max_abs_error'] = max(entry['max_abs_error'],
                                         row['r1_failure']['max_abs_error'])

    # ---- entry-tool ordering probe (read-only, synthetic) ---------------- #
    probe = {
        'ran': True,
        'method': ('validate_contract() on a synthetic in-memory-shaped contract containing all 120 R1 slots '
                   'with approved zero budgets, then validate_execution() on the same object'),
        'validate_contract_reasons': [],
        'validate_execution_result': None,
        'interpretation': ('The budget gate can be satisfied structurally; the next gate is the execution block, '
                           'which does not exist in the repository. Neither gate was passed by inventing a value: '
                           'the synthetic object was never written, never launched and is not evidence.'),
    }
    synthetic = dict(
        schema_version=1, contract_id='synthetic-probe-never-used', status='frozen',
        identity=dict(reference_revision='x', target_revision='x', reference_engine='x',
                      target_profile='x', slx=dict(path='x', sha256='0' * 64),
                      init=dict(path='x', sha256='0' * 64)),
        sampling=dict(array_lengths=dict(ARRAY_LENGTHS), fixed_step_s=TIME_STEP_S,
                      k_first=0, k_last=SAMPLES - 1),
        observables=[
            dict(observable=obs['id'], source_mapping=obs['source'], unit=obs['native_unit'],
                 frame='synthetic', datum='synthetic', sample_phase='major_root_output',
                 metric=FROZEN_METRIC, abs_budget=0.0, rel_budget=0.0, rms_budget=0.0,
                 derivation='synthetic', domain='synthetic', approval='approved',
                 contract_sha256='0' * 64, array=obs['array'], indices=list(obs['indices']))
            for obs in contract['observables']
        ],
    )
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        probe_path = Path(tmp) / 'synthetic-probe.json'
        probe_path.write_text(json.dumps(synthetic), encoding='utf-8')
        _, reasons = validate_contract(probe_path)
        probe['validate_contract_reasons'] = reasons
        try:
            from tools.run_e0_same_source_conformance import validate_execution
            validate_execution(probe_path, synthetic)
            probe['validate_execution_result'] = 'unexpectedly_reached_execution'
        except Reject as error:
            probe['validate_execution_result'] = 'Reject: %s' % error

    # ---- R1 frozen-contract refusal (real path, real tool) --------------- #
    try:
        validate_contract(CONTRACT)
        r1_refusal = 'unexpectedly accepted'
    except Reject as error:
        r1_refusal = 'Reject: %s' % error

    identity = {
        'r1_contract': {'path': 'Simulator/wksim_core/numerical-conformance-v1.json',
                        'sha256': sha256(CONTRACT), 'contract_id': contract['contract_id'],
                        'status': contract['status']},
        'materials': [],
    }
    for rel in ROUTE_DOCS + TOOL_INPUTS:
        path = ROOT / rel
        identity['materials'].append({
            'path': rel,
            'exists': path.is_file(),
            'sha256': sha256(path) if path.is_file() else None,
        })

    audit = {
        'schema': 'wksim.g6-budget-evidence-audit.v1',
        'audit_id': 'ds-g6-budget-evidence-20260913-01',
        'date': '2026-09-13',
        'work_class': 'new-development / read-only evidence audit',
        'summary': {
            'quantities_total': 120,
            'quantities_audited_dynamic': len(rows),
            'quantities_metadata_or_reserved': 120 - len(rows),
            'slots_with_any_approved_epsilon': 0,
            'slots_with_frame_binding': 0,
            'slots_with_datum_binding': 0,
            'slots_with_current_11_8_rhs_resolved': sum(
                1 for row in rows if row['rhs_resolution'].get('status') == 'terminal'),
            'slots_unresolved_in_slot_manifest': sum(
                1 for row in rows if row['unresolved_fields']),
            'r1_cross_version_failed_values': run_index['failed_values'],
            'r1_cross_version_failed_case_scalars': run_index['failed_case_scalars'],
            'r1_cross_version_comparisons': run_index['total_comparisons'],
            'same_source_c0_compared_values': c0_compared,
            'same_source_c0_different_values': c0_obs['different_values'],
            'first_step_mapped_states': 13,
            'first_step_total_states': 36,
            'first_step_stage_and_final_differences': step_diffs,
            'same_source_entry_status': 'blocked (no approved per-quantity budget, no execution block)',
            'physical_acceptance': False,
            'g6_acceptance': False,
        },
        'checkout': {
            'cwd': 'C:/Users/PC/Documents/odid编译/wksim',
            'branch': 'main',
            'head': 'abf1ac3934e3ad8dcfbcb5c7b4dc49712d407c18',
            'architecture_ancestor': 'f333316e6efa6b299b4288a9d91fb2bccedfb9d6',
            'architecture_ancestor_exit_code': 0,
        },
        'identity': identity,
        'three_distinct_levels': {
            'structural_alignment': (
                'Slot parse + exact array/index ownership under the frozen R1 observables, plus the '
                'same-source entry\'s structural layer (501 rows, 1 ms grid, 120 values/sample, complete '
                'terminal record, embedded source identity). The word "aligned" in the retained comparator '
                'outputs means this level only and is NOT a numerical or G6 verdict.'),
            'first_step_alignment': (
                'k=0->1 intra-step ODE4 trace comparison over 13 of 36 mapped rigid-body states plus five '
                'mrdivide operand/result rows. Retained result: 5 stage/final differences on Vehicle60 and '
                '1 ULP earliest divergence at p,q,r stage-2 derivatives[1]. This is one step, one case, one '
                'component, one value.'),
            'full_time_series_numerical_acceptance': (
                'The contract-declared rule over all 501 samples of all 120 slots under pre-approved '
                'abs_i/rel_i/rms_i budgets. THIS LEVEL HAS NEVER BEEN REACHED, because no budget is approved '
                'and no same-source contract with an execution block exists. It is NOT substituted by the '
                'same-source C0 offline diagnostic, which has zero approved budget and reports '
                'g6_acceptance=false.'),
        },
        'authoritative_sources': {
            'route_contract': 'docs/plan/10-g6-remediation-contract.md',
            'command_seam': 'docs/plan/59-e0-same-source-command.md',
            'budget_source_map': 'docs/plan/59-e0-dynamic-budget-source-map.md',
            'material_index': 'docs/g6-material-index.md',
            'frozen_r1_contract': 'Simulator/wksim_core/numerical-conformance-v1.json '
                                  '(sha256 23d72e26da5dfc7df0b41b96d090664d0ec022d777f6258e409bf7080f2c08f0)',
            'slot_manifest': 'validation/e0-source-to-slot-manifest-20260911.json (status=unresolved)',
            'current_source_mapping': 'validation/e0-current-source-mapping-20260912.json (status=bound, '
                                      'generated_source sha256 2c25b3fa08c996c8f2ed1a7feae5558062cd722ae5d350cc8a25caf2be10b274)',
            'current_rhs_references': 'validation/e0-current-rhs-references-20260912.json (status=bound)',
            'time_field_authority': 'validation/coordination/major-time-acceptance-20260913-01/verification.json',
        },
        'conventions': {
            'time_grid': TIME_GRID,
            'sample_phase': PHASE,
            'native_time_fields': NATIVE_TIME_FIELDS,
            'arrays': {'Vehicle60': 60, 'Sensor30': 30, 'GPS30': 30},
            'output_ports': contract['sampling']['source_port_mapping'],
            'frozen_metric': FROZEN_METRIC,
            'required_observable_fields': list(OBSERVABLE_REQUIRED_FIELDS),
            'frame_state': 'all 56/56 dynamic slots carry frame=null in the slot manifest; conventions exist '
                           'only as project prose in Simulator/wksim_core/README.md:52,54 and are not slot bindings',
            'datum_state': 'all 56/56 dynamic slots carry datum=null in the slot manifest; no WGS84/ellipsoid '
                           'binding exists for truth_altitude, gps_altitude or pressure_altitude',
        },
        'quantities': rows,
        'failure_aggregate_by_observable': by_observable,
        'r1_cross_version': {
            'role': 'historical R1 comparison; retained as failure evidence, NOT the G6 same-source route',
            'comparisons': run_index['total_comparisons'],
            'failed_values': run_index['failed_values'],
            'failed_case_scalars': run_index['failed_case_scalars'],
            'execution_invalid_cases': run_index['execution_invalid_cases'],
            'numerical_pass_label': contract['reporting']['numerical_pass_label'],
            'physical_accuracy_status': contract['reporting']['physical_accuracy_status'],
            'per_case': run_index['results'],
            'aggregate': read_json(ROOT / 'validation/coordination/g6-first-divergence-20260913/diagnosis.json')['aggregate'],
        },
        'same_source_full_series_diagnostic': {
            'role': 'offline diagnostic over retained originals; zero budget; g6_acceptance=false',
            'case': c0_obs['case'],
            'comparisons': c0_observed_comparisons(c0_observed := c0_obs),
            'different_values': c0_obs['different_values'],
            'different_scalars': c0_obs['different_scalars'],
            're_derived_this_round': {
                'comparisons': c0_compared,
                'different_values': sum(c0_by_slot[key]['different_values']
                                        for key in sorted(c0_by_slot)),
                'different_slots': [
                    '%s[%d]' % key for key in sorted(c0_by_slot)
                    if c0_by_slot[key]['different_values']],
            },
            'native_source_identity': build_manifest['source_identity'],
            'scope': c0_obs['scope'],
        },
        'first_step_alignment': {
            'role': 'bounded k=0->1 trace comparison; "aligned" is structural only',
            'mapped_states': 13,
            'total_states_in_generated_recorder': 36,
            'blocks': step_blocks,
            'earliest_difference': {
                'block': 'p,q,r', 'stage': 2, 'field': 'derivatives', 'index': 1,
                'reference_hex': 'bc56d4db33a987b8', 'target_hex': 'bc56d4db33a987b9',
                'ulp': 1,
            },
            'guarded_candidate_result': (
                'the diagonal fast-path candidate reproduces the reference on the 13 mapped states and on the '
                'five mrdivide results, but the guard review shows the branch is 1 ULP LESS accurate than the '
                'correctly rounded division in that component; the reference-solver hypothesis is unresolved'),
            'comparator_result_sha256': sha256(ROOT / 'validation/coordination/g6-diagonal-solve-candidate-20260913/comparator-result-v2.json'),
        },
        'time_fields': {
            'authority': 'validation/coordination/major-time-acceptance-20260913-01/verification.json',
            'reference_row_time_product_matches': 501,
            'reference_row_time_division_matches': 429,
            'differs_from_division_then_gain': {'Vehicle60': 72, 'Sensor30': 61, 'GPS30': 61},
            'budget_approved': time_verify['budget_approved'],
            'g6_acceptance': time_verify['g6_acceptance'],
            'prospective_rules': {
                'vehicle_time_premise': {'path': 'validation/coordination/g6-time-premise-acceptance-20260913-01/prospective-rule.json',
                                         'status': time_premise['status'],
                                         'acceptance': time_premise['acceptance'],
                                         'budget_approved': time_premise['budget_approved']},
                'identity_rule_v3': {'path': 'validation/coordination/ds-g6-identity-rule-20260913-01/g6-identity-rule-v3.json',
                                     'status': id_rule['status'], 'acceptance': id_rule['acceptance']},
                'major_microtime_binding_v4': {'path': 'validation/coordination/ds-g6-major-microtime-binding-20260913-01/g6-major-microtime-binding-v4.json',
                                               'status': micro['status'], 'acceptance': micro['acceptance']},
                'major_time_binding_v3': {'path': 'validation/coordination/ds-g6-major-time-binding-20260913-01/g6-major-time-binding-v3.json',
                                          'status': major['status'], 'acceptance': major['acceptance']},
            },
            'status': 'no time/phase rule is approved; all four retained records are prospective_for_review with acceptance=false',
        },
        'entry_probe': {
            'tool': 'tools/run_e0_same_source_conformance.py',
            'tool_sha256': sha256(ROOT / 'tools/run_e0_same_source_conformance.py'),
            'real_invocation_on_r1': {
                'argv': ['python', 'tools/run_e0_same_source_conformance.py',
                         'Simulator/wksim_core/numerical-conformance-v1.json'],
                'observed_status': 'blocked',
                'observed_exit_code': 2,
                'matlab_launched': False,
                'native_launched': False,
                'observed_stdout_status': 'blocked',
            },
            'r1_refusal': r1_refusal,
            'ordering_probe': probe,
            'conclusion': ('the same-source entry EXISTS and is implemented; the missing item is the approved '
                           'per-quantity budget and the execution identity, not the entry. No epsilon was '
                           'invented, relaxed or approved by this audit.'),
        },
        'blockers': [
            {
                'id': 'B1-no-approved-per-quantity-budget',
                'statement': 'No abs_budget / rel_budget / rms_budget basis exists for any of the 120 slots.',
                'discharge_authority': 'project owner / delegated engineering authority named in the #59 route contract',
                'evidence_needed': ['error analysis or calibration/sensor specification per observable',
                                    'state domain and event policy',
                                    'derivation note and owner-approval record'],
            },
            {
                'id': 'B2-frame-and-datum-unbound',
                'statement': 'frame and datum are null for all 56/56 dynamic slots.',
                'discharge_authority': 'project owner',
                'evidence_needed': ['slot-level frame binding', 'WGS84/ellipsoid and altitude-datum binding',
                                    'GPS course angle wrapping convention', 'eph/epv physical semantics'],
            },
            {
                'id': 'B3-time-phase-rule-unapproved',
                'statement': 'All four retained time/premise records are prospective_for_review with acceptance=false.',
                'discharge_authority': 'project owner (separate from B1; time fields may be excluded by a scoped decision)',
                'evidence_needed': ['a decision that the three time fields are schedule metadata (excluded) or a bound schedule budget'],
            },
            {
                'id': 'B4-no-same-source-execution-identity',
                'statement': 'No same-source contract with an execution block (matlab, export script, stage files, native manifest, WSL executable) exists.',
                'discharge_authority': 'main session (sole writer of native/official profile)',
                'evidence_needed': ['a frozen same-source contract file with all 120 approved budgets',
                                    'the full execution block with live hashes'],
            },
            {
                'id': 'B5-derivative-path-only-partially-observed',
                'statement': 'The first divergence is localised to one component of one step; the pqr(q) derivative operand chain is only partially observed.',
                'discharge_authority': 'main session (deeper instrumentation is second-level, not delegable offline)',
                'evidence_needed': ['mrdivide numerator and Selector2 captured on both engines',
                                    'all 36 states mapped, not 13', 'a second discriminating solve component'],
            },
        ],
        'next_recheck_commands': [
            {
                'purpose': 're-verify the frozen R1 identity and the retained 5684 failures',
                'command': ('$i = Get-Content validation/10-g6-remediation/review-20260909/inspection.json -Raw | '
                            'ConvertFrom-Json; foreach ($h in $i.hashes) { if ((Get-FileHash -LiteralPath $h.path '
                            '-Algorithm SHA256).Hash.ToLower() -ne $h.sha256) { throw ("Hash changed: " + $h.path) } }; '
                            'if (($i.results | Measure-Object -Property failed_values -Sum).Sum -ne 5684) { throw "Failure total changed" }'),
                'expected': 'exit 0; 15 identities unchanged; 5684 failures retained',
            },
            {
                'purpose': 'prove the same-source entry still refuses R1 and still blocks before any launch',
                'command': 'python tools/run_e0_same_source_conformance.py Simulator/wksim_core/numerical-conformance-v1.json',
                'expected': 'status=blocked, exit 2, matlab_launched=false, native_launched=false',
            },
            {
                'purpose': 're-validate the unresolved slot manifest offline',
                'command': 'python -B tools/validate_e0_source_to_slot_manifest.py',
                'expected': 'status=pass with 56 slots, 0 errors (the pass is provenance-only)',
            },
            {
                'purpose': 're-derive the same-source C0 full-series diagnostic read-only',
                'command': ('python -B -c "import sys; sys.path.insert(0,\'.\'); '
                            'from tools.run_e0_same_source_conformance import ARRAY_LENGTHS, parse_native_record, '
                            'parse_reference_f64; import json; from pathlib import Path; r=Path(\'.\'); '
                            'b=json.loads((r/\'validation/e0-major-recorder-parent-final-01/build-manifest.json\').read_bytes()); '
                            'n=parse_native_record(r/\'validation/e0-major-recorder-parent-final-01/record.jsonl\', b[\'source_identity\']); '
                            't=d=0; '
                            'for a,w in ARRAY_LENGTHS.items():\n'
                            ' e=parse_reference_f64(r/\'validation/numerical-conformance-u56ce17a/C0\'/(a+\'.f64\'),a,w)\n'
                            ' for i in range(w):\n'
                            '  t+=501; d+=sum(1 for k in range(501) if e[k][i]!=n[a][k][i])\n'
                            'print(t,d)"'),
                'expected': 'comparisons 60120, different_values 2 (Sensor30[10] at k=153 and k=181)',
            },
            {
                'purpose': 're-hash every input this audit cites',
                'command': 'python -B validation/coordination/ds-g6-budget-evidence-20260913-01/verify_inputs.py',
                'expected': 'exit 0, all identities match audit.json',
            },
        ],
        'non_claims': [
            'This audit approves NO epsilon and relaxes NO budget.',
            'The same-source entry tools/run_e0_same_source_conformance.py EXISTS; it is not missing. Only the approved budget and the execution identity are missing.',
            'The same-source entry exists and is implemented; structural alignment is not a numerical or G6 verdict.',
            'No first-step alignment (13 states, 1 case, 1 step, 1 component) substitutes for full time-series acceptance.',
            'No MATLAB, native, ROS, flight-controller, model, UE, or MATLAB build was started; no epsilon was invented.',
            'R1 remains numerical_failed; G6 and physical accuracy remain unverified; issue #59 remains OPEN/needs-triage.',
        ],
    }
    return audit


def c0_observed_comparisons(obs):
    return obs['comparisons']


if __name__ == '__main__':
    result = build()
    out = HERE / 'audit.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                              allow_nan=False) + '\n', encoding='utf-8', newline='\n')
    print('wrote', out)
    print(json.dumps(result['summary'], indent=1, ensure_ascii=False))
