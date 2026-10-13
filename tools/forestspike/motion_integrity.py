"""Verify every world-view frame against registered B0.1 warm/V3/end holds."""
import csv
import json
import math
from pathlib import Path
from perf_integrity import read_csv, sha256


def expected(spec, frame):
    poses = spec['path']['poses']
    elapsed = max(0, min(spec['flight_intervals'], frame - spec['warm_frames']))
    segment = min(len(poses) - 2, elapsed // 120)
    alpha = (elapsed - segment * 120) / 120
    a, b = poses[segment], poses[segment + 1]
    enu = [a['eye_enu'][k] * (1-alpha) + b['eye_enu'][k] * alpha for k in range(3)]
    xyz = [enu[0]*100, -enu[1]*100, enu[2]*100]
    pitch = math.radians(a['pitch_deg'] * (1-alpha) + b['pitch_deg'] * alpha)
    yaw = math.radians(a['heading_deg'] - 90)
    forward = [math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)]
    up = [-math.sin(pitch)*math.cos(yaw), -math.sin(pitch)*math.sin(yaw), math.cos(pitch)]
    phase = 'warm_hold' if frame < spec['warm_frames'] else ('flight' if frame <= spec['warm_frames'] + spec['flight_intervals'] else 'endpoint_hold')
    return xyz, forward, up, phase, int(segment), 14 + elapsed / spec['fps']


def angle(a, b):
    na, nb = math.sqrt(sum(x*x for x in a)), math.sqrt(sum(x*x for x in b))
    if not na or not nb:
        return 180.0
    return math.degrees(math.acos(max(-1, min(1, sum(x*y for x,y in zip(a,b))/(na*nb)))))


def verify(csv_path, spec):
    errors = []
    report = {'status': 'FAIL_FS_B01_MOTION', 'csv_sha256': sha256(csv_path), 'errors': errors,
              'host_scope': 'Intel UHD 770 only', 'scope': 'camera motion integrity; GPU data diagnostic only'}
    try:
        data = read_csv(csv_path)
    except (ValueError, KeyError) as exc:
        errors.append('invalid camera CSV: ' + str(exc))
        return report, []
    cols = data['columns']
    vectors = {name: [[cols['View/' + name + k][i] for k in 'XYZ'] for i in range(data['frames'])]
               for name in ('Pos', 'Forward', 'Up')}
    pos = vectors['Pos']
    boot = next((i for i, p in enumerate(pos) if math.dist(p, [0,0,0]) > 1), len(pos))
    tol = spec['motion_tolerances']
    if boot > tol['boot_frames_max']:
        errors.append('too many invalid boot/no-view frames')
    if any(math.dist(p, [0,0,0]) < 1 for p in pos[boot:]):
        errors.append('invalid no-view frame after world start')
    offsets = tol['first_valid_sequence_frame_allowed']
    # Registered 0/1-frame startup phase only; cannot fit arbitrary speed/path.
    offset = min(offsets, key=lambda off: max(math.dist(p, expected(spec, i+off)[0]) for i,p in enumerate(pos[boot:])))
    rows = []
    warm = pos[boot:boot+spec['warm_frames']]
    warm_delta = max((math.dist(p, expected(spec, 0)[0])/100 for p in warm), default=float('inf'))
    if len(warm) != spec['warm_frames'] or warm_delta > tol['warm_displacement_m']:
        errors.append('first 120 valid world-view samples did not hold still at the starting pose')
    for i, p in enumerate(pos):
        frame = i - boot + offset
        if i < boot:
            rows.append({'csv_frame': i, 'sequence_frame': '', 'phase': 'invalid_boot', 'segment': '', 'path_t_s': '',
                         'x_cm': p[0], 'y_cm': p[1], 'z_cm': p[2], 'position_error_m': '', 'forward_error_deg': '', 'up_error_deg': ''})
            continue
        xyz, forward, up, phase, segment, t = expected(spec, frame)
        rows.append({'csv_frame': i, 'sequence_frame': frame, 'phase': phase, 'segment': segment if phase == 'flight' else '',
                     'path_t_s': t, 'x_cm': p[0], 'y_cm': p[1], 'z_cm': p[2], 'position_error_m': math.dist(p, xyz)/100,
                     'forward_error_deg': angle(vectors['Forward'][i], forward), 'up_error_deg': angle(vectors['Up'][i], up)})
    cumulative = 0.0
    for i, row in enumerate(rows):
        for name in ('Forward', 'Up'):
            row.update({name.lower() + '_' + k.lower(): v for k,v in zip('XYZ',vectors[name][i])})
        step = math.dist(pos[i-1],pos[i])/100 if i > boot else 0.0
        row['step_distance_m'] = step
        if row['phase'] == 'flight' and row['sequence_frame'] > spec['warm_frames']:
            cumulative += step
        row['cumulative_flight_distance_m'] = cumulative
    valid = rows[boot:]
    maxima = {k: max((r[k] for r in valid), default=float('inf')) for k in ('position_error_m','forward_error_deg','up_error_deg')}
    if maxima['position_error_m'] > tol['position_m']:
        errors.append('per-frame position differs from registered fixed-rate trajectory')
    if max(maxima['forward_error_deg'], maxima['up_error_deg']) > tol['orientation_deg']:
        errors.append('per-frame orientation differs from registered trajectory')
    flight = [r for r in valid if r['phase'] == 'flight']
    if len(flight) != spec['flight_intervals']+1 or flight[0]['path_t_s'] != 14 or flight[-1]['path_t_s'] != 32:
        errors.append('complete 18s flight with both endpoints was not captured')
    endpoint = spec['warm_frames'] + spec['flight_intervals']
    path_pos = [pos[r['csv_frame']] for r in flight]
    distance = sum(math.dist(a,b) for a,b in zip(path_pos,path_pos[1:])) / 100
    expected_path = [expected(spec, i)[0] for i in range(spec['warm_frames'], endpoint+1)]
    expected_distance = sum(math.dist(a,b) for a,b in zip(expected_path,expected_path[1:]))/100
    nonmonotonic = sum(b[0] <= a[0] or b[1] >= a[1] for a,b in zip(path_pos,path_pos[1:]))
    if distance < 500 or abs(distance-expected_distance) > 0.1 or nonmonotonic:
        errors.append('travel distance or monotonic inbound motion invalid')
    report.update({'frames':data['frames'],'invalid_boot_frames':boot,'first_valid_sequence_frame':offset,
                   'first_120_valid_world_view_max_displacement_m':warm_delta, 'flight_samples':len(flight),
                   'verified_flight_seconds':18.0 if len(flight)==1081 and not errors else None,
                   'flight_csv_range':[flight[0]['csv_frame'],flight[-1]['csv_frame']] if flight else [],
                   'measured_distance_m':distance,'registered_distance_m':expected_distance,
                   'nonmonotonic_steps':nonmonotonic,'max_errors':maxima})
    report['flight_endpoint_error_m'] = math.dist(path_pos[-1], expected(spec, endpoint)[0])/100 if path_pos else None
    report['endpoint_hold_samples'] = sum(r['phase']=='endpoint_hold' for r in valid)
    if not errors:
        report['status'] = 'PASS_FS_B01_MOTION'
    return report, rows


def main():
    import argparse
    p=argparse.ArgumentParser()
    for name in ('csv','spec','trace','receipt'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    report,rows=verify(a.csv,json.loads(a.spec.read_text(encoding='utf-8')))
    with a.trace.open('x',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['csv_frame','phase']);w.writeheader();w.writerows(rows)
    with a.receipt.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(report['status'], report['errors'])
    raise SystemExit(0 if report['status']=='PASS_FS_B01_MOTION' else 2)


if __name__=='__main__':main()
