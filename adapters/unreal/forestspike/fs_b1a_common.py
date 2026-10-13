import os,json,sys,hashlib
from pathlib import Path
import unreal
repo=Path(os.environ['ACW_REPO_ROOT'])
sys.path.insert(0,str(repo/'adapters/unreal/forestspike'))
from fs_common import find_actor
from fs_instances import ARCHETYPES,load_pool,pivot_shift,place
spec=json.loads((repo/'tools/forestspike/b1a/registered.json').read_text())
root=spec['root'];lib=unreal.EditorAssetLibrary
levels=unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors=unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
sub=unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
assets=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/reports/fs_assets.report.json').read_text())['meshes']
prior=json.loads((repo/'unreal/ForestSpike/Saved/ForestSpike/b01/b01_build_d/receipt.json').read_text())
def output():return Path(os.environ['ACW_FS_B1A_REPORT'])
def receipt(data):
 with output().open('x',encoding='utf-8') as f:json.dump(data,f,indent=2)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def components():
 return {key:find_actor(actors,'FS_ArmA' if key=='Tree_A' else 'FS_ArmB_'+key.removeprefix('Tree_B_')).get_component_by_class(unreal.HierarchicalInstancedStaticMeshComponent) for key in prior['meshes']}
def duplicate(src,dest):
 assert dest.startswith(root+'/') and not lib.does_asset_exist(dest),dest
 obj=lib.duplicate_asset(src,dest);assert obj and lib.save_asset(dest);return obj
def set_cvars(world):
 commands=['r.VSync 0','t.MaxFPS 0','r.ScreenPercentage 100','r.MotionBlurQuality 0','r.RayTracing 0','foliage.ForceLOD -1','r.ForceLOD -1','foliage.LODDistanceScale 1','foliage.RandomLODRange 0','r.ViewDistanceScale 1']
 for c in commands:unreal.SystemLibrary.execute_console_command(world,c)
 return {c.split()[0]:unreal.SystemLibrary.get_console_variable_float_value(c.split()[0]) for c in commands}
def populate(hs,arm,n,debug=False):
 pool,count,cols=load_pool();assert n<=count
 for key,h in hs.items():
  h.clear_instances();active=(key=='Tree_A')==(arm=='A')
  h.set_visibility(active,True);h.set_forced_lod_model(0);h.set_lod_distance_scale(1);h.set_cull_distances(0,50000);h.set_cast_shadow(True)
  h.set_static_mesh(lib.load_asset(root+('/Debug/' if debug else '/Meshes/')+key))
  if active:
   idx=range(n) if arm=='A' else [i for i in range(n) if int(pool[i*cols+5])==ARCHETYPES.index(key.removeprefix('Tree_B_'))]
   place(h,pool,cols,idx,pivot_shift(assets[key]))
def aim(p):
 e,n,z=p['eye_enu'];return unreal.Vector(e*100,-n*100,z*100),unreal.Rotator(0,p['pitch_deg'],p['heading_deg']-90)
def bind(seq,world):
 return [{'name':str(b.get_name()),'objects':[o.get_path_name() for o in unreal.MovieSceneSequenceExtensions.locate_bound_objects(seq,b,world)]} for b in seq.get_bindings()]
