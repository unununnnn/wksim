"""Build the independent #23 major recorder. This command never executes it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile

ARCHIVE = Path('/mnt/e/rflysimtools/RflySimAPIs/4.RflySimModel/1.BasicExps/e0_MinModelTemp/MulticopterModel.zip')
ARCHIVE_SHA256 = 'd528b5d247e13d943f1eaa7a37fd3cb4d15c7e9bb7a6b0e5988a1423e59d05ed'
CPP_SHA256 = 'a35d7c8f39c94f2db8c27b19affee5b66c1b001c63ded334ba83c99f8be54019'
PREFIX = 'e0_MinModelTemp/Exp1_MinModelTemp_ert_rtw/'
MEMBERS = tuple(PREFIX + name for name in
                ('Exp1_MinModelTemp.cpp', 'Exp1_MinModelTemp.h', 'rtwtypes.h')) + (
    'R2022b/simulink/include/rtw_continuous.h', 'R2022b/simulink/include/rtw_solver.h')
INCLUDE = b'#include "Exp1_MinModelTemp.h"\r\n'
DECLARATION = (b'extern void wk_capture_major(const ExtY_Exp1_MinModelTemp_T&) noexcept;\r\n')
OUTPUT_END = (b'  std::memcpy(&Exp1_MinModelTemp_Y.VehileInfo60d[33],\r\n'
              b'              &Exp1_MinModelTemp_P.Constant_Value_ea[0], 27U * sizeof(real_T));\r\n')
NEXT_CONTEXT = (b'  if (rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))) {\r\n'
                b"    // If: '<S12>/If1' incorporates:\r\n")
HOOK = (b'  if (rtmIsMajorTimeStep((&Exp1_MinModelTemp_M))) {\r\n'
        b'    wk_capture_major(Exp1_MinModelTemp_Y);\r\n'
        b'  }\r\n')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def instrument(raw):
    """Only insert bytes: retain the original encoding and every original newline."""
    if sha256(raw) != CPP_SHA256:
        raise ValueError('Unreviewed generated CPP SHA256')
    context = OUTPUT_END + NEXT_CONTEXT
    if raw.count(INCLUDE) != 1 or raw.count(context) != 1 or b'wk_capture_major' in raw:
        raise ValueError('Generated source insertion context is not unique')
    # Logical line numbers are diagnostic; the actual replacement uses raw bytes.
    before = raw[:raw.index(context) + len(OUTPUT_END)]
    if before.replace(b'\r\r\n', b'\n').replace(b'\r\n', b'\n').count(b'\n') != 7877:
        raise ValueError('Reviewed root output boundary moved')
    patched = raw.replace(INCLUDE, INCLUDE + DECLARATION, 1)
    patched = patched.replace(context, OUTPUT_END + HOOK + NEXT_CONTEXT, 1)
    if patched.replace(DECLARATION, b'', 1).replace(HOOK, b'', 1) != raw:
        raise ValueError('Instrumentation changed original source bytes')
    return patched


def read_sources(archive_path):
    raw = Path(archive_path).read_bytes()
    if sha256(raw) != ARCHIVE_SHA256:
        raise ValueError('Unreviewed model archive SHA256')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        sources = {}
        for member in MEMBERS:
            if sum(item.filename == member for item in archive.infolist()) != 1:
                raise ValueError('Missing or duplicate allowlisted ZIP member')
            if archive.getinfo(member).file_size > 2_000_000:
                raise ValueError('Unexpected allowlisted member size')
            sources[Path(member).name] = archive.read(member)
    instrument(sources['Exp1_MinModelTemp.cpp'])
    return sources


def build(archive_path=ARCHIVE):
    if platform.system() != 'Linux':
        raise RuntimeError('Requires project-owned Ubuntu-22.04 WSL /root build directory')
    sources = read_sources(archive_path)
    driver = Path(__file__).with_name('major_model_recorder.cpp').read_bytes()
    patched = instrument(sources['Exp1_MinModelTemp.cpp'])
    source_identity = dict(archive_sha256=ARCHIVE_SHA256,
        members_sha256={member: sha256(sources[Path(member).name]) for member in MEMBERS},
        original_cpp_sha256=CPP_SHA256, patched_cpp_sha256=sha256(patched),
        driver_sha256=sha256(driver), builder_sha256=sha256(Path(__file__).read_bytes()),
        phase='major root outputs complete; before subsequent explicit Update/ODE',
        output_order=['Vehicle60', 'Sensor30', 'GPS30'])
    identity_json = json.dumps(source_identity, sort_keys=True, separators=(',', ':'))
    directory = Path(tempfile.mkdtemp(prefix='wksim-major-recorder-', dir='/root'))
    for name, raw in sources.items():
        (directory/name).write_bytes(raw)
    (directory/'Exp1_MinModelTemp.original.cpp').write_bytes(sources['Exp1_MinModelTemp.cpp'])
    (directory/'Exp1_MinModelTemp.cpp').write_bytes(patched)
    (directory/'major_model_recorder.cpp').write_bytes(driver)
    (directory/'build_major_model_recorder.py').write_bytes(Path(__file__).read_bytes())
    (directory/'major_recorder_source.h').write_text(
        'static constexpr const char* WK_SOURCE_JSON = R"wksim(' + identity_json + ')wksim";\n',
        encoding='ascii')
    executable = directory/'major_model_recorder'
    command = ['g++', '-std=c++17', '-O2', '-fno-fast-math', '-Wl,--no-undefined',
        '-I', str(directory), str(directory/'Exp1_MinModelTemp.cpp'),
        str(directory/'major_model_recorder.cpp'), '-o', str(executable)]
    manifest = dict(schema_version=1, kind='major_recorder_build', status='building',
        directory=str(directory), archive=str(archive_path), source=source_identity,
        argv=command, compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
        executable=str(executable), model_executed=False,
        note='Independent observation executable; no production ABI/pin change; no numerical acceptance.')
    manifest_path = directory/'build.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        result = subprocess.run(command, cwd=directory, capture_output=True, timeout=60)
        (directory/'build.stdout.log').write_bytes(result.stdout)
        (directory/'build.stderr.log').write_bytes(result.stderr)
        manifest.update(exit_code=result.returncode, status='built' if result.returncode == 0 else 'failed')
        if result.returncode == 0:
            manifest['executable_sha256'] = sha256(executable.read_bytes())
        else:
            raise RuntimeError(f'Build failed; see {directory}/build.stderr.log')
    except subprocess.TimeoutExpired as error:
        (directory/'build.stdout.log').write_bytes(error.stdout or b'')
        (directory/'build.stderr.log').write_bytes(error.stderr or b'')
        manifest.update(status='timeout', exit_code=None)
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    args = parser.parse_args()
    print(build(args.archive))
