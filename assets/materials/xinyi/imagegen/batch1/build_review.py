"""Offline deterministic review only. Requires Pillow and NumPy; no runtime dependency.
Run with --validate to audit without changing files. Original AI bytes are never edited.
"""
from pathlib import Path
import argparse, hashlib, json, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def font(size):
    try: return ImageFont.truetype('C:/Windows/Fonts/arial.ttf', size)
    except OSError: return ImageFont.load_default(size=size)
def metrics(im):
    a = np.asarray(im.convert('RGB'), dtype=float)
    return {'horizontal_wrap_mae_255': round(float(np.abs(a[:,0]-a[:,-1]).mean()),3),
            'vertical_wrap_mae_255': round(float(np.abs(a[0]-a[-1]).mean()),3),
            'mean_255': round(float(a.mean()),3), 'std_255':round(float(a.std()),3)}
def edge_blend(im, width=64):
    # Opposing border pair converges to their average, smoothly over 64 pixels.
    # No mirroring, synthesis, clone stamps, random noise or content generation.
    a=np.asarray(im,dtype=float).copy()
    for axis in (1,0):
        for i in range(width):
            t=0.5*(1-i/(width-1))**2
            if axis==1:
                left,right=a[:,i].copy(),a[:,-1-i].copy()
                a[:,i]=(1-t)*left+t*right; a[:,-1-i]=(1-t)*right+t*left
            else:
                top,bottom=a[i].copy(),a[-1-i].copy()
                a[i]=(1-t)*top+t*bottom; a[-1-i]=(1-t)*bottom+t*top
    return Image.fromarray(np.uint8(np.clip(np.rint(a),0,255)))

NOTES={
 'a1':('needs revision','Grout phase and partial border tiles cause visible horizontal/vertical repeat joins; regular ceramic grid is intentional but no seamless candidate accepted.'),
 'a2':('accepted','Quiet mineral plaster; raw broad tonal edge steps. Candidate smooth border blend removes edge jump; soft mottling still repeats.'),
 'a3':('needs revision','Panel joints do not close consistently at borders; repeated running-bond phase breaks and fine grain remain. No seamless candidate accepted.'),
 'b1':('accepted','Raw edge discontinuities and fine stain texture. Candidate low-pass and edge blend retain broad damp fields; recognizable broad blobs still recur every 32m.'),
 'b2':('needs revision','Repair structure is distinct but overly dense and large; cropped patches create abrupt border joins and camouflage-like repetition. No seamless candidate accepted.'),
 'b3':('accepted','Gravity-aligned varied runs; raw stains break at edges and have fine noise. Candidate low-pass and blend remove edge jump; 32m groups remain recognizable.')}

def repeat(im,size=300):
    tile=im.convert('RGB').resize((size//3,size//3),Image.Resampling.LANCZOS)
    out=Image.new('RGB',(size,size))
    for y in range(3):
        for x in range(3): out.paste(tile,(x*(size//3),y*(size//3)))
    return out

def build():
    if (ROOT/'manifest_r1.json').exists():
        raise RuntimeError('r1 is archived; use build_revision_r2.py to rebuild current review')
    log=json.loads((ROOT/'generation_log.json').read_text())
    for folder in ('sources','normalized_1024','processed','review'): (ROOT/folder).mkdir(exist_ok=True)
    entries=[]; derivatives=[]
    for asset in log['assets']:
        sid=asset['id']; name=asset['file']; src=ROOT/'sources'/name
        original=Path(asset['original_path'])
        if not src.exists(): shutil.copyfile(original,src)
        assert digest(src)==digest(original), 'Original bytes changed'
        with Image.open(src) as im:
            im.load(); dimensions=list(im.size); source_mode=im.mode
            rgb=np.asarray(im.convert('RGB'),dtype=np.int16)
            delta=int(np.max(np.max(rgb,axis=2)-np.min(rgb,axis=2)))
            im=im.convert('L' if sid.startswith('b') else 'RGB').resize((1024,1024),Image.Resampling.LANCZOS)
        norm=ROOT/'normalized_1024'/name; im.save(norm)
        derivatives.append({'source_id':sid,'kind':'normalized review copy','operation':'Pillow convert L for masks / RGB for color, then Lanczos resize 1254 square to 1024 square; no automatic sRGB-to-linear conversion','output_filename':norm.relative_to(ROOT).as_posix(),'output_sha256':digest(norm)})
        status,note=NOTES[sid]; candidates=[]
        if status=='accepted':
            candidate=im
            operations=['start from normalized_1024 copy']
            if sid.startswith('b'):
                candidate=candidate.filter(ImageFilter.GaussianBlur(8))
                a=np.asarray(candidate,dtype=float)
                a=(a-a.min())/(a.max()-a.min())*32+112
                candidate=Image.fromarray(np.uint8(np.rint(a)))
                operations+=['Gaussian blur sigma=8px (~0.25m at 32m span)','min/max linear remap to 112..144, neutral midpoint 128; numeric control values, no gamma interpretation']
            candidate=edge_blend(candidate)
            operations+=['64px opposing-border pair averaging, weight=0.5*(1-i/63)^2, x then y; identical boundary values, does not guarantee imperceptible derivative joins']
            dest=ROOT/'processed'/name.replace('.png','_candidate.png'); candidate.save(dest)
            candidates=[dest.relative_to(ROOT).as_posix()]
            derivatives.append({'source_id':sid,'kind':'processed game material candidate','operation':operations,'output_filename':candidates[0],'output_sha256':digest(dest),'dimensions':[1024,1024],'status':'accepted for offline review, pending artistic approval','tiling_metrics':metrics(candidate)})
        entries.append({'id':sid,'filename':src.relative_to(ROOT).as_posix(),'role':asset['label'],'material_family':'ageing mask' if sid.startswith('b') else 'material base',
          'dimensions':dimensions,'mode':source_mode,'sha256':digest(src),'generation_capability':log['capability'],'model':log['model'],'prompt':asset['prompt'],
          'generation_date':log['generation_date'],'independent_ai_output':True,'status':status,'acceptance_scope':'source/candidate offline review only; not production approval',
          'visible_tiling_problems':note,'tiling_metrics':metrics(Image.open(src)),'source_rgb_channel_max_difference':delta,
          'normalized_copy':norm.relative_to(ROOT).as_posix(),'processed_derivative_files':candidates,'imported_into_unreal':False})
    contact=Image.new('RGB',(1260,1040),'#172029'); d=ImageDraw.Draw(contact)
    d.text((20,12),'TAIPEI / IMAGEGEN BATCH 1 - ORIGINAL SOURCES',font=font(26),fill='white')
    for i,e in enumerate(entries):
        x=20+(i%3)*415; y=60+(i//3)*485
        sample=Image.open(ROOT/e['filename']).convert('RGB').resize((390,390),Image.Resampling.LANCZOS)
        contact.paste(sample,(x,y)); d.text((x,y+395),e['role'],font=font(20),fill='white')
        d.text((x,y+422),Path(e['filename']).name,font=font(15),fill='#ccd7df')
        d.text((x,y+443),'AI: built-in image_gen.imagegen | '+e['status'],font=font(15),fill='#ccd7df')
    contact.save(ROOT/'review/contact_sheet.png')
    sheet=Image.new('RGB',(1880,810),'#172029'); d=ImageDraw.Draw(sheet)
    d.text((16,10),'3x3 REPEATS / RAW (left) vs CANDIDATE (right); no candidate = needs revision',font=font(25),fill='white')
    for i,e in enumerate(entries):
        x=16+(i%3)*620; y=60+(i//3)*370
        d.text((x,y),e['role']+' / '+e['status'],font=font(19),fill='white')
        sheet.paste(repeat(Image.open(ROOT/e['filename'])),(x,y+28))
        if e['processed_derivative_files']: sheet.paste(repeat(Image.open(ROOT/e['processed_derivative_files'][0])),(x+305,y+28))
        else: d.text((x+322,y+140),'NEEDS REVISION',font=font(20),fill='#e5b477')
        d.text((x,y+332),'RAW / 1254 source',font=font(15),fill='white')
        d.text((x+305,y+332),'1024 processed candidate' if e['processed_derivative_files'] else 'No accepted derivative',font=font(15),fill='white')
    sheet.save(ROOT/'review/tiling_review.png')
    rejected=[]
    for r in log['rejected_attempts']:
        p=Path(r['path']); rejected.append({**r,'sha256':digest(p),'dimensions':list(Image.open(p).size),'tracked_image':False})
    manifest={'schema':'acw.material_pack/0','pilot':'xinyi-imagegen-batch1','starting_remote_head':log['starting_sha'],
       'branch':'spike/xinyi-material-imagegen-batch1','target_branch':'feat/opus55-xinyi-visual-quality','generation_attempts':7,
       'rejected_generations':1,'independent_ai_source_count':6,'accepted_independent_ai_source_count':3,'needs_revision_source_count':3,
       'processed_variant_count':3,'normalized_copy_count':6,'total_image_file_count':17,'review_image_count':2,'production_atlas_count':0,'images_imported_into_unreal':0,
       'sources':entries,'derivatives':derivatives,'rejected_attempts':rejected,
       'review_files':[{'filename':f'review/{f}','sha256':digest(ROOT/'review'/f)} for f in ('contact_sheet.png','tiling_review.png')],
       'limitations':['Offline source review only; no engine, motion, distance or performance validation.', 'Source dimensions and microdetail do not themselves establish useful aerial scale.', 'No model ID or seed exposed; no invented model/seed.', 'Native source masks are RGB with small channel drift; use normalized L derivatives.', 'Sources are AI outputs, not third-party texture downloads; licensing uniqueness not independently certified.']}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    validate()

def validate():
    m=json.loads((ROOT/'manifest.json').read_text())
    if m.get('revision')=='r2':
        from build_revision_r2 import validate as validate_revision
        return validate_revision()
    assert len(m['sources'])==6 and len(m['derivatives'])==9
    files=[]
    for e in m['sources']:
        p=ROOT/e['filename']; assert digest(p)==e['sha256']; files.append(p)
        with Image.open(p) as im: im.load(); assert list(im.size)==e['dimensions'] and im.format=='PNG'
        assert not e['imported_into_unreal']
    for e in m['derivatives']:
        p=ROOT/e['output_filename']; assert digest(p)==e['output_sha256']; files.append(p)
        with Image.open(p) as im:
            im.load(); assert im.size==(1024,1024) and im.format=='PNG'
            if e['source_id'].startswith('b'): assert im.mode=='L'
            if e['kind']=='processed game material candidate':
                a=np.asarray(im); assert np.array_equal(a[:,0],a[:,-1]) and np.array_equal(a[0],a[-1])
    for e in m['review_files']:
        p=ROOT/e['filename']; assert digest(p)==e['sha256']; files.append(p)
        with Image.open(p) as im: im.load(); assert im.format=='PNG'
    assert len(files)==17 and set(files)==set(ROOT.rglob('*.png'))
    print(json.dumps({'validation':'PASS','originals':6,'normalized_1024':6,'accepted_processed':3,'review_sheets':2,'total_png':17,'atlases':0,'unreal_imports':0}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--validate',action='store_true'); args=parser.parse_args()
    validate() if args.validate else build()
