import sys,json,tempfile,csv,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'b1a'))
from integrity import expected,verify
class B1aTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.file=Path(self.t.name)/'data.csv'
  self.s=json.loads((Path(__file__).parent/'b1a/registered.json').read_text())
 def run_case(self,path,corrupt=None):
  cfg={'group':'A1','view':path or 'static','path_id':path,'pose':self.s['static_poses'][0]}
  frames=self.s['paths'][path]['capture_frames'] if path else 601
  vectors=[[0]*9]+[sum(expected(self.s,cfg,i)[:3],[]) for i in range(frames-1)]
  if corrupt:corrupt(vectors)
  with self.file.open('w',newline='') as f:
   w=csv.writer(f);w.writerows([['',10,1,1,1,8]+v for v in vectors]);w.writerow(['EVENTS','FrameTime','GameThreadTime','RenderThreadTime','RHIThreadTime','GPUTime']+['View/'+n+k for n in ['Pos','Forward','Up'] for k in 'XYZ'])
  return verify(self.file,self.s,cfg)[0]
 def test_static(self):self.assertEqual(self.run_case(None)['status'],'PASS_FS_B1A_MOTION')
 def test_v3(self):self.assertEqual(self.run_case('V3')['status'],'PASS_FS_B1A_MOTION')
 def test_v5_full_inward_orbit(self):self.assertEqual(self.run_case('V5')['status'],'PASS_FS_B1A_MOTION')
 def test_stationary_v5_rejected(self):
  def change(v):
   for x in v[1:]:x[:3]=v[1][:3]
  self.assertEqual(self.run_case('V5',change)['status'],'FAIL_FS_B1A_MOTION')
 def test_wrong_v5_heading_rejected(self):
  def change(v):v[300][3:6]=[1,0,0]
  self.assertEqual(self.run_case('V5',change)['status'],'FAIL_FS_B1A_MOTION')
 def test_moving_static_rejected(self):
  def change(v):v[300][0]+=100
  self.assertEqual(self.run_case(None,change)['status'],'FAIL_FS_B1A_MOTION')
if __name__=='__main__':unittest.main()
