"""Collect original UE PNGs and receipts; never synthesize or edit a render."""
import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
INV = REPO / 'investigation'
CAP = REPO / 'unreal/Saved/XinyiLook/unreal/material_ab_captures'
OUT = REPO / 'docs/evidence/xinyi-material-ue58-round1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def latest(stage):
    candidates = [p for p in INV.glob(stage + '-*.report.json')
                  if re.fullmatch(re.escape(stage) + r'-\d{8}T\d{6}Z\.report\.json', p.name)]
    if not candidates:
        raise RuntimeError('No successful process receipt: ' + stage)
    return sorted(candidates)[-1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy(path, relative):
    dest = OUT / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    if sha(path) != sha(dest):
        raise RuntimeError('Copy hash mismatch')


def main():
    before, after = load(latest('baseline')), load(latest('candidate'))
    a, b = load(CAP / 'baseline/metadata.json'), load(CAP / 'candidate/metadata.json')
    for r in (before, after):
        if r['status'] != 'PASS_LOOK_CAPTURE' or not r['reopen_ok'] or r['level_saved']:
            raise RuntimeError('Capture did not pass')
    for key in ('resolution', 'time_of_day', 'clouds', 'camera_specs', 'requested_console_settings',
                'observed_console_settings', 'look_level_sha256', 'baseline_city_material_sha256'):
        if a[key] != b[key]:
            raise RuntimeError('A/B mismatch: ' + key)
    if a['transient_material_overrides'] or len(b['transient_material_overrides']) != 25:
        raise RuntimeError('Unexpected material override scope')
    immutable = load(INV / 'source-immutability.json')
    if immutable['status'] != 'PASS_SOURCE_IMMUTABILITY':
        raise RuntimeError('Protected source changed')
    build = load(REPO / 'unreal/Saved/XinyiLook/unreal/material_ab_build.report.json')
    if build['status'] != 'PASS_MATERIAL_AB_BUILD':
        raise RuntimeError('Material build receipt is not PASS')
    summary = {'status': 'PASS_WINDOWS_UE58_MATERIAL_AB', 'screenshots': [],
        'matched_settings': a, 'material_build': build, 'performance': {},
        'source_immutability': immutable, 'artistic_acceptance': 'PENDING',
        'mobile_validation': False, 'continuous_motion_flicker_validation': False}
    names_a = {c['name']: c for c in before['captures']}
    names_b = {c['name']: c for c in after['captures']}
    if names_a.keys() != names_b.keys() or len(names_a) != 7:
        raise RuntimeError('Expected seven matching A/B poses')
    for name in names_a:
        arrays = []
        records = {}
        for variant, captures in (('baseline', names_a), ('candidate', names_b)):
            path = Path(captures[name]['path'])
            if not path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError('Not an original PNG')
            with Image.open(path) as im:
                if im.size != (1920, 1080):
                    raise RuntimeError('Unexpected render dimensions')
                arr = np.asarray(im.convert('RGB'), dtype=np.int16)
            if arr.std() < 3:
                raise RuntimeError('Empty/flat render')
            arrays.append(arr)
            records[variant] = {'sha256': sha(path), 'bytes': path.stat().st_size}
            copy(path, f'captures/{variant}/{path.name}')
        difference = np.abs(arrays[1] - arrays[0])
        if name.startswith(('walkup', 'huaxia')) and float((difference.max(axis=2) > 1).mean()) < 0.001:
            raise RuntimeError('No visible facade material difference: ' + name)
        summary['screenshots'].append({'name': name, **records,
            'mean_abs_rgb_255': round(float(difference.mean()), 4),
            'pixels_changed_over_1_percent': round(float((difference.max(axis=2) > 1).mean() * 100), 3)})
    for name, baseline in before['perf']['shots'].items():
        candidate = after['perf']['shots'][name]
        summary['performance'][name] = {'baseline': baseline, 'candidate': candidate,
            'median_delta_ms': round(candidate['median_ms'] - baseline['median_ms'], 3),
            'median_delta_percent': round((candidate['median_ms'] / baseline['median_ms'] - 1) * 100, 2)}
    summary['performance_method'] = before['perf']['method']
    summary['material_statistics_limit'] = 'Custom-node texture operations are not reflected reliably in num_pixel_texture_samples; do not interpret its zero as zero texture fetches.'
    summary['limits'] = [
        'Windows SceneCapture synchronised wall-time proxy; includes CPU/submit/readback overhead.',
        'One final A/B batch, 40 samples per view; no significance or FPS claim.',
        'Five translated stills cover 24 m; continuous flight and temporal flicker are not certified.',
        'ASTC, mobile device, Cook and packaged gameplay performance are untested.',
        '32 m repeat, directional rain and contrast remain subject to artistic review.'
    ]
    for variant in ('baseline', 'candidate'):
        copy(CAP / variant / 'metadata.json', f'captures/{variant}/metadata.json')
    smoke = load(latest('smoke'))
    copy(Path(smoke['captures'][0]['path']), 'captures/baseline-smoke.png')
    for stage in ('assets', 'level', 'smoke', 'baseline', 'candidate-build', 'candidate'):
        copy(latest(stage), f'receipts/{stage}.json')
    for file in ('contract-dependency-probe.json', 'texture-recovery.json', 'staged-inputs.json',
                 'source-immutability.json', 'host-before-candidate-capture.json',
                 'candidate-build-shutdown-failure.json', 'candidate-build-shutdown-failed.report.json',
                 'texture-recovery.attempt1.json', 'python-environment.json'):
        if (INV / file).is_file():
            copy(INV / file, 'receipts/' + file)
    # Keep useful UE log evidence, excluding unrelated service/account output.
    for log in sorted(INV.glob('*.log')):
        lines = log.read_text(encoding='utf-8', errors='replace').splitlines()
        selected = [line.rstrip() for line in lines if any(key in line for key in (
            'Command Line:', 'LogD3D12RHI:', 'XINYI_LOOK_REPORT', 'XINYI_MATERIAL_AB_BUILD',
            'XINYI_MATERIAL_CONTRACT_PROBE', 'Failed to compile Material',
            'ModeManagerInteractiveToolsContext', 'Fatal error:', 'LogExit: Exiting.',
            'LogPython: Error:', 'LogTexture: Display: Building texture TwoD: /Game/XinyiMaterialAB/'))]
        path = OUT / 'logs' / log.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(selected) + '\n', encoding='utf-8')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': summary['status'], 'pairs': len(names_a), 'performance': summary['performance']}, indent=2))


if __name__ == '__main__':
    main()
