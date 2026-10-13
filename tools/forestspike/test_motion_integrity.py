import json
import tempfile
import unittest
from pathlib import Path
from motion_integrity import expected, verify


class MotionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv=Path(self.tmp.name)/'motion.csv'
        self.spec=json.loads(Path(__file__).with_name('b01_registered_d.json').read_text())
        self.positions=[]
        self.forward=[]
        self.up=[]
        for i in range(self.spec['capture_frames']-1):
            p,f,u,*_=expected(self.spec,i)
            self.positions.append(p);self.forward.append(f);self.up.append(u)

    def run_gate(self):
        names=['EVENTS','FrameTime','GameThreadTime','RenderThreadTime','RHIThreadTime','GPUTime']
        names += ['View/'+n+k for n in ('Pos','Forward','Up') for k in 'XYZ']
        lines=[','.join(map(str,['',10,1,1,1,8]+[0]*9))]
        lines += [','.join(map(str,['',10,1,1,1,8]+p+f+u)) for p,f,u in zip(self.positions,self.forward,self.up)]
        lines.append(','.join(names))
        self.csv.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        return verify(self.csv,self.spec)[0]

    def test_complete_warm_hold_and_flight(self):
        result=self.run_gate()
        self.assertEqual(result['status'],'PASS_FS_B01_MOTION')
        self.assertEqual(result['flight_samples'],1081)

    def test_stationary_camera_rejected(self):
        self.positions=[self.positions[0]]*len(self.positions)
        self.assertEqual(self.run_gate()['status'],'FAIL_FS_B01_MOTION')

    def test_warm_hold_motion_rejected(self):
        self.positions[50][0]+=100
        self.assertEqual(self.run_gate()['status'],'FAIL_FS_B01_MOTION')

    def test_missing_endpoint_rejected(self):
        self.positions=self.positions[:900]
        self.forward=self.forward[:900];self.up=self.up[:900]
        self.assertEqual(self.run_gate()['status'],'FAIL_FS_B01_MOTION')

    def test_wrong_orientation_rejected(self):
        self.forward[400]=[1,0,0]
        self.assertEqual(self.run_gate()['status'],'FAIL_FS_B01_MOTION')

    def test_restore_to_start_after_sequence_rejected(self):
        self.positions[-3:]=[self.positions[0]]*3
        self.assertEqual(self.run_gate()['status'],'FAIL_FS_B01_MOTION')

    def test_nonfinite_camera_vector_rejected(self):
        self.positions[400][0]=float('nan')
        result=self.run_gate()
        self.assertEqual(result['status'],'FAIL_FS_B01_MOTION')
        self.assertIn('Nonfinite',result['errors'][0])


if __name__=='__main__':unittest.main()
