"""Project known native fixture geometry into actual SceneCapture PNGs."""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path

from PIL import Image,ImageChops,ImageDraw,ImageFilter

EDGE_PIXELS=2
COVERAGE=.995


def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def rotate(q,v):
    a=cross(q[:3],v);b=cross(q[:3],a)
    return [v[i]+2*q[3]*a[i]+2*b[i] for i in range(3)]
def hull(points):
    points=sorted(set(points))
    def turn(o,a,b):return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];hi=[]
    for p in points:
        while len(lo)>=2 and turn(lo[-2],lo[-1],p)<=0:lo.pop()
        lo.append(p)
    for p in reversed(points):
        while len(hi)>=2 and turn(hi[-2],hi[-1],p)<=0:hi.pop()
        hi.append(p)
    return lo[:-1]+hi[:-1]
def project_box(obj,metadata):
    pose=metadata['camera_world_pose'];q=pose['quaternion_xyzw'];inverse=[-q[0],-q[1],-q[2],q[3]]
    points=[]
    for bits in itertools.product((0,1),repeat=3):
        local=[obj['mesh_bounds_max' if bits[i] else 'mesh_bounds_min'][i]*obj['scale'][i] for i in range(3)]
        rotated=rotate(obj['quaternion_xyzw'],local)
        world=[obj['position_cm'][i]+rotated[i]-pose['position_cm'][i] for i in range(3)]
        x,y,z=rotate(inverse,world)
        if x<=0:raise ValueError('Fixture corner behind camera')
        k=metadata['K'];points.append((k[0]*y/x+k[2]-.5,-k[4]*z/x+k[5]-.5))
    return hull(points)
def count(image):return image.histogram()[255]
def masks(metadata,fixture):
    size=(metadata['width'],metadata['height']);out={}
    for obj in fixture['objects']:
        mask=Image.new('L',size)
        if obj['visible']:ImageDraw.Draw(mask).polygon(project_box(obj,metadata),fill=255)
        out[obj['name']]=mask
    out['red']=ImageChops.subtract(out['RedTarget'],out['GreenOccluder'])
    out['green']=out['GreenOccluder']
    return out
def color_masks(image):
    raw=image.convert('RGB').tobytes();channels=[raw[i::3] for i in range(3)];result={}
    for name,index in (('red',0),('green',1)):
        m=Image.new('L',image.size);others=[i for i in range(3) if i!=index]
        m.putdata([255 if p[index]>=60 and all(p[index]>1.5*p[j] for j in others) else 0 for p in zip(*channels)]);result[name]=m
    return result
def compare(image,metadata,fixture):
    expected=masks(metadata,fixture);observed=color_masks(image);result={}
    for name in ('red','green'):
        core=expected[name].filter(ImageFilter.MinFilter(2*EDGE_PIXELS+1))
        expanded=expected[name].filter(ImageFilter.MaxFilter(2*EDGE_PIXELS+1))
        n=count(core);actual=count(observed[name])
        if name=='green' and fixture['case_id']!=2:
            if actual>4:raise ValueError('Unexpected visible green occluder')
            result[name]=dict(observed=actual);continue
        if n<500 or actual<500:raise ValueError(name+': too few real/expected interior pixels')
        coverage=count(ImageChops.multiply(core,observed[name]))/n
        precision=count(ImageChops.multiply(expanded,observed[name]))/actual
        if coverage<COVERAGE or precision<COVERAGE:raise ValueError(f'{name}: projected coverage {coverage:.6f}, precision {precision:.6f}')
        result[name]=dict(interior_pixels=n,observed_pixels=actual,coverage=coverage,precision=precision)
    return result
def audit(root):
    root=Path(root).resolve();report=json.loads((root/'report.json').read_text())
    if report['status']!='pass':raise ValueError('Underlying real RGB flow did not pass')
    fixture_path=Path(report['view_final']['rgb_fixture_manifest']);fixture=json.loads(fixture_path.read_text())
    if fixture['schema']!='wksim.rgb-calibration-visual.v1' or fixture['physics_authority'] is not False:
        raise ValueError('Not the declared visual calibration fixture')
    if fixture['case_id']!=report['fixture_case']:raise ValueError('Reported fixture case differs')
    config=report['view_final']['rgb_config'];case=fixture['case_id']
    mount=[30,80,120] if case==1 else [30,0,100]
    q=[0,0,math.sin(math.radians(10)),math.cos(math.radians(10))] if case==3 else [0,0,0,1]
    if (config['width'],config['height'],config['horizontal_fov_degrees'],config['position_cm'],config['quaternion_xyzw'])!=(640,480,90,mount,q):
        raise ValueError('Camera configuration differs from predeclared case')
    expected={'BlueBackground':([425,0,100],[1,230,230]),'RedTarget':([400,0,100],[1,160,160]),'GreenOccluder':([350,0,100],[1,40,180])}
    if set(o['name'] for o in fixture['objects'])!=set(expected):raise ValueError('Fixture object set differs')
    for obj in fixture['objects']:
        p,s=expected[obj['name']];actual=[(obj['mesh_bounds_max'][i]-obj['mesh_bounds_min'][i])*obj['scale'][i] for i in range(3)]
        if obj['position_cm']!=p or math.dist(actual,s)>1e-5 or obj['quaternion_xyzw']!=[0,0,0,1]:raise ValueError('Fixture geometry differs from predeclared case')
    frames=[]
    for frame in report['frames']:
        path=Path(frame['image_path']);metadata=json.loads(Path(frame['metadata_path']).read_text())
        if metadata!=frame['metadata'] or metadata['K']!=[320,0,320,0,320,240,0,0,1]:
            # Trigonometric evaluation may differ by roundoff, but never use a
            # different focal length to fit observed pixels.
            if metadata!=frame['metadata'] or math.dist(metadata['K'],[320,0,320,0,320,240,0,0,1])>1e-9:
                raise ValueError('Camera intrinsics/consumer metadata changed')
        with Image.open(path) as image:
            image.load();result=compare(image,metadata,fixture)
        frames.append(dict(step=metadata['step'],image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),result=result))
    if len(frames)<15:raise ValueError('Missing consumed real PNGs')
    return dict(status='pass',case_id=fixture['case_id'],edge_tolerance_pixels=EDGE_PIXELS,required_coverage=COVERAGE,
                fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),frames=frames)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:r=audit(a.directory)
    except (OSError,ValueError,KeyError,TypeError) as error:r=dict(status='failed',error=repr(error))
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k) for k in ('status','case_id','error')}));raise SystemExit(r['status']!='pass')
