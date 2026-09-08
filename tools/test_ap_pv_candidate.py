"""Offline patch/source guard; no AP build, runtime, or baseline mutation."""
import json
from contextlib import nullcontext
from pathlib import Path
import shutil
import subprocess
import tempfile
from prepare_ap_pv_candidate import BASE, MANIFEST_SHA, PATCH, sha


def main():
    raw = (BASE / 'wksim-build.json').read_bytes()
    assert sha(raw) == MANIFEST_SHA
    manifest = json.loads(raw)
    names = [line[6:] for line in PATCH.read_text().splitlines() if line.startswith('+++ b/')]
    assert set(names) == {'libraries/AP_DDS/AP_DDS_ExternalControl.cpp',
                          'libraries/AP_ExternalControl/AP_ExternalControl.h',
                          'ArduCopter/AP_ExternalControl_Copter.cpp',
                          'ArduCopter/AP_ExternalControl_Copter.h'}
    before = {}
    # Only four source files are copied. This is NOT a buildable source checkout.
    # Retain manifest/original hashes as review evidence, without copying a full tree.
    with nullcontext(tempfile.mkdtemp(prefix='wksim-pv-guard-')) as directory:
        root = Path(directory)
        (root / 'baseline-manifest.json').write_bytes(raw)
        for name in names:
            source = BASE / 'src' / name
            before[name] = source.read_bytes()
            assert sha(before[name]) == manifest['source']['files'][name]['sha256']
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (root / 'before-sha.json').write_text(json.dumps({p: sha(v) for p, v in before.items()}))
        for args in [('--check',), ()]:
            subprocess.run(['git', 'apply', *args, str(PATCH)], cwd=root, check=True)
        dds = (root / names[0]).read_text()
        # The source expression itself, not a separate hand-written mask policy.
        start = dds.index('        if ((cmd_pos.type_mask & required_ignored)')
        stop = dds.index('            !std::isfinite(cmd_pos.latitude)', start)
        expression = dds[start:stop].strip()[4:].rstrip().removesuffix('||').strip()
        expression = expression.replace('cmd_pos.type_mask', 'mask').replace('GlobalPosition::IGNORE_YAW', '1024').replace('||', ' or ').replace('&&', ' and ')
        rejected = compile(' '.join(expression.split()), '<actual candidate mask expression>', 'eval')
        accepted = []
        for mask in range(65536):
            if not eval(rejected, {}, dict(mask=mask, required_ignored=2496,
                                          velocity_fields=56, ignored_velocity=mask & 56)):
                accepted.append(mask)
        assert accepted == [2496, 2552, 3520, 3576], accepted
        assert 'float(v.y), float(v.x), float(-v.z)' in dds
        assert 'std::numeric_limits<float>::max()' in dds
        assert 'use_yaw ? wrap_PI(radians(90.0f) - cmd_pos.yaw) : 0.0f' in dds
        old = before[names[0]].decode()
        # Everything after the old pure-P yaw branch is byte-for-byte unchanged.
        anchor = '        if (use_yaw) {\n            // map is ENU/FLU;'
        assert dds[dds.index(anchor):] == old[old.index(anchor):]
        copter = (root / 'ArduCopter/AP_ExternalControl_Copter.cpp').read_text()
        assert 'if (!ready_for_external_control() ||' in copter
        assert '!loc.get_vector_from_origin_NED_m(position_ned_m)' in copter
        assert 'copter.mode_guided.set_pos_vel_NED_m(position_ned_m, velocity_ned_ms,' in copter
        assert 'use_yaw, use_yaw ? yaw_rad : 0.0f, false, 0.0f, false)' in copter
        subprocess.run(['git', 'apply', '--reverse', str(PATCH)], cwd=root, check=True)
        assert all((root / name).read_bytes() == value for name, value in before.items())
    assert (BASE / 'wksim-build.json').read_bytes() == raw
    assert all((BASE / 'src' / name).read_bytes() == value for name, value in before.items())
    print('PASS: isolated apply/reverse, 65536 masks, legacy tail, native conversion/call guards, baseline unchanged; evidence=' + str(root))


if __name__ == '__main__':
    main()
