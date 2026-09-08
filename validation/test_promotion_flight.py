"""Promotion contract checks; mocked reports are not build or flight evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Simulator.wksim_runtime.config import ConfigError, validate_config
from Simulator.wksim_runtime import independent_profile as profile, joint_profile, preflight
from validation.test_independent_profile import config
from tools import rebuild_promotion_evidence as rebuild


class PromotionFlightTests(unittest.TestCase):
    def test_flag_is_explicit_boolean_and_session_only(self):
        for value in ('true', 1, 0, None, [], {}):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                validate_config(dict(config(), promotion_flight=value))
        for value in (True, False):
            self.assertIs(validate_config(dict(config(), promotion_flight=value))['promotion_flight'], value)
        data = config()
        data.pop('runtime_profile')
        with self.assertRaisesRegex(ConfigError, 'explicit session_v1'):
            validate_config(dict(data, control_protocol='legacy_v1', promotion_flight=True))

    def test_independent_only_skips_history_and_never_claims_flown(self):
        for stack in ('px4', 'arducopter'):
            key = 'ap' if stack == 'arducopter' else 'px4'
            report = dict(ok=True, reasons=[], children_created=0, model_library='/model',
                          identities={key: dict(path='/firmware', sha256='fw', commit='commit'),
                                      stack + '_agent': dict(path='/agent', sha256='agent'),
                                      'model': dict(library_sha256='model')})
            for flag in (None, False, True):
                data = config(stack)
                if flag is not None:
                    data['promotion_flight'] = flag
                with self.subTest(stack=stack, flag=flag), \
                        patch.object(joint_profile, 'check_resources', return_value=copy.deepcopy(report)) as resources, \
                        patch.object(profile, 'check_flight_evidence', side_effect=ValueError('old flight')) as history:
                    result = profile.check_profile(data)
                resources.assert_called_once()
                self.assertEqual(resources.call_args.kwargs, dict(stacks=(stack,)))
                self.assertEqual(result['ok'], flag is True)
                self.assertFalse(result['candidate_status']['flown'])
                if flag is True:
                    history.assert_not_called()
                    self.assertEqual(result['flight_provenance'], 'promotion_flight')
                    self.assertTrue(result['candidate_status']['built'])
                    self.assertFalse(result['capabilities'][0]['flown'])
                    self.assertEqual(result['identities']['firmware']['sha256'], 'fw')
                else:
                    history.assert_called_once()

    def test_promotion_resource_failure_remains_rejection(self):
        for reason in ('firmware', 'control build', 'model', 'message content', 'overlay'):
            with self.subTest(reason=reason), patch.object(joint_profile, 'check_resources', return_value=dict(
                    ok=False, reasons=[dict(code='joint_profile_rejected', message=reason)], identities={})), \
                    patch.object(profile, 'check_flight_evidence') as history:
                result = profile.check_profile(dict(config(), promotion_flight=True))
                self.assertFalse(result['ok'])
                self.assertFalse(result['candidate_status']['built'])
                self.assertFalse(result['candidate_status']['flown'])
                self.assertEqual(result['reasons'][0]['message'], reason)
                history.assert_not_called()

    def test_session_requires_pinned_build_and_complete_snapshot(self):
        data = dict(config(), prometheus_workspace='/reviewed', promotion_flight=True)
        pin = dict(prefix='/reviewed/install/prometheus_control', complete_snapshot=True, sha256='snapshot')
        index = dict(control_profiles=dict(session_v1=dict(installed_packages=dict(prometheus_control=pin))))
        evidence = dict(prometheus=dict(implementation_sha256={'old.py': 'old'}))
        record = dict(python_sha256={'current.py': 'current'})
        self.assertEqual(preflight.control_sources(dict(data, promotion_flight=False), index, evidence), {'old.py': 'old'})
        with patch.object(joint_profile, '_pinned_json', return_value=record), \
                patch.object(joint_profile, '_control') as build, \
                patch.object(preflight, 'package_digest', return_value='snapshot') as snapshot:
            self.assertEqual(preflight.control_sources(data, index, evidence), record['python_sha256'])
            build.assert_called_once_with(record)
            self.assertEqual(snapshot.call_args.kwargs, dict(complete=True))
            for mutation in (dict(sha256='wrong'), dict(complete_snapshot=False), dict(prefix='/wrong')):
                changed = copy.deepcopy(index)
                changed['control_profiles']['session_v1']['installed_packages']['prometheus_control'].update(mutation)
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    preflight.control_sources(data, changed, evidence)
            build.side_effect = ValueError('build differs')
            with self.assertRaisesRegex(ValueError, 'build differs'):
                preflight.control_sources(data, index, evidence)

    def test_session_catalog_is_candidate_only_and_requires_current_control(self):
        before = preflight.INDEX.read_bytes()
        index = json.loads(before)
        paths = [preflight.REPO / p['result'] for p in index['control_profiles']['session_v1']['evidence'].values()]
        sources = json.loads(paths[0].read_text())['prometheus']['implementation_sha256']
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(preflight, 'control_sources', return_value={'not-flown.py': 'new'}):
                with self.assertRaisesRegex(ValueError, 'current pinned control'):
                    rebuild.session(paths, Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])
            with patch.object(preflight, 'control_sources', return_value=sources):
                rebuild.session(paths, Path(directory))
            candidate = json.loads((Path(directory) / 'capability-index.candidate.json').read_text())
            self.assertEqual(candidate, index)
            with patch.object(preflight, 'control_sources', return_value=sources), self.assertRaises(FileExistsError):
                rebuild.session(paths, Path(directory))
        self.assertEqual(preflight.INDEX.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
