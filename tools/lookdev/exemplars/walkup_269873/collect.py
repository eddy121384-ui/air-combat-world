"""Collect untouched UE PNGs plus symmetric mobile JPEG comparisons. No UE run."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO=Path(__file__).resolve().parents[4]
SOURCE=REPO/'unreal/Saved/XinyiExemplar/Walkup269873'
OUT=REPO/'docs/evidence/xinyi-walkup-exemplar-269873'
CROPS={50:(576,280,1664,896),150:(800,400,1248,704),300:(864,448,1120,640)}
MATCH=('shots','resolution','lighting','clouds','observed_settings','level_sha256','base_material_sha256')


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(source,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)
    assert sha(source)==sha(destination)


def pair(panels,title,note,destination):
    w,h=panels[0].size
    assert panels[1].size==(w,h)
    canvas=Image.new('RGB',(2*w+48,h+160),(32,32,32))
    draw=ImageDraw.Draw(canvas)
    titlefont=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',28)
    labelfont=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',38)
    note_font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    draw.text((16,8),title,font=titlefont,fill='white')
    for index,(panel,label) in enumerate(zip(panels,('Before','After (r2)'))):
        x=16+index*(w+16)
        draw.text((x,54),label,font=labelfont,fill='white')
        canvas.paste(panel,(x,112))
    draw.text((16,h+124),note,font=note_font,fill=(210,210,210))
    destination.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(destination,quality=90,subsampling=0,optimize=True,progressive=True)
    assert destination.stat().st_size<1_000_000
    return {'path':destination.relative_to(OUT).as_posix(),'bytes':destination.stat().st_size,
            'sha256':sha(destination),'dimensions':list(canvas.size)}


def main():
    summary={'status':'PASS_EXEMPLAR_CAPTURE_COLLECTION','variants':{},'comparisons':[],
             'iteration_limit':'r1 and one targeted r2 only','mobile_validation':False,
             'actual_RHI_draw_calls_measured':False,'draw_submission_estimate':'+1 section per visible raster pass; additional depth/shadow passes',
             'raw_images_unmodified':True,'performance':'GPU-synchronised capture + readback wall time, n=40 per pose; not pure GPU or gameplay FPS'}
    summary['art_assessment']={'50m':'clear depth / shadow improvement',
        '150m':'visible cage / sill and AC layering improvement',
        '300m':'subtle in full frame; stronger identification criterion not conclusively met',
        'overall':'PARTIAL_VISUAL_SUCCESS; pending human art review',
        'next':'Review and resolve 300m hierarchy / residual flat features before starting huaxia'}
    reference=None
    for variant in ('before','r1','r2'):
        folder=SOURCE/'captures'/variant
        receipt=load(folder/'look_capture.report.json')
        meta=load(folder/'metadata.json')
        assert receipt['status']=='PASS_LOOK_CAPTURE' and receipt['reopen_ok'] and not receipt['level_saved']
        assert len(receipt['captures'])==3 and meta['resolution']==[1920,1080]
        if reference is None:
            reference=meta
        for key in MATCH:
            assert meta[key]==reference[key],(variant,key)
        for name,shot in meta['shots'].items():
            assert abs(float(np.linalg.norm(np.array(shot['eye'])-shot['target']))-shot['distance_m'])<1e-8
        originals_for_variant=[]
        for record in receipt['captures']:
            source=Path(record['path'])
            assert source.parent==folder and source.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            with Image.open(source) as image:
                assert image.size==(1920,1080)
            copy(source,OUT/'captures'/variant/source.name)
            originals_for_variant.append({'name':source.name,'sha256':sha(source),'bytes':source.stat().st_size})
        for filename in ('look_capture.report.json','metadata.json'):
            copy(folder/filename,OUT/'captures'/variant/filename)
        summary['variants'][variant]={'performance':receipt['perf'],'metadata':meta,'raw_PNGs':originals_for_variant}
    for revision in ('r1','r2'):
        for filename in ('kit_'+revision+'.json','import_'+revision+'.json','walkup_kit_'+revision+'.glb'):
            copy(SOURCE/filename,OUT/'assets'/filename)
        summary['variants'][revision]['mesh_import']=load(SOURCE/('import_'+revision+'.json'))
    for process in SOURCE.glob('process-*.json'):
        assert load(process)['ExitCode']==0
        copy(process,OUT/'receipts'/process.name)
    logs=[]
    for stage,variant in (('import','r1'),('capture','before'),('capture','r1'),('import','r2'),('capture','r2')):
        path=next(SOURCE.glob(stage+'-'+variant+'-*.log'))
        content=path.read_text(encoding='utf-8-sig',errors='replace')
        assert 'LogExit: Exiting.' in content
        snippets=[line for line in content.splitlines() if any(key in line for key in
            ('EXEMPLAR_','LogPython: Error','Error:','LogExit:','LogD3D12RHI: Found D3D12 adapter','LogD3D12RHI: Chosen D3D12 Adapter'))]
        target=OUT/'logs'/(path.stem+'.excerpt.log')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('\n'.join(snippets)+'\n',encoding='utf-8')
        logs.append({'stage':stage,'variant':variant,'full_local_log':str(path),
                     'full_log_sha256':sha(path),'normal_exit_log':True,
                     'observed_driver_exit_code':0,
                     'exit_code_source':'driver console output; r2 also has native process receipt'})
    summary['execution']=logs
    for distance,crop in CROPS.items():
        images=[]
        originals=[]
        for variant in ('before','r2'):
            path=OUT/'captures'/variant/f'distance_{distance:03d}m__day.png'
            with Image.open(path) as image:
                images.append(image.convert('RGB'))
            originals.append({'path':path.relative_to(OUT).as_posix(),'sha256':sha(path)})
        full=pair([i.resize((768,432),Image.Resampling.LANCZOS) for i in images],
                  f'Walk-up 269873 | {distance} m | FOV 50 deg',
                  'UE5 full frame | Both sides 40% | Same camera / lighting',OUT/'review'/f'{distance:03d}m-full-ab.jpg')
        detail=pair([i.crop(crop) for i in images],f'{distance} m | native pixel crop',
                    'Same crop | No enhancement',OUT/'review'/f'{distance:03d}m-detail-ab.jpg')
        delta=np.abs(np.array(images[0],np.int16)-np.array(images[1],np.int16))
        pixels=np.max(delta,axis=2)>3
        ys,xs=np.where(pixels)
        roi=pixels[crop[1]:crop[3],crop[0]:crop[2]]
        summary['comparisons'].append({'distance_m':distance,'inputs':originals,'crop_xyxy':crop,
            'full_jpeg':full,'detail_jpeg':detail,'mean_abs_RGB_delta':float(delta.mean()),
            'changed_pixels_above_3':int(pixels.sum()),'changed_pixels_in_crop':int(roi.sum()),
            'change_bbox_xyxy':None if not len(xs) else [int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)]})
    # CC0 real photograph; visibly separate from the UE evidence.
    with Image.open(SOURCE/'reference-alfred-twu-cc0.jpg') as image:
        image.thumbnail((960,720),Image.Resampling.LANCZOS)
        image.save(OUT/'reference-alfred-twu-2018-cc0.jpg',quality=88,optimize=True)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'raw_PNG_count':9,'comparisons':summary['comparisons']},indent=2))


if __name__=='__main__':
    main()
