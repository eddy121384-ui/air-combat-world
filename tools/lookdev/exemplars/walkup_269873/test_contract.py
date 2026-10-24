"""Offline integration QA of the actual submitted geometry and UE receipts."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/lookdev'))
import numpy as np
from gltf_writer import read_glb_primitives

EVIDENCE=ROOT/'docs/evidence/xinyi-walkup-exemplar-269873'


class ExemplarContract(unittest.TestCase):
    def test_triangle_geometry_and_normals(self):
        for revision in ('r1','r2'):
            p=read_glb_primitives(EVIDENCE/'assets'/('walkup_kit_'+revision+'.glb'))
            self.assertEqual(len(p),1)
            mesh=p[0]; tri=mesh['position'][mesh['indices']]
            cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            self.assertTrue(np.isfinite(tri).all())
            self.assertTrue((np.linalg.norm(cross,axis=1)>1e-7).all())
            normal=mesh['normal'][mesh['indices'][:,0]]
            self.assertTrue((np.sum(cross*normal,axis=1)>0).all())
            manifest=json.loads((EVIDENCE/'assets'/('kit_'+revision+'.json')).read_text())
            imported=json.loads((EVIDENCE/'assets'/('import_'+revision+'.json')).read_text())
            self.assertEqual(len(tri),manifest['triangles'])
            self.assertEqual(len(tri),imported['triangles'])
            self.assertEqual(imported['sections'],1)

    def test_single_building_storefront_and_scope(self):
        data=json.loads((EVIDENCE/'assets/kit_r2.json').read_text())
        self.assertEqual(data['building_id'],'tp_building_height.269873')
        self.assertEqual(len(data['faces']),2)
        self.assertEqual(len(data['modules']),12)
        self.assertNotIn('glass_backing',data['parts'])
        for module in data['modules']:
            face=data['faces'][module['face']]
            left,right,bottom,top=module['window']
            self.assertGreaterEqual(left,0)
            self.assertLessEqual(right,face['length'])
            self.assertGreaterEqual(bottom,1.72*data['grammar']['floor_height_m'])
            self.assertLess(top,data['height_m'])

    def test_camera_distances_and_capture_pairing(self):
        summary=json.loads((EVIDENCE/'summary.json').read_text())
        before=summary['variants']['before']['metadata']
        for revision in ('r1','r2'):
            after=summary['variants'][revision]['metadata']
            for key in ('shots','observed_settings','resolution','level_sha256','base_material_sha256','lighting','clouds'):
                self.assertEqual(before[key],after[key])
            self.assertEqual(after['overlay_actors_added'],1)
        for shot in before['shots'].values():
            distance=np.linalg.norm(np.array(shot['eye'])-shot['target'])
            self.assertAlmostEqual(distance,shot['distance_m'],places=8)
            self.assertEqual(shot['fov'],50)

    def test_raw_UE_PNG_integrity_and_preview_budget(self):
        summary=json.loads((EVIDENCE/'summary.json').read_text())
        for variant in ('before','r1','r2'):
            for record in summary['variants'][variant]['raw_PNGs']:
                path=EVIDENCE/'captures'/variant/record['name']
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),record['sha256'])
        for comparison in summary['comparisons']:
            for key in ('full_jpeg','detail_jpeg'):
                path=EVIDENCE/comparison[key]['path']
                self.assertLess(path.stat().st_size,1_000_000)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),comparison[key]['sha256'])


if __name__=='__main__':
    unittest.main()
