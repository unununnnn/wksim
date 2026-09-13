"""Run a small analytic Simulink logging fixture; never run a vehicle model."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = Path(tempfile.mkdtemp(prefix='simulink-sampling-', dir=ROOT/'validation'))
    source = ROOT/'tools/probe_simulink_sampling.m'
    staged = out/source.name
    shutil.copyfile(source, staged)
    env = dict(os.environ)
    env.pop('MATLABPATH', None)
    for name, directory in (('TEMP','temp'), ('TMP','temp'), ('MATLAB_PREFDIR','pref')):
        (out/directory).mkdir(exist_ok=True)
        env[name] = str(out/directory)
    command = ['D:/matlab/install date/bin/matlab.exe', '-wait', '-sd', str(out), '-batch', 'probe_simulink_sampling']
    identity = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (Path(__file__), source)}
    (out/'command.json').write_text(json.dumps(dict(argv=command, cwd=str(out), source_sha256=identity,
        environment_overrides={key:env[key] for key in ('TEMP','TMP','MATLAB_PREFDIR')},
        contract='The staged script fixes analytic inputs, outputs, time grid and roundoff bound before execution.'), indent=2))
    print(out, flush=True)
    with (out/'console.log').open('w') as log:
        process = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
    report = json.loads((out/'sampling.json').read_text()) if (out/'sampling.json').is_file() else {}
    unchanged = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in identity.items())
    unchanged &= staged.read_bytes()==source.read_bytes()
    passed = process.returncode==0 and report.get('status')=='pass' and unchanged
    (out/'process.json').write_text(json.dumps(dict(exit_code=process.returncode, source_unchanged=unchanged,
        status='pass' if passed else 'failed'), indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
