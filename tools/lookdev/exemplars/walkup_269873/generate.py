"""Single-building, toggleable facade kit over existing accepted Look triangles.

Reads existing GLB attributes only. Never extrudes/retriangulates a footprint or
writes a city tile. The same bay/floor grammar can be applied to another walkup.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(REPO / '.capture-python'), str(REPO / 'tools/lookdev')]
import numpy as np
from gltf_writer import read_glb_primitives, write_glb, ue_local_bounds_cm

OUT = REPO / 'unreal/Saved/XinyiExemplar/Walkup269873'
BID = 'tp_building_height.269873'


def frac(x):
    return x - np.floor(x)


def h21(x, y):
    p = frac(np.array([x, y, x], np.float32) * np.float32(.1031))
    p += np.dot(p, p[[1, 2, 0]] + np.float32(33.33))
    return float(frac((p[0] + p[1]) * p[2]))


def h31(x, y, z):
    p = frac(np.array([x, y, z], np.float32) * np.float32(.1031))
    p += np.dot(p, p[[1, 0, 2]] + np.float32(31.32))
    return float(frac((p[0] + p[1]) * p[2]))


class Kit:
    def __init__(self, pivot):
        self.pivot = np.array(pivot)
        self.p, self.n, self.rgb, self.i = [], [], [], []
        self.parts = {}

    def box(self, face, s0, s1, d0, d1, z0, z1, color, category):
        if min(s1-s0, d1-d0, z1-z0) <= .001:
            raise ValueError('Degenerate module')
        origin, tangent, normal = (np.array(face[k]) for k in ('origin', 'tangent', 'normal'))
        points = []
        for s, d, z in ((s0,d0,z0),(s1,d0,z0),(s1,d1,z0),(s0,d1,z0),
                        (s0,d0,z1),(s1,d0,z1),(s1,d1,z1),(s0,d1,z1)):
            v = origin + tangent*s + normal*d + np.array([0,0,z]) - self.pivot
            points.append(np.array([v[0], v[2], -v[1]]))
        center = np.mean(points, axis=0)
        for quad in ((0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)):
            q = [points[j] for j in quad]
            normal = np.cross(q[1]-q[0], q[2]-q[0])
            if np.dot(normal, np.mean(q,axis=0)-center) < 0:
                q.reverse()
                normal = -normal
            normal /= np.linalg.norm(normal)
            start = len(self.p)
            self.p.extend(q)
            self.n.extend([normal]*4)
            self.rgb.extend([color]*4)
            self.i.extend(((start,start+1,start+2),(start,start+2,start+3)))
        self.parts[category] = self.parts.get(category, 0) + 1

    def primitive(self):
        colors = np.array(self.rgb, np.float32)
        return dict(name='WalkupKit', positions=np.array(self.p,np.float32),
                    normals=np.array(self.n,np.float32), indices=np.array(self.i,np.uint32),
                    uv0=colors[:,:2], uv1=np.column_stack([colors[:,2],np.full(len(colors),.74)]),
                    uv2=np.zeros((len(colors),2),np.float32))


def generate(revision):
    OUT.mkdir(parents=True, exist_ok=True)
    look = REPO / 'unreal/Saved/XinyiLook'
    with gzip.open(look / 'look_buildings.jsonl.gz', 'rt', encoding='utf-8') as stream:
        style = next(r for r in map(json.loads,stream) if r['building_id'] == BID)
    assert style['archetype'] == 1 and style['facade_generation'] == 'legacy'
    # Accepted per-building payload, then spatial / height gate. No record is edited.
    payload = 32768 + (style['archetype']*16+style['variant'])*256+style['seed']
    report = json.loads((look / 'look_tiles.report.json').read_text())
    tile = next(t for t in report['tiles'] if t['tile'] == '-001_-001')
    source = look / 'tiles' / tile['path']
    mesh = read_glb_primitives(source)[0]
    p, uv, packed, normals = [mesh[k] for k in ('position','texcoord_0','texcoord_2','normal')]
    mask = (np.abs(packed[:,0]-payload)<.1) & (np.abs(mesh['texcoord_1'][:,0]-15.95)<.001)
    assert int(mask.sum()) == 97  # Pinned exemplar binding, not a general city skip rule.
    world = np.column_stack([p[:,0]+tile['origin_enu_m'][0],
                             -p[:,2]+tile['origin_enu_m'][1],p[:,1]])
    assert np.all((world[mask,0]>-368)&(world[mask,0]<-341))
    assert np.all((world[mask,1]>-318)&(world[mask,1]<-289))
    ground, top = float(world[mask,2].min()), float(world[mask,2].max())
    pivot = [float((world[mask,0].min()+world[mask,0].max())/2),
             float((world[mask,1].min()+world[mask,1].max())/2),ground]
    fh = style['floor_h']
    # Preserve r1 as the recorded rejected attempt. r2 matches xc_city's seed,
    # which deliberately differs from the packed vc.g normalisation.
    seed = style['seed']/255 if revision=='r1' else float(np.float32(style['seed']/256)+np.float32(.00123))
    bw = 3.6*(.9+.2*float(frac(np.float32(seed)*np.float32(7.13))))
    period = 2+math.floor(float(frac(seed*11.3))*3)
    faces = []
    wall = mask & (np.abs(normals[:,1])<.01) & ((packed[:,1]%256)//16>=3)
    for key in sorted(set(tuple(v) for v in np.round(normals[wall],5))):
        select = wall & np.all(np.abs(normals-np.array(key))<.00002,axis=1)
        ids = np.where(select & (uv[:,1]<.01))[0]
        if len(ids)<2:
            continue
        low, high = ids[np.argmin(uv[ids,0])], ids[np.argmax(uv[ids,0])]
        start, end = world[low].astype(float), world[high].astype(float)
        tangent = (end-start)/np.linalg.norm(end-start)
        normal = np.array([key[0],-key[2],0.0]); normal/=np.linalg.norm(normal)
        faces.append(dict(origin=start.tolist(),tangent=tangent.tolist(),normal=normal.tolist(),
                          length=float(np.linalg.norm(end-start)),u0=float(uv[low,0]),u1=float(uv[high,0])))
    assert len(faces)==2
    kit = Kit(pivot)
    records=[]
    depth = .52 if revision == 'r1' else .82
    bar = .035 if revision == 'r1' else .055
    spacing = .25 if revision == 'r1' else .34
    for face in faces:
        for bay in range(math.floor(face['u0']/bw),math.ceil(face['u1']/bw)):
            slot=bay%period; col=h21(slot,seed*71)
            balc=col>=.78; narrow=.60<=col<.78
            pier=.52<=col<.60 and float(frac(seed*3.1))>=.5
            if pier:
                continue
            wx0,wx1=(.36,.64) if narrow else (.12,.88)
            left=max(.08,bay*bw+wx0*bw-face['u0'])
            right=min(face['length']-.08,bay*bw+wx1*bw-face['u0'])
            if right-left<.75:
                continue
            for floor in range(2,round((top-ground)/fh)):
                # Existing shop/sign grammar occupies 1.72 floors; leave it untouched.
                z0=floor*fh+(.46 if narrow else .30)*fh; z1=(floor+.82)*fh
                if z0<1.72*fh or z1>top-ground-.15:
                    continue
                cell=h31(bay,floor,seed*97)
                caged=balc or float(frac(cell*7.1))>=.38
                metal=[.38,.37,.32] if cell>.55 else [.19,.145,.10]
                frame=[.57,.57,.50] if revision=='r1' else [.44,.43,.38]
                sill=[.52,.46,.35] if revision=='r1' else [.44,.395,.32]
                glass=[.075,.13,.12]
                d=depth if caged else .16
                b=lambda a,b,c,e,f,g,color,category:kit.box(face,a,b,c,e,f,g,color,category)
                if revision=='r1':
                    b(left,right,.015,.045,z0,z1,glass,'glass_backing')
                for x in (left,right-.075):
                    b(x,x+.075,.04,.19,z0-.07,z1+.07,frame,'window_reveal')
                for z in (z0-.07,z1):
                    b(left,right,.04,.19,z,z+.07,frame,'window_reveal')
                b((left+right)/2-.025,(left+right)/2+.025,.045,.10,z0,z1,frame,'window_mullion')
                # Balcony/cage ledge and head create readable depth / shadow at range.
                b(left-.07,right+.07,.025,d+.07,z0-.18,z0-.06,sill,'projecting_sill')
                if caged:
                    b(left-.07,right+.07,.025,d+.09,z1+.05,z1+.15,frame,'cage_canopy')
                    for x in (left,right-bar):
                        b(x,x+bar,.07,d,z0,z1,metal,'cage_side')
                    for x in np.linspace(left,right-bar,max(3,round((right-left)/spacing))):
                        b(float(x),float(x)+bar,d-.04,d,z0,z1,metal,'cage_vertical')
                    for z in (z0,z0+(z1-z0)*.38,z1-bar):
                        b(left,right,d-.04,d,z,z+bar,metal,'cage_horizontal')
                    # End cheeks make projection readable obliquely without filling it.
                    for x in (left,right-bar):
                        for z in (z0,z1-bar):
                            b(x,x+bar,.04,d,z,z+bar,metal,'cage_side_return')
                if balc:
                    b(left,right,d-.10,d,z0-.65,z0-.18,sill,'balcony_knee')
                records.append(dict(face=faces.index(face),bay=bay,floor=floor,balcony=balc,caged=caged,
                                    window=[left,right,z0,z1],projection_m=d))
                # AC service module: existing shader AC column, one unit per selected bay/floor.
                colac=h21(slot,seed*37)
                if colac<1-.55*1.35 or float(frac(cell*3.7))<.22:
                    continue
                acleft=float(frac(colac*5.9))>=.5
                a=bay*bw+(.06 if acleft else .60)*bw-face['u0']
                if a<.08 or a+.84>face['length']-.08:
                    continue
                acz=(floor+.05)*fh
                b(a,a+.84,.025,.46,acz,acz+.67,[.67,.65,.57],'ac_body')
                b(a+.08,a+.60,.46,.475,acz+.10,acz+.57,[.16,.18,.17],'ac_grille')
                for j in range(6):
                    x=a+.10+j*.085
                    b(x,x+.022,.475,.49,acz+.11,acz+.56,[.48,.49,.44],'ac_fins')
                for x in (a+.08,a+.70):
                    b(x,x+.045,.04,.49,acz-.055,acz-.015,metal,'ac_bracket')
                    b(x,x+.045,.025,.07,acz-.32,acz-.015,metal,'ac_bracket')
    primitive=kit.primitive()
    path=OUT/('walkup_kit_'+revision+'.glb')
    write_glb(path,[primitive],'Walkup269873_'+revision)
    back=read_glb_primitives(path)[0]
    assert np.array_equal(back['position'],primitive['positions'])
    tri=back['position'][back['indices']]
    areas=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
    assert np.isfinite(tri).all() and float(areas.min())>1e-7
    # Same physical FOV at every distance. Pairwise cameras are immutable.
    target=np.array([-362.105,-305.505,ground+15.95*.62])
    angle=math.radians(217.2+8); pitch=math.radians(35)
    direction=np.array([math.cos(angle)*math.cos(pitch),math.sin(angle)*math.cos(pitch),math.sin(pitch)])
    shots={f'distance_{d:03d}m':dict(eye=(target+direction*d).tolist(),target=target.tolist(),fov=50,distance_m=d)
           for d in (50,150,300)}
    manifest=dict(building_id=BID,revision=revision,pivot_enu_m=pivot,ground_m=ground,height_m=top-ground,
                  source_tile=tile['tile'],source_glb=str(source.relative_to(REPO)),
                  source_glb_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_payload=payload,
                  scope='Two street-facing walls, above existing storefront, one building only; overlay toggle',
                  grammar=dict(floor_height_m=fh,bay_width_m=bw,period=period),faces=faces,modules=records,
                  parts=kit.parts,triangles=len(primitive['indices']),vertices=len(primitive['positions']),
                  material_sections=1,texture_samples=0,nanite=False,shadows=True,
                  glb=path.name,glb_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  expected_local_bounds=ue_local_bounds_cm(primitive['positions']),
                  qa=dict(roundtrip_exact=True,min_triangle_area_m2=float(areas.min()),finite=True),shots=shots)
    (OUT/('kit_'+revision+'.json')).write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ('revision','triangles','vertices','parts','material_sections')},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--revision',choices=['r1','r2'],default='r1')
    generate(parser.parse_args().revision)
