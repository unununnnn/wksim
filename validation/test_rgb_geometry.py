"""Analytic raster fixtures test the verifier; these are not sensor evidence."""
import unittest
from PIL import Image,ImageDraw
from tools.audit_rgb_geometry import compare,project_box


def fixture(case=0):
    rows=[]
    for name,p,size in (('BlueBackground',[425,0,100],[1,230,230]),
                        ('RedTarget',[400,0,100],[1,160,160]),('GreenOccluder',[350,0,100],[1,40,180])):
        rows.append(dict(name=name,position_cm=p,scale=[x/100 for x in size],mesh_bounds_min=[-50]*3,
                         mesh_bounds_max=[50]*3,quaternion_xyzw=[0,0,0,1],visible=name!='GreenOccluder' or case==2))
    return dict(case_id=case,objects=rows)
def metadata():
    return dict(width=640,height=480,K=[320,0,320,0,320,240,0,0,1],
                camera_world_pose=dict(position_cm=[30,0,100],quaternion_xyzw=[0,0,0,1]))


class GeometryTests(unittest.TestCase):
    def test_analytic_projection_and_visible_occlusion(self):
        target=fixture()['objects'][1];polygon=project_box(target,metadata())
        self.assertAlmostEqual(min(p[0] for p in polygon),319.5-320*80/369.5)
        self.assertAlmostEqual(max(p[1] for p in polygon),239.5+320*80/369.5)
        image=Image.new('RGB',(640,480),'blue');draw=ImageDraw.Draw(image)
        draw.rectangle((251,171,388,308),fill='red')
        self.assertGreater(compare(image,metadata(),fixture())['red']['coverage'],.995)
        draw.rectangle((300,150,339,329),fill=(0,255,0))
        self.assertGreater(compare(image,metadata(),fixture(2))['green']['coverage'],.995)
        with self.assertRaises(ValueError):compare(image,metadata(),fixture(0))

    def test_empty_and_displaced_pixels_fail(self):
        image=Image.new('RGB',(640,480),'blue')
        with self.assertRaises(ValueError):compare(image,metadata(),fixture())
        ImageDraw.Draw(image).rectangle((261,171,398,308),fill='red')
        with self.assertRaises(ValueError):compare(image,metadata(),fixture())


if __name__=='__main__':unittest.main()
