"""#117 pure boundary tests; optional fixed C++ oracle executable argument."""
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'Simulator'))
from wksim_control.global_reference import (
    SCHEMA, Identity, HomeSnapshot, OriginSnapshot, GlobalCommand, Rejection,
    resolve, validate_current, project, reproject, f32, ap_distance)

ORACLE = None
if '--oracle' in sys.argv:
    index = sys.argv.index('--oracle')
    ORACLE = sys.argv[index+1]
    del sys.argv[index:index+2]


def fixture(stack='px4', lat=0., lon=0.):
    identity = Identity(stack, 'run', 'instance', 1, 2, 'boot', 'gid', 'scene')
    home = HomeSnapshot(SCHEMA, identity, 100, 10., 1, lat, lon, 123., 'datum-proof',
                        True, True, False, 1 if stack == 'px4' else None,
                        False if stack == 'px4' else None,
                        None if stack == 'px4' else (round(lat*1e7), round(lon*1e7), 12300))
    origin = OriginSnapshot(identity, 'ekf', 1, 90, lat, lon, 118., (0, 0), (0, 0, 0),
                            100, 10., True, 'datum-proof')
    command = GlobalCommand(SCHEMA, lat, lon, 3., 'home_relative', identity, 1, 'ekf', 1, 1, 10., 12.)
    return home, origin, command


def run(home, origin, command, **kwargs):
    return resolve(command, now=10., home=home, origin=origin, last_command_id=0, **kwargs)


class GlobalTests(unittest.TestCase):
    def reject(self, reason, function, *args, **kwargs):
        with self.assertRaises(Rejection) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.reason, reason)

    def test_explicit_heights_and_axes(self):
        for stack in ('px4', 'arducopter'):
            h, o, c = fixture(stack)
            a = run(h, o, c)
            b = run(h, o, replace(c, height_m=126, height_reference='amsl'))
            self.assertEqual(a.native_target, b.native_target)
            self.assertEqual((a.height_amsl_m, a.height_relative_m), (126, 3))
            self.assertEqual(a.native_target, (0, 0, -8) if stack == 'px4' else (0, 0, 300))
            self.assertEqual(a.native_kind, 'trajectory_setpoint_ned' if stack == 'px4' else 'FRAME_GLOBAL_REL_ALT')
            self.assertEqual(b.original.height_reference, 'amsl')

    def test_nonfinite_bool_and_missing(self):
        h, o, c = fixture()
        for value in (True, False, math.nan, math.inf, -math.inf, '1', None, 10**400):
            for field in ('latitude_deg', 'longitude_deg', 'height_m', 'issued_monotonic', 'expires_monotonic'):
                with self.subTest(value=str(value), field=field):
                    self.reject('invalid_number', run, h, o, replace(c, **{field: value}))
        with self.assertRaises(TypeError):
            GlobalCommand(schema=SCHEMA)

    def test_datums(self):
        for stack in ('px4', 'arducopter'):
            h, o, c = fixture(stack)
            for datum in ('ellipsoid', 'agl', 'terrain', 'WGS84', '', None):
                self.reject('height_reference_unsupported', run, h, o, replace(c, height_reference=datum))
            self.reject('datum_unverified', run, replace(h, datum_proof_id=''), o, c)
            self.reject('datum_unverified', run, h, replace(o, datum_proof_id=''), c)

    def test_coordinate_envelope(self):
        h, o, c = fixture()
        for field, value in (('latitude_deg', 85.000001), ('latitude_deg', -85.000001),
                             ('longitude_deg', 180.000001), ('longitude_deg', -180.000001)):
            self.reject('coordinate_range', run, h, o, replace(c, **{field: value}))
        for lat in (85., -85.):
            h, o, c = fixture(lat=lat)
            run(h, o, c)

    def test_hundred_metre_bounds(self):
        for stack in ('px4', 'arducopter'):
            h, o, c = fixture(stack)
            for north, east in ((99.8, 0), (0, 99.8), (60, 60)):
                lat, lon = reproject(0, 0, north, east)
                run(h, o, replace(c, latitude_deg=lat, longitude_deg=lon))
            for north, east in ((100.1, 0), (0, 100.1), (80, 80)):
                lat, lon = north/6371000*180/math.pi, east/6371000*180/math.pi
                self.reject('horizontal_range', run, h, o, replace(c, latitude_deg=lat, longitude_deg=lon))
            for height in (-100, 100):
                run(h, o, replace(c, height_m=height))
            for height in (-100.0001, 100.0001):
                self.reject('height_range', run, h, o, replace(c, height_m=height))

    def test_distinct_origin(self):
        h, o, c = fixture()
        o = replace(o, latitude_deg=.0001, longitude_deg=-.0002)
        t = run(h, o, c)
        self.assertGreater(t.check_enu_m[0], 22)
        self.assertLess(t.check_enu_m[1], -11)
        self.assertEqual(t.check_enu_m[2], 8)
        self.reject('horizontal_range', run, h, replace(o, latitude_deg=.01), c)

    def test_round_trips(self):
        for lat, lon in ((0, 0), (-35, -120), (35, 120), (84.99, 179.9999), (-84.99, -179.9999)):
            for n, e in ((0, 0), (3, 5), (-30, -40), (60, 60)):
                target = reproject(lat, lon, n, e)
                projected = project(lat, lon, *target)
                for a, b in zip(projected, (n, e)):
                    self.assertLessEqual(abs(a-b), 1e-6)
                for quantized in (False, True):
                    point = tuple(map(f32, projected)) if quantized else projected
                    inverse = reproject(lat, lon, *point)
                    self.assertLessEqual(abs(inverse[0]-target[0]), 2e-7 if quantized else 1e-9)
                    self.assertLessEqual(abs((inverse[1]-target[1]+180)%360-180), 2e-7 if quantized else 1e-9)

    def test_date_line_and_hemispheres(self):
        for stack in ('px4', 'arducopter'):
            for lat, lon, target_lon in ((0, 180, -179.9999), (0, -180, 179.9999), (-35, -120, -119.9999)):
                h, o, c = fixture(stack, lat, lon)
                t = run(h, o, replace(c, longitude_deg=target_lon))
                self.assertLess(math.hypot(*t.check_enu_m[:2]), 20)

    def test_time_bounds_and_replay(self):
        h, o, c = fixture()
        t = run(h, o, c)
        validate_current(t, now=12., home=h, origin=o)
        for now, reason in ((12.000001, 'snapshot_stale'), (9.9, 'clock_regressed')):
            self.reject(reason, validate_current, t, now=now, home=h, origin=o)
        self.reject('command_id_not_increasing', resolve, c, now=10, home=h, origin=o, last_command_id=1)
        for issued, expires in ((9, 12), (11, 12), (10, 10), (8, 9)):
            self.reject('command_expired', run, h, o, replace(c, issued_monotonic=issued, expires_monotonic=expires))

    def test_duplicate_does_not_refresh(self):
        h, o, c = fixture()
        t = run(h, o, c)
        validate_current(t, now=11, home=h, origin=o)
        self.reject('duplicate_source_changed', validate_current, t, now=11,
                    home=replace(h, received_monotonic=11), origin=o)
        self.reject('source_clock_regressed', validate_current, t, now=11,
                    home=replace(h, source_timestamp=99), origin=o)
        self.reject('source_clock_regressed', run, replace(h, source_timestamp=99), o, c, previous_home=h)

    def test_checkpoint_chain(self):
        h, o, c = fixture()
        t = run(h, o, c)
        h2, o2 = replace(h, source_timestamp=101, received_monotonic=11), replace(o, source_timestamp=101, received_monotonic=11)
        t2 = validate_current(t, now=11, home=h2, origin=o2)
        self.assertEqual(t2.home, h2)
        self.reject('source_clock_regressed', validate_current, t2, now=11.1, home=h, origin=o)
        self.reject('paused', run, h, o, c, paused=True)
        self.reject('paused', validate_current, t, now=11, home=h, origin=o, paused=True)

    def test_old_identity(self):
        h, o, c = fixture()
        for field, value in (('run_id', 'old'), ('instance_id', 'other'), ('vehicle_id', 2),
                             ('control_epoch', 1), ('native_session', 'old'), ('publisher_gid', 'other'), ('scene_origin_id', 'other')):
            self.reject('identity_mismatch', run, h, o, replace(c, identity=replace(c.identity, **{field: value})))
        self.reject('home_changed', run, h, o, replace(c, home_generation=2))
        self.reject('origin_changed', run, h, o, replace(c, local_origin_generation=2))

    def test_home_changes_even_without_generation(self):
        h, o, c = fixture()
        t = run(h, o, c)
        for field, value in (('home_generation', 2), ('latitude_deg', .000001), ('alt_amsl_m', 124),
                             ('update_count', 0), ('manual_home', True), ('valid_lpos', True), ('datum_proof_id', 'new')):
            changed = replace(h, source_timestamp=101, **{field: value})
            self.reject('home_changed', validate_current, t, now=10, home=changed, origin=o)

    def test_origin_resets(self):
        h, o, c = fixture()
        t = run(h, o, c)
        for field, value in (('origin_id', 'new'), ('local_origin_generation', 2), ('ref_timestamp', 91),
                             ('latitude_deg', .000001), ('alt_amsl_m', 119),
                             ('global_reset_counters', (1, 0)), ('local_reset_counters', (0, 1, 0))):
            self.reject('origin_changed', validate_current, t, now=10, home=h,
                        origin=replace(o, source_timestamp=101, **{field: value}))

    def test_invalid_native_and_navigation(self):
        h, o, c = fixture('arducopter')
        self.reject('home_native_mismatch', run, replace(h, ap_raw=(1, 0, 12300)), o, c)
        self.reject('navigation_invalid', run, replace(h, valid_alt=False), o, c)
        self.reject('navigation_invalid', run, h, replace(o, navigation_valid=False), c)
        self.reject('invalid_flag', run, replace(h, valid_hpos=1), o, c)
        self.reject('invalid_integer', run, h, o, replace(c, command_id=True))

    def test_fixed_cpp_oracle(self):
        if ORACLE is None:
            # This portable suite does not claim the separate native oracle gate.
            self.skipTest('Separate fixed C++ oracle requires --oracle executable')
        rows = []
        for lat, lon in ((0., 0.), (-35., -120.), (35., 120.), (85., 179.9999), (-85., -179.9999)):
            for dn, de in ((0, 0), (-3 if lat > 0 else 3, 5), (0, -50), (0, 99.8)):
                tlat, tlon = reproject(lat, lon, dn, de)
                for altitude in (3., -3.019, 99.99):
                    rows.append([lat, lon, tlat, tlon, 123., 118., altitude])
        raw = '\n'.join(' '.join(map(str, row)) for row in rows)+'\n'
        output = subprocess.run([ORACLE], input=raw, text=True, capture_output=True, check=True).stdout
        results = [list(map(float, line.split())) for line in output.splitlines()]
        print(json.dumps(dict(oracle_inputs=rows, oracle_outputs=results)))
        self.assertEqual(len(results), len(rows))
        max_px4 = max_ap = max_round = 0.
        for row, oracle in zip(rows, results):
            lat, lon, tlat, tlon, home_alt, origin_alt, altitude = row
            for stack in ('px4', 'arducopter'):
                h, o, c = fixture(stack, lat, lon)
                result = run(h, o, replace(c, latitude_deg=tlat, longitude_deg=tlon, height_m=altitude))
                if stack == 'px4':
                    max_px4 = max(max_px4, *(abs(a-b) for a, b in zip(result.native_target, oracle[:3])))
                else:
                    self.assertEqual(result.native_target, tuple(map(int, oracle[3:6])))
                    max_ap = max(max_ap, *(abs(a-b) for a, b in zip(result.check_enu_m, oracle[6:9])))
                    self.assertLessEqual(abs(result.native_target[0]/1e7-tlat), 2e-7)
                    self.assertLessEqual(abs(result.native_target[1]/1e7-tlon), 2e-7)
                    max_round = max(max_round, abs(result.native_target[2]/100-altitude))
        self.assertLessEqual(max_px4, .001)
        self.assertLessEqual(max_ap, .001)
        self.assertLessEqual(max_round, .02)
        print(json.dumps(dict(oracle_cases=len(rows), max_px4_error_m=max_px4,
                              max_ap_error_m=max_ap, max_ap_height_roundtrip_m=max_round)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
