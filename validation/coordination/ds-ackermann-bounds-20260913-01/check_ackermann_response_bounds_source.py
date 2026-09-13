"""Static AST inspection of the Ackermann speed-response bound fix.

This checker never imports or executes the model, its tests, a firmware, ROS,
MATLAB or a build. It parses two files with ``ast`` and asserts the required
structure, then writes evidence/static-check.json. Run from the repository root:

    python validation/coordination/ds-ackermann-bounds-20260913-01/check_ackermann_response_bounds_source.py
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
RECEIPT=Path(__file__).resolve().parent
MODEL=ROOT/'Simulator/wksim_core/ackermann.py'
TEST=ROOT/'validation/test_ackermann_response_bounds.py'

CROSSING='self.speed < target_speed < following_speed or following_speed < target_speed < self.speed'
DT_CONTRACT=('-1 <= throttle <= 1','-1 <= steering <= 1','not 0 < dt_s <= 0.02')
ACCELERATION_CLAMP=('acceleration = max(-p.max_acceleration_m_s2, min(p.max_acceleration_m_s2, '
                    '(target_speed - self.speed) / p.speed_response_s))')
STATIC_TEST='test_small_response_constants_stay_legal_parameters'
EXPECTED_TESTS=(
    'test_small_response_constant_cannot_exceed_the_declared_max_speed',
    'test_small_response_constant_holds_the_reverse_speed_bound',
    'test_zero_throttle_brakes_to_rest_without_crossing_it',
    'test_crossing_step_reports_the_bounded_increment',
    'test_reported_specific_force_is_the_realised_speed_increment',
    'test_bound_holds_across_every_allowed_step_length',
    'test_default_parameters_keep_the_verified_response_path',
    STATIC_TEST,
    'test_signed_command_and_step_contract_is_unchanged',
)


def norm(text):
    return ' '.join(text.split())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def statements(node):
    return [norm(ast.unparse(statement)) for statement in node.body]


def method_source(tree,source):
    return {node.name:ast.get_source_segment(source,node) or ''
            for node in ast.walk(tree)
            if isinstance(node,ast.FunctionDef) and node.name.startswith('test_')}


def main():
    checks={}
    model_source=MODEL.read_text(encoding='utf-8')
    test_source=TEST.read_text(encoding='utf-8')
    model_tree=ast.parse(model_source)
    test_tree=ast.parse(test_source)

    step=next(node for node in ast.walk(model_tree)
              if isinstance(node,ast.FunctionDef) and node.name=='step')
    body=statements(step)
    body_text=' | '.join(body)
    checks['step_requires_target_speed']='target_speed = throttle * p.max_speed_m_s' in body
    checks['step_keeps_acceleration_clamp']=ACCELERATION_CLAMP in body_text
    checks['step_keeps_explicit_euler_speed']='following_speed = self.speed + acceleration * dt_s' in body

    crossing=[node for node in step.body
              if isinstance(node,ast.If) and norm(ast.unparse(node.test))==CROSSING]
    checks['step_bounds_the_crossing_step']=len(crossing)==1
    clamp_body=statements(crossing[0]) if crossing else []
    checks['crossing_holds_the_target']=clamp_body==['following_speed = target_speed',
                                                    'acceleration = (following_speed - self.speed) / dt_s']
    checks['step_assigns_following_speed']='self.speed = following_speed' in body

    returns=[node for node in ast.walk(step) if isinstance(node,ast.Return)]
    arguments=returns[0].value.args if returns else []
    force=arguments[5] if len(arguments)>5 else None
    checks['return_shape_unchanged']=isinstance(returns[0].value,ast.Call) and len(arguments)==6
    checks['specific_force_is_reported_acceleration']=(
        isinstance(force,ast.Tuple) and len(force.elts)==3
        and isinstance(force.elts[0],ast.Name) and force.elts[0].id=='acceleration')
    checks['specific_force_keeps_gravity_term']=(
        isinstance(force,ast.Tuple) and len(force.elts)==3
        and isinstance(force.elts[2],ast.UnaryOp)
        and isinstance(force.elts[2].operand,ast.Constant)
        and force.elts[2].operand.value==9.80665)

    parameters=next(node for node in ast.walk(model_tree)
                    if isinstance(node,ast.ClassDef) and node.name=='AckermannParameters')
    post_init=next(node for node in parameters.body
                   if isinstance(node,ast.FunctionDef) and node.name=='__post_init__')
    checks['parameter_rejection_unchanged']=len([node for node in ast.walk(post_init)
                                                 if isinstance(node,ast.Raise)])==2
    checks['no_new_response_floor']=not any(isinstance(node,ast.Attribute) and node.attr=='speed_response_s'
                                            for node in ast.walk(post_init))
    checks['dt_contract_unchanged']=all(fragment in body_text for fragment in DT_CONTRACT)
    checks['original_imports_kept']=(sorted(alias.name for node in model_tree.body
                                            if isinstance(node,ast.Import) for alias in node.names)==['math']
                                     and sorted(node.module for node in model_tree.body
                                                if isinstance(node,ast.ImportFrom))==['dataclasses','vehicle_state'])
    steering_update=('self.steering += (steering * p.max_steering_rad - self.steering) * '
                     '(1 - math.exp(-dt_s / p.steering_response_s))')
    checks['steering_response_unchanged']=steering_update in body_text
    checks['step_has_only_input_and_crossing_branches']=len([node for node in step.body if isinstance(node,ast.If)])==2

    methods=method_source(test_tree,test_source)
    checks['all_prepared_tests_present']=sorted(methods)==sorted(EXPECTED_TESTS)
    behaviour=[name for name in methods if name!=STATIC_TEST]
    checks['every_behaviour_test_exercises_the_model']=all(
        'step(' in methods[name] or 'drive(' in methods[name] for name in behaviour)
    checks['parameter_contract_test_does_not_step']=('AckermannParameters(' in methods[STATIC_TEST]
                                                     and 'step(' not in methods[STATIC_TEST])
    checks['forward_case']=('speed_response_s=SMALL_RESPONSE_S' in test_source
                            and 'drive(model,1.,0.,.001,2000)' in test_source)
    checks['reverse_case']='drive(model,-1.,0.,.001,2000)' in test_source
    checks['brake_case']='model.step(throttle=0.,steering=0.,dt_s=.001)' in test_source
    checks['allowed_dt_sweep']=all(value in test_source for value in ('.0001','.001','.005','.01','.02'))
    checks['default_path_equivalence']=('math.exp(-dt_s/p.steering_response_s)' in test_source
                                        and 'test_default_parameters_keep_the_verified_response_path' in methods)
    checks['no_step_call_at_import_time']=not any(
        isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='step'
        for node in test_tree.body)
    checks['test_has_main_guard']=any(
        isinstance(node,ast.If) and norm(ast.unparse(node.test))=="__name__ == '__main__'"
        for node in test_tree.body)

    evidence=dict(
        checker='static AST only; the model, its tests, a firmware, ROS, MATLAB and any build were not run',
        model_file=dict(path='Simulator/wksim_core/ackermann.py',sha256=sha256(MODEL),
                        step_source_sha256=hashlib.sha256(ast.unparse(step).encode()).hexdigest()),
        test_file=dict(path='validation/test_ackermann_response_bounds.py',sha256=sha256(TEST),
                       test_methods=sorted(methods)),
        checks=checks,
        failed=sorted(name for name,ok in checks.items() if not ok),
        ran_model_code=False,
        ran_model_tests=False,
    )
    (RECEIPT/'evidence').mkdir(exist_ok=True)
    (RECEIPT/'evidence/static-check.json').write_text(
        json.dumps(evidence,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(dict(failed=evidence['failed'],checks=len(checks),
        model_sha256=evidence['model_file']['sha256'],test_sha256=evidence['test_file']['sha256'])))
    return 1 if evidence['failed'] else 0


if __name__=='__main__':
    raise SystemExit(main())
