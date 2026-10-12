"""Original opaque tree pilot. Blender 5.2 headless, isolated from Xinyi runtime.
blender -b --factory-startup --python-exit-code 2 --python tools/vegetation_pilot/build_pilot.py -- --work-dir PATH
Run with --skip-render for deterministic geometry/reload audit only.
"""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import bpy
from mathutils import Vector
import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / 'assets/vegetation/north_taiwan/pilot_v0'
sys.path.insert(0, str(REPO / 'tools/lookdev'))
from gltf_writer import write_glb, ue_local_bounds_cm

BASE = 'ede7960d8ec05b2aa521b1e4c65b5bbd667c456d'
RESEARCH = '796e03892d85731582ddb6c9151d3a1fe49d102a'
NAMES = ['xinyi_reference', 'dense_rounded', 'horizontal_tiered', 'open_vase', 'tall_columnar']
LABELS = ['Xinyi reference', 'Dense rounded', 'Horizontal tiered', 'Open vase', 'Tall columnar']
LIMITS = [120, 40, 20]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def code_sha(p): return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()

class Tree:
    def __init__(self, seed):
        self.vertices=[]; self.faces=[]; self.leaf=[]; self.rng=random.Random(seed)
        self.is_reference=False

    def part(self, vertices, faces, leaf):
        start=len(self.vertices); self.vertices.extend(vertices)
        self.faces.extend([tuple(start+i for i in f) for f in faces]); self.leaf.extend([leaf]*len(faces))

    def stem(self, start, end, r0, r1, sides=3, caps=True):
        a,b=Vector(start),Vector(end); axis=(b-a).normalized()
        side=axis.cross(Vector((0,1,0)))
        if side.length < 0.1: side=axis.cross(Vector((1,0,0)))
        side.normalize(); other=axis.cross(side)
        vertices=[]
        for c,r in [(a,r0),(b,r1)]:
            for j in range(sides):
                t=2*math.pi*j/sides
                vertices.append(tuple(c+r*(math.cos(t)*side+math.sin(t)*other)))
        faces=[]
        for j in range(sides):
            k=(j+1)%sides; faces.extend([(j,k,k+sides),(j,k+sides,j+sides)])
        if caps:
            for j in range(1,sides-1): faces.extend([(0,j+1,j),(sides,sides+j,sides+j+1)])
        self.part(vertices,faces,False)

    def crown(self, center, widths, rings, sides, phase=0, lean=(0,0), notch=0):
        """Asymmetric lobed radial shell, not a primitive sphere or decimated icosphere.
        rings=(normalized height, radial multiplier); caps follow irregular ring heights.
        """
        cx,cy,cz=center; rx,ry,rz=widths
        angular=[1+0.16*math.sin(j*2.35+phase)+self.rng.uniform(-0.10,0.10) for j in range(sides)]
        vertices=[]
        for row,(z,rad) in enumerate(rings):
            for j in range(sides):
                t=2*math.pi*j/sides+phase
                t+=.11*math.sin(2*t+phase)
                # Correlated lobes and small ring offsets avoid uniform balls / straight cones.
                r=rad*angular[j]*(1+self.rng.uniform(-0.13,0.13))
                zz=z+0.075*math.sin(3*t+row*0.9)+self.rng.uniform(-0.035,0.035)
                vertices.append((cx+rx*r*math.cos(t)+lean[0]*z,
                                 cy+ry*r*math.sin(t)+lean[1]*z,cz+rz*zz))
        bottom=len(vertices); vertices.append((cx-0.15*rx,cy+0.1*ry,cz-rz))
        top=len(vertices); vertices.append((cx+0.18*rx,cy-0.08*ry,cz+rz*(1-notch)))
        faces=[]
        for j in range(sides): faces.append((bottom,(j+1)%sides,j))
        for row in range(len(rings)-1):
            for j in range(sides):
                a=row*sides+j; b=row*sides+(j+1)%sides
                c=b+sides; d=a+sides
                if (row+j)%2: faces.extend([(a,b,d),(b,c,d)])
                else: faces.extend([(a,b,c),(a,c,d)])
        off=(len(rings)-1)*sides
        for j in range(sides): faces.append((off+j,off+(j+1)%sides,top))
        self.part(vertices,faces,True)

def prototype(name,lod):
    t=Tree(701+NAMES.index(name)*103+lod*19)
    sides=4 if lod==0 else (3 if lod==1 else 4)
    trunk_end={'dense_rounded':4.4,'horizontal_tiered':7.8,'open_vase':3.7,'tall_columnar':8.6}[name]
    trunk_tip=(0.18,-0.12,trunk_end)
    if name=='open_vase' and lod==2:
        # Follow the crown's offset bottom cap in XY too, with a small internal overlap.
        trunk_tip=(-.59,.76,5.15)
    t.stem((0,0,0),trunk_tip,0.24,0.10,sides,caps=(lod<2))
    if name=='dense_rounded':
        if lod==0:
            # Interlocking offset masses, different aspect/height; no spherical primitives.
            for i,(c,w) in enumerate([((-1.7,.0,5.8),(2.4,2.3,1.7)),((1.55,.2,6.2),(2.6,2.1,1.9)),
                                      ((.2,1.6,7),(2.25,2.0,1.75)),((-.3,-1.0,7.2),(2.55,2.15,1.8))]):
                t.crown(c,w,[(-.4,.83),(.3,.91)],6,.17+i*.73,lean=(.25,-.2))
            for p in [(2.1,.2,5.0),(-1.8,.7,5.4)]: t.stem((.1,0,2.8),p,.13,.06,3,caps=False)
        elif lod==1: t.crown((0,0,6.25),(4,3.25,2.8),[(-.45,.88),(.4,.91)],7,.17,lean=(.5,-.2))
        else: t.crown((0,0,6.25),(4,3.25,2.8),[(0,1)],6,.17,lean=(.5,-.2))
    elif name=='horizontal_tiered':
        plates=[((-.3,.05,4.65),(4.2,3.4,.8)),((.5,-.25,6.6),(3.6,2.8,.8)),((-.45,.28,8.35),(2.65,2.15,.8))]
        if lod==2: plates=[plates[0],((0,0,7.55),(3.25,2.6,1.55))]
        for i,(c,w) in enumerate(plates):
            if lod==0:
                # Broad branch-supported fan plus offset tuft, rather than one regular saucer.
                t.crown((c[0]-.3*w[0],c[1],c[2]),(.73*w[0],w[1],w[2]),[(-.32,.75),(.28,.95)],5,.2+i*.48)
                t.crown((c[0]+.50*w[0],c[1]-.1,c[2]+.2),(.5*w[0],.75*w[1],w[2]*.85),[(0,1)],4,.7+i*.61)
            else:
                t.crown(c,w,[(0,1)],4 if lod==1 else 3,.2+i*.24)
        if lod==0:
            t.stem((.1,0,4.1),(2.3,.4,4.7),.11,.045,3)
            t.stem((.1,0,5.7),(-1.6,-.4,6.65),.10,.045,3)
        elif lod==1: t.stem((0,0,4),(2.1,.3,4.7),.11,.045,3,caps=False)
    elif name=='open_vase':
        if lod==0:
            tips=[(-2.5,.05,6.4),(2.4,.15,7.1),(.4,2.5,7.6)]
            for i,p in enumerate(tips):
                t.stem((.12,-.08,2.7),p,.15,.055,3,caps=False)
                t.crown((p[0]*1.12,p[1]*1.12,p[2]+.75),(2.0,1.55,1.2),[(-.3,.79),(.35,.94)],6,.35+i*.7,lean=(.3,0))
        elif lod==1:
            for i,p in enumerate([(-2.6,0,6.7),(2.1,1.1,7.4)]):
                t.stem((.12,-.08,2.7),p,.15,.06,3,caps=False)
                t.crown((p[0],p[1],p[2]+.6),(2.3,2.0,1.4),[(0,1)],5,.3+i*.8)
        else:
            # Far simplification deliberately loses open branch fan; measured/reviewed, not hidden.
            t.crown((.1,.4,7),(4.6,3.6,2.0),[(.15,1)],6,.35,notch=.6)
    elif name=='tall_columnar':
        if lod==0:
            t.crown((.08,.05,7.5),(1.65,1.45,5.25),[(-.75,.60),(-.4,.91),(0,.86),(.4,.70),(.72,.45)],7,.3,lean=(.34,-.28))
            t.crown((-.75,.25,7.2),(.7,.65,1.4),[(0,1)],5,.75)
            for p in [(1.0,0,5.3),(-.8,.4,7.4)]: t.stem((0,0,3.8),p,.11,.04,3)
        elif lod==1: t.crown((.08,.05,7.5),(1.65,1.45,5.25),[(-.65,.72),(0,1),(.62,.5)],5,.3,lean=(.34,-.28))
        else: t.crown((.08,.05,7.5),(1.65,1.45,5.25),[(-.3,1),(.5,.53)],3,.3,lean=(.34,-.28))
    if lod>0:
        # Match outer bounds to LOD0 without adding triangles; does not imply matching silhouette.
        target=np.asarray(prototype(name,0).vertices); v=np.asarray(t.vertices)
        lo,hi=v.min(axis=0),v.max(axis=0); a,b=target.min(axis=0),target.max(axis=0)
        t.vertices=((v-lo)/(hi-lo)*(b-a)+a).tolist()
    return t

def reference():
    """Execute only existing write_tree_mesh AST; never run build_ground.main or load GIS inputs."""
    p=REPO/'tools/lookdev/build_ground.py'; module=ast.parse(p.read_text(encoding='utf-8'))
    fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='write_tree_mesh')
    captured={}
    def capture(path,primitives,mesh_name):
        write_glb(path,primitives,mesh_name); captured.update(primitives[0])
    env={'np':np,'write_glb':capture,'ue_local_bounds_cm':ue_local_bounds_cm}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),env)
    env['write_tree_mesh'](OUT/'models/xinyi_reference_original.glb')
    t=Tree(7); p=captured['positions']; p=np.column_stack([p[:,0],-p[:,2],p[:,1]])
    t.is_reference=True
    t.vertices=p.tolist(); t.faces=captured['indices'].tolist(); t.leaf=[True]*20+[False]*8
    return t

def arrays(tree):
    v=np.asarray(tree.vertices,dtype=float); f=np.asarray(tree.faces,dtype=int)
    tri=v[f]; cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]); area=np.linalg.norm(cross,axis=1)
    assert np.isfinite(v).all() and (area>1e-8).all(), 'Invalid/degenerate triangle'
    face_norm=cross/area[:,None]; smooth=np.zeros_like(v)
    for i,face in enumerate(f):
        if tree.leaf[i]:
            for j in face: smooth[j]+=cross[i]
    lens=np.linalg.norm(smooth,axis=1); smooth[lens>0]/=lens[lens>0,None]
    normals=[]; colors=[]
    for i,face in enumerate(f):
        for j in face:
            # Same foliage/bark color and height-based value ramp on every tree, including reference.
            if tree.leaf[i]:
                shade=.6+.5*min(1,max(0,(v[j,2]-3.5)/5))
                color=np.array([.07,.11,.035])*shade
                normals.append(face_norm[i] if tree.is_reference else smooth[j])
            else: color=np.array([.10,.08,.06]); normals.append(face_norm[i])
            colors.append([*color,1])
    return tri.reshape(-1,3),np.asarray(normals),np.asarray(colors),v,f

def export(tree,name,lod):
    p,n,c,v,f=arrays(tree)
    # Blender Z-up -> glTF Y-up proper rotation; same physical metre scale, roots at ground.
    y_up=lambda a: np.column_stack([a[:,0],a[:,2],-a[:,1]]).astype(np.float32)
    path=OUT/'models'/f'{name}_lod{lod}.glb'
    colors=np.uint8(np.rint(np.clip(c,0,1)*255))
    # Merge identical position/normal/color tuples; retain deliberate hard bark seams.
    packed=np.concatenate([y_up(p),y_up(n),colors.astype(np.float32)],axis=1)
    unique,indices=np.unique(packed,axis=0,return_inverse=True)
    write_glb(path,[{'name':'PilotOpaqueShared','positions':unique[:,:3],'normals':unique[:,3:6],
        'color0':unique[:,6:].astype(np.uint8), 'indices':indices.astype(np.uint32).reshape(-1,3),
        'base_color':[1,1,1,1]}],mesh_name=f'{name}_LOD{lod}')
    return {'archetype':name,'lod':lod,'triangles':len(f),'topology_vertices':len(v),
        'exported_vertices':len(unique),'material_slots':1,'dimensions_m':np.round(v.max(axis=0)-v.min(axis=0),5).tolist(),
        'bounds_z_up_m':[np.round(v.min(axis=0),5).tolist(),np.round(v.max(axis=0),5).tolist()],
        'filename':path.relative_to(OUT).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)}

def mesh_obj(tree,name,mat):
    p,n,c,v,f=arrays(tree); mesh=bpy.data.meshes.new(name); mesh.from_pydata(v.tolist(),[],f.tolist()); mesh.update()
    obj=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj); mesh.materials.append(mat)
    attr=mesh.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='CORNER')
    for i,x in enumerate(c): attr.data[i].color=x
    for i,poly in enumerate(mesh.polygons): poly.use_smooth=bool(tree.leaf[i]) and name!='xinyi_reference'
    return obj

def reload_audit(records):
    for e in records:
        before=set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=str(OUT/e['filename']))
        imported=[o for o in bpy.data.objects if o not in before and o.type=='MESH']
        tris=sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in imported)
        assert tris==e['triangles']
        pts=np.asarray([tuple(o.matrix_world@v.co) for o in imported for v in o.data.vertices])
        assert np.allclose(pts.max(axis=0)-pts.min(axis=0),e['dimensions_m'],atol=2e-5)
        e['blender_reload']={'status':'PASS','triangles':tris,'vertices':sum(len(o.data.vertices) for o in imported),
                             'material_slots':sum(len(o.material_slots) for o in imported)}
        for o in imported: bpy.data.objects.remove(o,do_unlink=True)

def setup():
    scene=bpy.context.scene; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=24
    scene.cycles.use_denoising=True; scene.cycles.seed=31
    scene.render.image_settings.file_format='PNG'; scene.render.resolution_percentage=100
    scene.view_settings.view_transform='Standard'; scene.view_settings.look='Medium High Contrast'
    scene.world=bpy.data.worlds.new('NeutralWorld'); scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(.68,.74,.8,1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=.6
    sun_data=bpy.data.lights.new('FixedSun','SUN'); sun_data.energy=2.0; sun_data.angle=math.radians(12)
    sun=bpy.data.objects.new('FixedSun',sun_data); scene.collection.objects.link(sun); sun.rotation_euler=(.45,-.55,-.4)
    mat=bpy.data.materials.new('PilotOpaqueShared'); mat.use_nodes=True
    nodes=mat.node_tree.nodes; bs=nodes.get('Principled BSDF'); bs.inputs['Roughness'].default_value=.85
    bs.inputs['Specular IOR Level'].default_value=.25
    attr=nodes.new('ShaderNodeVertexColor'); attr.layer_name='Color'; mat.node_tree.links.new(attr.outputs['Color'],bs.inputs['Base Color'])
    cam_data=bpy.data.cameras.new('LockedCamera'); cam=bpy.data.objects.new('LockedCamera',cam_data); scene.collection.objects.link(cam)
    scene.camera=cam; cam.data.clip_start=.1; cam.data.clip_end=2000
    return scene,cam,mat

def aim(cam,pos,target,ortho=None):
    cam.location=pos; cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO' if ortho else 'PERSP'
    if ortho: cam.data.ortho_scale=ortho
    else:
        cam.data.sensor_fit='VERTICAL'; cam.data.sensor_height=24; cam.data.lens=24/(2*math.tan(math.radians(30)))

def main():
    arg=argparse.ArgumentParser(); arg.add_argument('--work-dir',type=Path,required=True); arg.add_argument('--skip-render',action='store_true')
    arg.add_argument('--render-only',nargs='+',help='Replace only named frames in an existing complete review run')
    args=arg.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    work=args.work_dir.resolve(); work.mkdir(parents=True,exist_ok=True); (OUT/'models').mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    trees={('xinyi_reference',0):reference()}; records=[]
    for name in NAMES[1:]:
        for lod in range(3):
            t=prototype(name,lod); trees[name,lod]=t; e=export(t,name,lod)
            assert e['triangles']<=LIMITS[lod],(name,lod,e['triangles']); records.append(e)
    ref=export(trees['xinyi_reference',0],'xinyi_reference_preview',0); assert ref['triangles']==28
    records.append(ref); reload_audit(records)
    manifest={'schema':'acw.vegetation_pilot/0','baseline_sha':BASE,'research_inventory_sha':RESEARCH,
        'generation_date':'2026-10-12','numpy_version':np.__version__,
        'source_code_hash_normalization':'CRLF to LF only; image and GLB hashes use untouched bytes',
        'source_code_sha256':{p.relative_to(REPO).as_posix():code_sha(p) for p in [Path(__file__),Path(__file__).with_name('package_review.py'),REPO/'tools/lookdev/gltf_writer.py',REPO/'tools/lookdev/build_ground.py',REPO/'tools/lookdev/shaders/xinyi_city.hlsl']},
        'generator':'Original deterministic procedural mesh; no ImageGen, leaf cards, textures, third-party models or runtime integration',
        'blender_version':bpy.app.version_string,'units':'metres; GLB Y-up; modelling/render Z-up',
        'budgets_hypotheses':LIMITS,'assets':records,
        'reference_original':{'filename':'models/xinyi_reference_original.glb','sha256':sha(OUT/'models/xinyi_reference_original.glb'),
            'bytes':(OUT/'models/xinyi_reference_original.glb').stat().st_size,'triangles':28,'exported_vertices':84,'material_slots':1,
            'method':'Unmodified write_tree_mesh AST from baseline build_ground.py, isolated execution. Preview counterpart uses identical triangles with shared pilot colors.'},
        'render_assumptions':{'engine':'Cycles CPU','samples':24,'denoise':True,'seed':31,'perspective_vfov_degrees':60,
            'distance_image_px':[1920,1080],'orthographic_lineup_width_m':65,'light':'same fixed sun + neutral world',
            'shader':'shared opaque vertex color; height ramp approximates xc_foliage, no leafN noise, no exact Unreal shader equivalence',
            'real_device_measurements':False},'runtime_modified':False}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if args.skip_render: print('PASS_GEOMETRY_AND_RELOAD'); return
    scene,cam,mat=setup(); objects=[]
    def clear():
        for obj in objects: bpy.data.objects.remove(obj,do_unlink=True)
        objects.clear()
    def add(name,lod,x=0,y=0,scale=1,yaw=0):
        o=mesh_obj(trees[name,lod],name,mat); o.location=(x,y,0); o.scale=(scale,scale,scale); o.rotation_euler.z=yaw; objects.append(o); return o
    results=[]
    def render(name,w=1500,h=650):
        if args.render_only and name not in args.render_only: return
        scene.render.resolution_x=w; scene.render.resolution_y=h; scene.render.filepath=str(work/(name+'.png'))
        bpy.ops.render.render(write_still=True); p=Path(scene.render.filepath)
        results.append({'id':name,'filename':p.name,'dimensions':[w,h],'bytes':p.stat().st_size,'sha256':sha(p),'status':'PASS'})
    def lineup(lod=0):
        clear()
        for i,name in enumerate(NAMES): add(name,0 if i==0 else lod,(i-2)*12)
        # Same 2m ruler beside every archetype, 0.2m square base; neutral shared material.
        for i in range(5):
            bpy.ops.mesh.primitive_cube_add(size=1,location=((i-2)*12-5.0,0,1)); o=bpy.context.object
            o.scale=(.12,.12,2); objects.append(o)
    lineup(); aim(cam,(0,-80,18),(0,0,6),65); render('shaded_front')
    aim(cam,(28,-80,38),(0,0,6),65); render('shaded_oblique')
    aim(cam,(-18,-80,44),(0,0,6),65); render('shaded_reverse')
    # Material override for silhouette: same locked camera, no surface shading interpretation.
    black=bpy.data.materials.new('SilhouetteBlack'); black.use_nodes=True; ns=black.node_tree.nodes; ns.clear()
    em=ns.new('ShaderNodeEmission'); em.inputs['Color'].default_value=(.005,.005,.005,1); out=ns.new('ShaderNodeOutputMaterial'); black.node_tree.links.new(em.outputs[0],out.inputs[0])
    scene.view_layers[0].material_override=black
    aim(cam,(0,-80,6),(0,0,6),65); render('silhouette_front')
    aim(cam,(28,-80,38),(0,0,6),65); render('silhouette_oblique')
    scene.view_layers[0].material_override=None
    for lod in [1,2]: lineup(lod); aim(cam,(0,-80,18),(0,0,6),65); render('lod'+str(lod))
    clear()
    for row,name in enumerate(NAMES):
        for col,(scale,yaw) in enumerate([(.8,.0),(1,.8),(1.25,1.7),(1,2.9)]): add(name,0,(col-1.5)*15,(row-2)*16,scale,yaw)
    aim(cam,(52,-110,110),(0,0,4),110); render('repetition',1500,1100)
    clear(); rng=random.Random(51)
    for row in range(4):
        for col in range(5):
            name=NAMES[1+(row*3+col)%4]; add(name,0,(col-2)*10+rng.uniform(-2,2),(row-1.5)*11+rng.uniform(-2,2),rng.uniform(.8,1.25),rng.uniform(0,math.tau))
    aim(cam,(38,-55,42),(0,0,5),68); render('mixed_grove',1300,950)
    # Native physical perspective framing; same lineup and same 60-degree vertical FOV for all ranges.
    lineup()
    for distance in [150,300,600,800]:
        pitch=math.radians(12); target=Vector((0,0,6))
        aim(cam,target+Vector((0,-distance*math.cos(pitch),distance*math.sin(pitch))),target)
        render('range_'+str(distance),1920,1080)
    if args.render_only:
        previous=json.loads((work/'render_results.json').read_text())['renders']
        replaced={r['id']:r for r in results}
        assert set(args.render_only)==set(replaced), 'Unknown requested frame'
        results=[replaced.get(r['id'],r) for r in previous]
    (work/'render_results.json').write_text(json.dumps({'renders':results,'assumptions':manifest['render_assumptions']},indent=2)+'\n')
    print('PASS_PILOT_RENDER',len(results))

if __name__=='__main__': main()
