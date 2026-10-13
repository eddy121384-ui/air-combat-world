"""Lossy review copies; native PNG sequences remain the quantitative originals."""
import json,subprocess,hashlib,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[3];raw=r/'unreal/ForestSpike/Saved/ForestSpike/b1a'
out=raw/'review_media';out.mkdir(exist_ok=False)
ffmpeg=shutil.which('ffmpeg');assert ffmpeg
rows=[]
for path,start,count in [('V3',720,361),('V5',120,281)]:
 patterns=[]
 for group in ['A0','A1','B0','B1']:
  tag=f'native_{group}_V3_03' if path=='V3' else f'clip_{group}_V5_01'
  d=raw/'movies'/tag;v=json.loads((d/'validated.json').read_text());assert v['status']=='PASS_FS_B1A_NATIVE_MOVIE'
  framefiles=list((d/'frames').rglob(f'frame_{start:04d}.png'));assert len(framefiles)==1
  pattern=framefiles[0].parent/'frame_%04d.png';target=out/f'{path}_{group}_1080p60_review.mp4'
  patterns.append(pattern)
  args=[ffmpeg,'-hide_banner','-loglevel','warning','-n','-framerate','60','-start_number',str(start),'-i',str(pattern),'-frames:v',str(count),'-an','-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
  subprocess.run(args,check=True)
  probe=subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(target)]);s=json.loads(probe)['streams'][0]
  assert (s['width'],s['height'],int(s['nb_frames']))==(1920,1080,count)
  rows.append({'path':path,'group':group,'file':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'source_validation':str(d/'validated.json'),'start_frame':start,'end_frame_inclusive':start+count-1,'frames':count,'trajectory_seconds':(count-1)/60,'encoded_duration_seconds':float(s['duration']),'resolution':[1920,1080],'fps':s['r_frame_rate'],'scope':'Lossy CRF18 H.264 review copy, no rescaling. Quantitative image metrics use native PNGs.','command':args})
 target=out/f'{path}_four_arm_4k60_review.mp4'
 args=[ffmpeg,'-hide_banner','-loglevel','warning','-n']
 for pattern in patterns:args+=['-framerate','60','-start_number',str(start),'-i',str(pattern)]
 args+=['-filter_complex','[0:v][1:v][2:v][3:v]xstack=inputs=4:layout=0_0|1920_0|0_1080|1920_1080[v]','-map','[v]','-frames:v',str(count),'-an','-c:v','libx264','-threads','4','-preset','slow','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
 subprocess.run(args,check=True)
 s=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(target)]))['streams'][0]
 assert (s['width'],s['height'],int(s['nb_frames']))==(3840,2160,count)
 rows.append({'path':path,'group':'four-arm','file':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'start_frame':start,'end_frame_inclusive':start+count-1,'frames':count,'resolution':[3840,2160],'scope':'Lossy CRF18 4K review grid built directly from PNGs without rescaling. Each quadrant retains 1920x1080. Layout: A0 A1 / B0 B1.','command':args})
with (out/'encoding.json').open('x') as f:json.dump(rows,f,indent=2)
print('Eight matched 1080p + two 4K review clips encoded and probed')
