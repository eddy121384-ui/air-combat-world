"""Render audit tables directly from validated run-grain JSON, no hand transcription."""
import json,csv
from pathlib import Path
r=Path(__file__).resolve().parents[3];base=r/'unreal/ForestSpike/Saved/ForestSpike/b1a/analysis'
s=json.loads((base/'static.json').read_text());v=json.loads((base/'visual.json').read_text());lod=json.loads((base/'runtime_lods.json').read_text())
native=json.loads((base/'native_static.json').read_text())
def write_csv(name,rows):
 with (base/name).open('x',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
arms=[];pairs=[]
for a in s['arms']:
 for metric in ['GPUTime','CPUThreadMax']:
  for quantile,spread in a['metrics'][metric].items():
   arms.append({'host':'Intel UHD 770 only','agl_m':a['agl_m'],'view':a['view'],'group':a['group'],'metric':metric,'quantile':quantile,**spread})
for a in s['paired_contrasts']:
 for metric in ['GPUTime','CPUThreadMax']:
  for quantile,sp in a['metrics'][metric].items():
   pairs.append({'host':'Intel UHD 770 only','agl_m':a['agl_m'],'view':a['view'],'contrast':a['contrast'],'metric':metric,'quantile':quantile,'n_rounds':sp['n'],'median_delta_ms':sp['median'],'mean_delta_ms':sp['mean'],'sample_sd_ms':sp['sample_sd'],'ci_low_ms':sp['mean_difference_t95_ci_ms'][0],'ci_high_ms':sp['mean_difference_t95_ci_ms'][1],'positive_rounds':sp['positive_rounds'],'negative_rounds':sp['negative_rounds']})
if not (base/'arms.csv').exists():write_csv('arms.csv',arms)
if not (base/'paired.csv').exists():write_csv('paired.csv',pairs)
f11=[]
for a in native['F11_static']:
 for mask,stats in a['metrics'].items():f11.append({'host':'Intel UHD 770 only','pose':a['pose'],'group':a['group'],'mask':mask,'frames':a['frames'],**stats})
write_csv('f11-native.csv',f11)
def num(x):return f'{x:.3f}'
def ms(m):return num(m['median'])+' ± '+num(m['sample_sd'])
lines=['## 靜態效能：Intel UHD 770 only','','單位 ms；每格為五輪 run quantile 的中位數 ± 跨輪 sample SD。p95 欄是五個 run p95 的中位數，並非 pooled-frame p95。CPU 為逐幀 max(GT, RT, RHI)，包含等待。','','| AGL | 組別 | GPU median ± SD | GPU p95 ± SD | CPU median ± SD | CPU p95 ± SD | GPU median CV |','|---:|---|---:|---:|---:|---:|---:|']
for a in s['arms']:
 g=a['metrics']['GPUTime'];c=a['metrics']['CPUThreadMax']
 lines.append(f"| {a['agl_m']}m | {a['group']} | {ms(g['median_ms'])} | {ms(g['p95_ms'])} | {ms(c['median_ms'])} | {ms(c['p95_ms'])} | {g['median_ms']['cv_percent']:.1f}% |")
lines+=['','500／1000m 的四組值僅提供 S 配對所需上下文，不可解讀為 A/B 樹木比較。所有 metric、各輪數值、CV、range 見 JSON／CSV。','','## 配對差異：Intel UHD 770 only','','正值表示新增成本。S_A=A1−A0，S_B=B1−B0，N_Soff=B0−A0，N_Son=B1−A1；主效應取兩個同類差值平均，interaction=(B1−B0)−(A1−A0)。以下差值在同輪同視角計算後彙整；95% CI 是 n=5、df=4 的 paired mean t interval，不能證明等價。','','| AGL | 對比 | GPU median Δ mean [95% CI] | GPU median Δ 中位數 / SD | GPU p95 Δ mean / SD | CPU median Δ mean [95% CI] | CPU p95 Δ mean / SD |','|---:|---|---:|---:|---:|---:|---:|']
for a in s['paired_contrasts']:
 g=a['metrics']['GPUTime'];c=a['metrics']['CPUThreadMax']
 def ci(z):return f"{num(z['mean'])} [{num(z['mean_difference_t95_ci_ms'][0])}, {num(z['mean_difference_t95_ci_ms'][1])}]"
 def mean_sd(z):return num(z['mean'])+' / '+num(z['sample_sd'])
 lines.append(f"| {a['agl_m']}m | {a['contrast']} | {ci(g['median_ms'])} | {num(g['median_ms']['median'])} / {num(g['median_ms']['sample_sd'])} | {mean_sd(g['p95_ms'])} | {ci(c['median_ms'])} | {mean_sd(c['p95_ms'])} |")
lines+=['','## 實際可見像素與 LOD attribution','','ID 為無 AA 的診斷 pass；下表不是每一個 instance 的可見性。樹冠可能跨核心邊界，projected-core 定義包含其樹像素。','','| 視角 | 樹組 | 核心投影占整幀 | 樹像素 | 樹像素／核心投影 |','|---|---|---:|---:|---:|']
for a in v['rows']:
 if a['kind']=='id':lines.append(f"| {a['pose']['id']} | {a['group'][0]} | {100*a['core_fraction_frame']:.2f}% | {a['tree_pixels']} | {100*a['tree_fraction_projected_core']:.2f}% |")
lines+=['','下表是獨立 normal-game 的一次 primary render snapshot（shadow:0），非 480 幀完整分布；相機在同次 240 個 valid CSV samples 保持固定。空日誌保留為未觀測，不當作量測零。','','| 視角 | 樹組 | LOD0 / 1 / 2 submitted instances | LOD0 / 1 / 2 triangles |','|---|---|---|---|']
for a in lod['rows']:lines.append(f"| {a['view']} | {a['group'][0]} | {a['submitted_instances_by_lod']} | {a['submitted_triangles_by_lod']} |")
lines+=['','## F11 locked-camera 原生診斷：Intel UHD 770 only','','每組每靜態視角 120 fixed native MRQ output frames 暖機後，取 frame120..183 共64個連續原生幀。值為 display-referred D65 sRGB L* 的 per-pixel population σ，再取森林遮罩 p95。數值門檻仍待校準；S-off 遠景森林缺席，低變動不可當作更佳森林畫質。SceneCapture temporal 值保留在原分析，非此主要結果。','','| 視角 | 組別 | 所有 potential forest p95 σ L* | 3D 樹 p95 σ L* | 遠景 potential forest p95 σ L* |','|---|---|---:|---:|---:|']
for a in native['F11_static']:
 def value(mask):return num(a['metrics'][mask]['p95_sigma_Lstar']) if mask in a['metrics'] else '—'
 lines.append(f"| {a['pose']} | {a['group']} | {value('all_potential_forest')} | {value('tree_geometry')} | {value('far_potential_forest')} |")
lines+=['','## 同鏡頭原生影像變化量','','單位 L* MAE；這是變化大小，不是畫質改善分數，不將像素差值當作主觀效益排名。','','| AGL | 對比 | 全幀 | 核心投影 | Potential forest |','|---:|---|---:|---:|---:|']
for a in native['matched_image_changes']:
 for name,z in a['changes'].items():lines.append(f"| {a['agl_m']}m | {name} | {num(z['whole_frame_Lstar_MAE'])} | {num(z['projected_core_Lstar_MAE'])} | {num(z['potential_forest_Lstar_MAE'])} |")
with (base/'tables-native.md').open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
print('Validated JSON → reproducible CSV and Markdown tables')
