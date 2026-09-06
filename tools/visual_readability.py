"""Native-render display diagnostic, not flight or camera-physics acceptance.

The fixed central scene ROI excludes the HUD and most sky. Thresholds are
declared before fixing the old black/dim frames and are not dynamics budgets.
Pillow measures original pixels; it never edits, brightens or replaces frames.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Simulator.wksim_console.visual import View, ENGINE, REPO, DISPLAY_COMMANDS, _probe_port, _sha

THRESHOLDS=dict(mean_luma_min=45.0,dark_fraction_max=.25,clipped_fraction_max=.15)
ROI_FRACTION=(.15,.25,.85,.92)


def measure(path):
    with Image.open(path) as image:
        width,height=image.size
        roi=tuple(round(v*s) for v,s in zip(ROI_FRACTION,(width,height,width,height)))
        pixels=list(image.convert('RGB').crop(roi).get_flattened_data())
        values=[.2126*r+.7152*g+.0722*b for r,g,b in pixels]
    result=dict(file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=width,height=height,roi_px=roi,mean_luma=sum(values)/len(values),
        dark_fraction=sum(v<12 for v in values)/len(values),
        clipped_fraction=sum(v>245 for v in values)/len(values))
    result['readable_probe']=bool(result['mean_luma']>=THRESHOLDS['mean_luma_min'] and
        result['dark_fraction']<=THRESHOLDS['dark_fraction_max'] and
        result['clipped_fraction']<=THRESHOLDS['clipped_fraction_max'])
    return result


def readability_gate(frames, minimum=3):
    # A short native capture is inconclusive, never a three-frame pass.
    return len(frames)>=minimum and all(frame['readable_probe'] for frame in frames[-3:])


def candidate_build(path):
    """Validate a frozen staged diagnostic, not current-source deployment.

    Source drift is reported so old/new binaries can be compared after edits.
    Staging and DLL drift still fail closed. The product preflight is unchanged.
    """
    build=json.loads(path.read_text(encoding='utf-8-sig'))
    deployed=json.loads((REPO/'Simulator/ue55/state-build-manifest.json').read_text(encoding='utf-8'))
    expected={item['path'] for item in deployed['build_inputs']}
    inputs=build.get('build_inputs',[])
    if (build.get('build_exit_code')!=0 or len(inputs)!=len(expected) or
            {item['path'] for item in inputs}!=expected):
        raise ValueError('Candidate must pin the complete deployed build-input set')
    stage=Path(build['project']).resolve().parent
    if not Path(build['project']).is_file() or not ENGINE.is_file():
        raise FileNotFoundError('Candidate project or pinned UE is unavailable')
    binary=Path(build['binary']).resolve()
    if not binary.is_relative_to(stage) or _sha(binary)!=build['binary_sha256']:
        raise ValueError('Candidate DLL identity mismatch')
    build['diagnostic_source_drift']=[]
    for item in inputs+build.get('asset_inputs',[]):
        staged=(stage/item['path']).resolve()
        if not staged.is_relative_to(stage) or _sha(staged)!=item['staging_sha256']:
            raise ValueError('Candidate staged input identity mismatch: '+item['path'])
        root=(REPO/'Simulator/ue55').resolve(); source=(root/item['path']).resolve()
        if not source.is_relative_to(root):
            raise ValueError('Candidate input escapes source tree')
        current=_sha(source) if source.is_file() else None
        if current!=item['source_sha256']:
            build['diagnostic_source_drift'].append(dict(path=item['path'],
                build_sha256=item['source_sha256'],current_sha256=current))
    return build


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,action='append')
    parser.add_argument('--launch',action='store_true')
    parser.add_argument('--candidate-manifest',type=Path)
    parser.add_argument('--display-profile',choices=('reference','desktop-balanced'),default='reference')
    parser.add_argument('--probe',choices=('baseline','exposure-disabled','sun-pitch','sun-movable','exposure-cut'),default='baseline')
    parser.add_argument('--seconds',type=int,default=12)
    parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args(argv)
    if bool(args.image)==args.launch or not 4<=args.seconds<=40:
        parser.error('Select exactly --image or --launch; seconds must be 4..40')
    if not args.launch and (args.candidate_manifest or args.probe!='baseline'):
        parser.error('Candidate and diagnostic probe apply only to --launch')
    root=args.evidence.resolve();root.mkdir(parents=True,exist_ok=False)
    report=dict(status='failed',scope='Static native render diagnostic; no FC/physics/state injection',
                thresholds=THRESHOLDS,roi_fraction=ROI_FRACTION,frames=[],probe=args.probe,
                tool_sha256=_sha(__file__))
    report['display_profile']=args.display_profile
    child=None
    try:
        paths=args.image or []
        if args.launch:
            run_id='readability-'+uuid.uuid4().hex[:12]
            view=View(root/'unused-view-authority',run_id,'/tmp/wksim-'+run_id+'/state.sock')
            build=(candidate_build(args.candidate_manifest) if args.candidate_manifest else view._preflight())
            manifest=args.candidate_manifest or REPO/'Simulator/ue55/state-build-manifest.json'
            report.update(build_manifest=str(manifest.resolve()),build_manifest_sha256=_sha(manifest))
            report['diagnostic_source_drift']=build.get('diagnostic_source_drift',[])
            _probe_port()
            frames=root/'frames';frames.mkdir()
            exec_commands=(DISPLAY_COMMANDS if args.display_profile=='desktop-balanced'
                           else 't.IdleWhenNotForeground 0,t.MaxFPS 30')
            if args.probe=='exposure-disabled':
                exec_commands+=',r.EyeAdaptationQuality 0'
            command=[str(ENGINE),build['project'],
                '/Game/Maps/UrbanBlock?game=/Script/WksimVisual.WksimVisualGameMode',
                '-game','-windowed','-ResX=1280','-ResY=720','-NoSound','-NoSplash','-unattended',
                '-ExecCmds='+exec_commands,'-WksimVehicle=1',
                '-WksimRunId='+run_id,'-WksimPort=19060',
                '-abslog='+str(root/'ue.log'),'-WksimCaptureDir='+str(frames)]
            if args.probe=='sun-pitch':
                command.append('-WksimDiagnosticSunPitch=-55')
            elif args.probe=='sun-movable':
                command.append('-WksimDiagnosticMovableSun')
            elif args.probe=='exposure-cut':
                command.append('-WksimDiagnosticExposureCut')
            report.update(run_id=run_id,argv=command,binary_sha256=build['binary_sha256'])
            with (root/'ue.stdout.log').open('xb') as output:
                child=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT)
                report['pid']=child.pid
                deadline=time.monotonic()+60
                first_at=None
                while time.monotonic()<deadline:
                    if child.poll() is not None:
                        raise RuntimeError('UE exited before render diagnostic completed')
                    if list(frames.glob('frame-*.png')):
                        first_at=first_at or time.monotonic()
                    if first_at is not None and time.monotonic()-first_at>=args.seconds:
                        break
                    time.sleep(.1)
                else:
                    raise TimeoutError('No bounded native render capture')
            # Stop only the Popen instance owned here before reading complete files.
            child.terminate();child.wait(timeout=10)
            paths=sorted(frames.glob('frame-*.png'))
            report['native_capture_log']=[line for line in (root/'ue.log').read_text(errors='replace').splitlines()
                                          if re.search(r'WKSIM_(READY|CAPTURE|RENDER|LIGHT)|\[DEBUG-',line)]
        report['frames']=[measure(path) for path in paths]
        # Native runs require three frames; offline inspection may select one.
        report['minimum_frames']=3 if args.launch else 1
        report['status']='pass' if readability_gate(report['frames'],report['minimum_frames']) else 'failed'
    except Exception as error:
        report['error']=type(error).__name__+': '+str(error)
    finally:
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill();child.wait(timeout=5)
            report['launcher_returncode']=child.poll()
        with (root/'result.json').open('x',encoding='utf-8') as output:
            json.dump(report,output,ensure_ascii=False,allow_nan=False,indent=2);output.write('\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('argv','native_capture_log')},ensure_ascii=False,indent=2))
    return 0 if report['status']=='pass' else 1


if __name__=='__main__':
    raise SystemExit(main())
