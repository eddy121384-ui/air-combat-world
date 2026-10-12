"""Compose compact review sheets and audit actual GLB buffers. Python + Pillow + NumPy.
python tools/vegetation_pilot/package_review.py --work-dir ../vegetation-pilot-work
--validate performs a portable read-only package audit.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image,ImageDraw,ImageFont

REPO=Path(__file__).resolve().parents[2]
OUT=REPO/'assets/vegetation/north_taiwan/pilot_v0'
LABELS=['Xinyi 28t','Dense rounded','Tiered','Open vase','Columnar']

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def code_sha(p): return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def font(n):
    try: return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',n)
    except OSError: return ImageFont.load_default(size=n)

def glb(path):
    data=path.read_bytes(); magic,version,size=struct.unpack_from('<III',data)
    assert magic==0x46546c67 and version==2 and size==len(data)
    length,kind=struct.unpack_from('<II',data,12); assert kind==0x4e4f534a
    j=json.loads(data[20:20+length]); blen,bkind=struct.unpack_from('<II',data,20+length); assert bkind==0x004e4942
    blob=data[28+length:28+length+blen]
    def accessor(i):
        a=j['accessors'][i]; v=j['bufferViews'][a['bufferView']]
        dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
        components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        assert 'byteStride' not in v
        return np.frombuffer(blob,dtype=dtype,count=a['count']*components,
            offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],components)
    return j,accessor

def audit_assets(m):
    results=[]
    for e in m['assets']+[m['reference_original']]:
        p=OUT/e['filename']; assert sha(p)==e['sha256'] and p.stat().st_size==e['bytes']
        j,get=glb(p); assert not j.get('textures') and not j.get('images')
        for material in j['materials']:
            assert material.get('alphaMode','OPAQUE')=='OPAQUE'
            assert material['pbrMetallicRoughness']['baseColorFactor'][3]==1
        all_positions=[]; count=0; nv=0; degenerates=0
        for primitive in j['meshes'][0]['primitives']:
            assert primitive.get('mode',4)==4
            v=get(primitive['attributes']['POSITION']); n=get(primitive['attributes']['NORMAL']); f=get(primitive['indices']).reshape(-1,3)
            assert np.isfinite(v).all() and np.isfinite(n).all() and (f<len(v)).all()
            assert np.allclose(np.linalg.norm(n,axis=1),1,atol=1e-5)
            tri=v[f]; area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)
            degenerates+=int((area<=1e-8).sum()); count+=len(f); nv+=len(v); all_positions.extend(v)
        assert degenerates==0 and count==e['triangles'] and nv==e['exported_vertices']
        if 'dimensions_m' in e:
            v=np.asarray(all_positions); dims=(v.max(axis=0)-v.min(axis=0))[[0,2,1]]
            assert np.allclose(dims,e['dimensions_m'],atol=2e-5)
        if 'lod' in e and e['archetype']!='xinyi_reference_preview':
            assert count<=[120,40,20][e['lod']]
        results.append({'filename':e['filename'],'status':'PASS','triangles':count,'exported_vertices':nv,'degenerate_triangles':0,'opaque':True,'textures':0})
    # Same baseline geometry; shared material preview changes only shading/attribute packaging.
    j,a=glb(OUT/m['reference_original']['filename']); p=j['meshes'][0]['primitives'][0]
    original=a(p['attributes']['POSITION'])[a(p['indices']).reshape(-1,3)]
    j,a=glb(OUT/'models/xinyi_reference_preview_lod0.glb'); p=j['meshes'][0]['primitives'][0]
    preview=a(p['attributes']['POSITION'])[a(p['indices']).reshape(-1,3)]
    assert np.array_equal(original,preview), 'Reference triangles changed'
    for name in ['dense_rounded','horizontal_tiered','open_vase','tall_columnar']:
        dims=[e['dimensions_m'] for e in m['assets'] if e['archetype']==name]
        assert np.allclose(dims,dims[0],atol=2e-5), 'LOD bounds drift'
    return results

def build(work):
    m=json.loads((OUT/'manifest.json').read_text()); audit=audit_assets(m)
    snapshot=work/'model_hashes_before_rebuild.json'
    if snapshot.exists():
        previous=json.loads(snapshot.read_text())
        current={p.name:sha(p) for p in (OUT/'models').glob('*.glb')}
        assert previous==current
        m['reproducibility']={'status':'PASS','separate_generation_runs':2,'byte_identical_glbs':14,'sha256_by_filename':current}
    renders=json.loads((work/'render_results.json').read_text()); assert len(renders['renders'])==13
    for r in renders['renders']:
        p=work/r['filename']; assert sha(p)==r['sha256'] and p.stat().st_size==r['bytes']
        with Image.open(p) as im: im.load(); assert list(im.size)==r['dimensions']
    review=OUT/'review'; review.mkdir(exist_ok=True)
    def load(name): return Image.open(work/(name+'.png')).convert('RGB')
    def lineup_crop(name): return load(name).crop((0,100,1500,570))  # fixed crop, never aspect-distort trees
    def save(im,name): im.save(review/name,optimize=True)
    def row_labels(d,y,width):
        for i,label in enumerate(LABELS):
            d.text((int((i+.5)*width/5)-45,y),label,font=font(17),fill='white')
    sheet=Image.new('RGB',(1500,1690),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'NORTHERN TAIWAN / OPAQUE CROWN PILOT - IDENTICAL SHARED MATERIAL',font=font(25),fill='white')
    for row,(name,label) in enumerate([('shaded_front','Front / 2m scale bars'),('shaded_oblique','Oblique / crown depth'),('shaded_reverse','Reverse oblique / asymmetry')]):
        y=55+row*540; d.text((20,y),label,font=font(20),fill='white'); row_labels(d,y+28,1500)
        sheet.paste(lineup_crop(name),(0,y+55))
    save(sheet,'crown_comparison.png')
    sheet=Image.new('RGB',(1500,1100),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'SILHOUETTES / FRONT + OBLIQUE / SAME ROOT SCALE',font=font(27),fill='white')
    for row,name in enumerate(['silhouette_front','silhouette_oblique']):
        y=65+row*505; row_labels(d,y,1500); sheet.paste(lineup_crop(name),(0,y+28))
    save(sheet,'silhouette_comparison.png')
    sheet=Image.new('RGB',(1500,1690),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'AUTHORED LODS / SAME CAMERA AND BOUNDS; BASELINE ALWAYS 28t',font=font(25),fill='white')
    for row,name in enumerate(['shaded_front','lod1','lod2']):
        y=55+row*540; d.text((20,y),'LOD'+str(row)+' / caps '+str([120,40,20][row])+'t (hypotheses)',font=font(19),fill='white')
        row_labels(d,y+28,1500); sheet.paste(lineup_crop(name),(0,y+55))
    save(sheet,'lod_comparison.png')
    sheet=Image.new('RGB',(1500,1180),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'REPETITION / 5 ARCHETYPES x 4 INSTANCES / SHARED MATERIAL',font=font(25),fill='white')
    d.text((20,45),'Scale 0.8 / 1.0 / 1.25 / 1.0; yaw 0 / 46 / 97 / 166 degrees. No new per-instance mesh seeds.',font=font(19),fill='white')
    sheet.paste(load('repetition'),(0,80)); save(sheet,'repetition.png')
    sheet=Image.new('RGB',(1300,1030),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'MIXED GROVE / 20 LOD0 INSTANCES / FOUR ARCHETYPES',font=font(26),fill='white')
    d.text((20,45),'Fixed seed 51, size/yaw variation only; preview placement does not modify Xinyi.',font=font(19),fill='white')
    sheet.paste(load('mixed_grove'),(0,80)); save(sheet,'mixed_grove.png')
    # Never auto-fit range crops: show native pixels and explicitly labeled nearest-neighbor enlargements.
    sheet=Image.new('RGB',(1500,1170),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((20,12),'DISTANCE FRAMING / 1920x1080 / 60 deg VERTICAL FOV / LOD0 ONLY',font=font(25),fill='white')
    ranges=[]
    for row,distance in enumerate([150,300,600,800]):
        y=65+row*275; im=load('range_'+str(distance)); focal=1080/(2*math.tan(math.radians(30)))
        full=im.resize((480,270),Image.Resampling.LANCZOS); sheet.paste(full,(0,y))
        d.text((490,y),str(distance)+'m / full frame left is 25% scale',font=font(19),fill='white')
        crop=im.crop((640,460,1280,620)); sheet.paste(crop,(490,y+35))
        d.text((490,y+198),'Central crop above: NATIVE pixels, no resize',font=font(17),fill='white')
        # Central crop stays same rectangle for every distance, not fitted to a tree.
        zoom=im.crop((864,500,1056,596)).resize((360,180),Image.Resampling.NEAREST); sheet.paste(zoom,(1140,y+35))
        d.text((1140,y+220),'Center zoom 1.875x',font=font(17),fill='white')
        ranges.append({'distance_m':distance,'focal_px':focal,'reference_8_436m_projected_height_px_approx':round(focal*8.43619/distance,2),
                       'native_crop_xyxy':[640,460,1280,620],'zoom_crop_xyxy':[864,500,1056,596],
                       'camera':'12deg pitch, target (0,0,6)m, Euclidean distance to lineup center; edge trees slightly farther'})
    save(sheet,'distance_comparison.png')
    # Actual 1080p framing retained for inspection, compact enough for GitHub.
    # Do not commit giant concatenation; original sizes/hashes remain in render report.
    m['visual_review_files']=[{'filename':p.relative_to(OUT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p),
        'dimensions':list(Image.open(p).size)} for p in sorted(review.glob('*.png'))]
    m['distance_previews']=ranges; m['render_results']=renders['renders']; m['buffer_validation']=audit
    m['measurements']={'prototype_glb_count':12,'reference_glb_count':2,
        'prototype_glb_bytes':sum(e['bytes'] for e in m['assets'] if e['archetype']!='xinyi_reference_preview'),
        'all_glb_bytes':sum(p.stat().st_size for p in (OUT/'models').glob('*.glb')),
        'review_png_bytes':sum(p.stat().st_size for p in review.glob('*.png')),'render_count':13,'render_failures':0,
        'reference_triangles_identical':True,'matching_lod_bounds':True,'real_device_performance':'NOT MEASURED'}
    (OUT/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
    validate()

def validate():
    m=json.loads((OUT/'manifest.json').read_text()); result=audit_assets(m)
    for filename,expected in m['source_code_sha256'].items(): assert code_sha(REPO/filename)==expected
    assert len(result)==14 and len(m['visual_review_files'])==6 and len(m['render_results'])==13
    for e in m['visual_review_files']:
        p=OUT/e['filename']; assert sha(p)==e['sha256'] and p.stat().st_size==e['bytes']
        with Image.open(p) as im: im.load(); assert list(im.size)==e['dimensions'] and im.format=='PNG'
    assert not m['runtime_modified']
    print(json.dumps({'status':'PASS','models':12,'reference_models':2,'sheets':6,'renders':13,'degenerate_triangles':0,'opaque':True,'runtime_modified':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--work-dir',type=Path); p.add_argument('--validate',action='store_true'); args=p.parse_args()
    if args.validate: validate()
    else:
        if not args.work_dir: p.error('--work-dir required')
        build(args.work_dir)
