"""Validate a packaged Xinyi collision run and emit a path-free gate receipt."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-root',type=Path,required=True)
    ap.add_argument('--run-index',type=int,default=1)
    ap.add_argument('--plan-name',default='10-collision-plan.json')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    run=args.run_root.resolve()
    raw_path=run/f'30-collision-{args.run_index}.raw.json'
    host_path=run/f'31-collision-{args.run_index}-host.json'
    log_path=run/f'30-collision-{args.run_index}.log'
    plan_path=run/args.plan_name
    raw=json.loads(raw_path.read_text(encoding='utf-8-sig'))
    host=json.loads(host_path.read_text(encoding='utf-8-sig'))
    plan=json.loads(plan_path.read_text(encoding='utf-8-sig'))
    if host['raw_sha256']!=digest(raw_path) or host['plan_sha256']!=digest(plan_path) or host['log_sha256']!=digest(log_path):
        raise ValueError('Host hash attestation mismatch')
    if raw['run_id']!=host['run_id'] or raw['run_id'] not in run.name or host['timed_out'] or host['exit_code']!=0:
        raise ValueError('Host/runtime identity or process exit mismatch')
    if raw['status']!='ENGINE_COLLISION_ROUTE_COMPLETE' or len(raw['steps'])!=len(plan['steps']):
        raise ValueError(f'Runtime route incomplete: {raw["status"]}, {len(raw["steps"])} steps')
    if raw.get('primary_trace_complex') is not False or raw.get('reference_trace_complex') is not True:
        raise ValueError('Query complexity is not explicitly attested; simple collision cannot be certified')
    if [s['id'] for s in raw['steps']] != [s['id'] for s in plan['steps']]:
        raise ValueError('Runtime plan order mismatch')
    # Independently re-check the negative-space certificates against the accepted
    # placement manifest. A result from an empty point is only meaningful if the
    # point is actually outside *all* source building bounds.
    repo=run.parents[3]
    source=repo/'unreal/Saved/XinyiUnrealV2Inputs/run-35822928983/unreal/Saved/XinyiUnrealV2Contract'
    contract_path=source/'xinyi_unreal_v2_contract.json'
    if digest(contract_path)!=plan['sources']['contract_sha256']:
        raise ValueError('Accepted contract hash mismatch')
    contract=json.loads(contract_path.read_text(encoding='utf-8'))
    heightmap_path=source/contract['outputs']['heightmap_r16']['path']
    placement_path=source/contract['outputs']['building_component_placement']['path']
    if digest(heightmap_path)!=plan['sources']['heightmap_sha256'] or digest(placement_path)!=plan['sources']['placement_sha256']:
        raise ValueError('Accepted heightfield or placement hash mismatch')
    with gzip.open(placement_path,'rt',encoding='utf-8') as f:
        header=json.loads(next(f))['header']
        boxes=[json.loads(line) for line in f]
    if len(boxes)!=header['count'] or len(boxes)!=11130:
        raise ValueError('Accepted placement row count mismatch')
    verified_negative=0
    for step in plan['steps']:
        for sample in step['building_samples']:
            if sample['expect_hit']: continue
            cert=sample['certificate']
            margin=cert['minimum_aabb_clearance_cm']
            if (cert['basis']!='outside every accepted building component AABB' or
                    cert['manifest_sha256']!=plan['sources']['placement_sha256'] or
                    cert['global_component_count']!=len(boxes) or margin<500):
                raise ValueError(f'Invalid negative certificate: {sample["id"]}')
            x,y=sample['start_cm'][:2]
            if sample['end_cm'][:2]!=[x,y]:
                raise ValueError(f'Negative trace is not vertical: {sample["id"]}')
            for box in boxes:
                lo,hi=box['expected_ue_bounds_min_cm'],box['expected_ue_bounds_max_cm']
                if lo[0]-margin<=x<=hi[0]+margin and lo[1]-margin<=y<=hi[1]+margin:
                    raise ValueError(f'Negative sample lies within accepted AABB: {sample["id"]}')
            verified_negative+=1
    if not all(s['streaming_completed'] for s in raw['steps']):
        raise ValueError('Streaming incomplete during collision probe')
    terrain=[];building=[];ownership=[]
    for step in raw['steps']:
        terrain.extend(step['terrain_traces'])
        building.extend(step['building_traces'])
        ownership.extend(step['terrain_actors'])
    expected_terrain=sum(len(s['terrain_samples']) for s in plan['steps'])
    expected_building=sum(len(s['building_samples']) for s in plan['steps'])
    if len(terrain)!=expected_terrain or len(building)!=expected_building:
        raise ValueError('Probe count mismatch')
    if verified_negative!=sum(not x['expect_hit'] for s in plan['steps'] for x in s['building_samples']):
        raise ValueError('Negative certificate count mismatch')
    inside=[x for x in terrain if x['expect_hit']]
    outside=[x for x in terrain if not x['expect_hit']]
    tolerance=plan['terrain_tolerance_cm']
    terrain_misses=[x['id'] for x in inside if not (x['hit'] and x.get('is_landscape'))]
    terrain_error=[(x['id'],x.get('absolute_z_error_cm')) for x in inside if x.get('absolute_z_error_cm',float('inf'))>tolerance]
    outside_false=[x['id'] for x in outside if x['hit'] and x.get('is_landscape')]
    positives=[x for x in building if x['expect_hit']]
    negatives=[x for x in building if not x['expect_hit']]
    positive_fail=[{'id':x['id'],'expected_tile':x['expected_tile'],'hit_tile':x.get('building_tile',''),
                    'hit_actor_class':x.get('actor_class','')} for x in positives
                   if not (x['hit'] and x.get('building_tile')==x['expected_tile'])]
    negative_blocked=[{'id':x['id'],'tile':x.get('building_tile',''),
                       'actor_class':x.get('actor_class',''),
                       'hit_location_cm':x.get('location_cm',[])} for x in negatives if x['hit']]
    complex_negative_blocked=[x['id'] for x in negatives if x.get('complex_reference',{}).get('hit')]
    complex_positive_fail=[x['id'] for x in positives if not
                           (x.get('complex_reference',{}).get('hit') and
                            x['complex_reference'].get('building_tile')==x['expected_tile'])]
    policies=raw['building_policy']
    tiles={x['tile'] for x in policies}
    if len(tiles)!=25 or len(policies)!=25 or raw['audited_tile_count']!=25:
        raise ValueError(f'Incomplete packaged BodySetup inventory: {len(tiles)}')
    log=log_path.read_text(encoding='utf-8-sig',errors='replace')
    interesting=[line for line in log.splitlines()
                 if re.search(r'(?:Error:|Warning:|Fatal error|Missing package|Failed to load)',line,re.I)]
    warning_summary=Counter()
    for line in interesting:
        if 'Error:' in line or 'Fatal error' in line: warning_summary['errors']+=1
        elif 'Warning:' in line: warning_summary['warnings']+=1
    roots={x['actor'] for x in ownership if not x['is_proxy']}
    proxies={x['actor'] for x in ownership if x['is_proxy']}
    packages={x['package'] for x in ownership}
    collision_components={c['name'] for x in ownership for c in x['collision_components']}
    components_by_kind=Counter(x['kind'] for x in terrain)
    status_terrain='PASS' if not terrain_misses and not terrain_error and not outside_false and inside and outside else 'FAIL'
    status_building='PASS' if not positive_fail and not negative_blocked and len(positives)>=15 and len(negatives)>=25 else 'FAIL'
    # Do not describe UObject resource size as cooked collision bytes: the API does not expose that figure here.
    result={
        'schema':'xinyi-packaged-collision-gate/v1','run_id':host['run_id'],
        'status':'MEASURED','runtime_status':raw['status'],
        'host':{'run_index':host['run_index'],'launch_id':host['launch_id'],
                'executable_sha256':host['executable_sha256'],'raw_sha256':host['raw_sha256'],
                'plan_sha256':host['plan_sha256'],'log_sha256':host['log_sha256'],
                'elapsed_seconds':host['elapsed_seconds'],'exit_code':host['exit_code']},
        'world':raw['world'],'trace_channel':raw['trace_channel'],
        'primary_trace_complex':False,'reference_trace_complex':True,
        'streaming_step_count':len(raw['steps']),'all_steps_streaming_complete':True,
        'landscape':{'status':status_terrain,'sample_count':len(terrain),'inside_count':len(inside),
            'outside_count':len(outside),'sample_kinds':dict(components_by_kind),
            'tolerance_cm_predeclared':tolerance,
            'max_absolute_z_error_cm':max((x.get('absolute_z_error_cm',0) for x in inside),default=None),
            'in_bounds_misses':terrain_misses,'z_outliers':terrain_error,
            'out_of_bounds_false_hits':outside_false,
            'root_actor_count':len(roots),'proxy_actor_count_observed':len(proxies),
            'landscape_package_count_observed':len(packages),
            'collision_component_count_observed':len(collision_components),
            'root_actors':sorted(roots),'proxy_actors':sorted(proxies),
            'ownership_examples':ownership[:3]},
        'building':{'status':status_building,'policy_tile_count':len(policies),
            'trace_flag_counts':dict(Counter(str(x['trace_flag_enum']) for x in policies)),
            'visibility_response_counts':dict(Counter(str(x['visibility_response_enum']) for x in policies)),
            'collision_enabled_counts':dict(Counter(str(x['component_collision_enabled_enum']) for x in policies)),
            'simple_primitive_totals':{k:sum(x.get(k,0) for x in policies) for k in
                ('sphere_count','box_count','capsule_count','tapered_capsule_count','convex_count')},
            'body_resource_bytes_total':sum(x.get('body_resource_bytes',0) for x in policies),
            'mesh_resource_bytes_total':sum(x.get('mesh_resource_bytes',0) for x in policies),
            'cooked_collision_bytes':'not exposed by this packaged runtime API',
            'positive_count':len(positives),'positive_failures':positive_fail,
            'certified_negative_count':len(negatives),'negative_blocked_count':len(negative_blocked),
            'independently_verified_negative_certificate_count':verified_negative,
            'blocked_certified_negative_samples':negative_blocked,
            'complex_reference_negative_blocked_count':len(complex_negative_blocked),
            'complex_reference_positive_failures':complex_positive_fail,
            'policies':policies},
        'identity_isolation':{'terrain_requires_landscape_actor_and_heightfield_component':True,
            'terrain_queries_ignore_static_mesh_actors':True,
            'building_queries_ignore_landscape_actors':True,
            'building_positive_requires_expected_tile_identity':True},
        'log_diagnostics':{'error_count':warning_summary['errors'],'warning_count':warning_summary['warnings'],
            'selected_lines':[x[:400] for x in interesting[:25]]},
    }
    with args.out.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps({'run_id':host['run_id'],'landscape':status_terrain,'building':status_building,
                      'terrain_samples':len(terrain),'positive_count':len(positives),
                      'negative_count':len(negatives),'blocked_negatives':len(negative_blocked),
                      'receipt':str(args.out)}))


if __name__=='__main__': main()
