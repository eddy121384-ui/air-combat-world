"""Validate host-attested packaged A/B runs for the Xinyi Complex-As-Simple candidate."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import statistics
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, fraction):
    values=sorted(values)
    if not values:return 0.0
    pos=fraction*(len(values)-1);lo=int(pos);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)


def load_run(run: Path, mode: str):
    slug=mode.lower()
    raw_path=run/f'30-complex-{slug}.raw.json'
    host_path=run/f'31-complex-{slug}-host.json'
    log_path=run/f'30-complex-{slug}.log'
    raw=json.loads(raw_path.read_text(encoding='utf-8-sig'))
    host=json.loads(host_path.read_text(encoding='utf-8-sig'))
    if host['raw_sha256']!=sha(raw_path) or host['log_sha256']!=sha(log_path):
        raise ValueError(f'{mode} host hash mismatch')
    if host['mode']!=mode or raw['mode']!=mode or host['process_id']!=str(raw['process_id']):
        raise ValueError(f'{mode} process identity mismatch')
    if host['timed_out'] or host['exit_code']!=0 or raw['status']!='ENGINE_COMPLEX_CANDIDATE_COMPLETE':
        raise ValueError(f'{mode} runtime did not complete')
    return raw,host,log_path


def summarize(raw,host,log_path):
    queries=[q for step in raw['steps'] for q in step['building_queries']]
    positives=[q for q in queries if q['expect_hit']]
    negatives=[q for q in queries if not q['expect_hit']]
    pos_fail=[q['id'] for q in positives if not(q['hit'] and q.get('building_tile')==q['expected_tile'])]
    neg_block=[q['id'] for q in negatives if q['hit']]
    sweeps=[(q['id'],s) for q in queries for s in q['sweeps']]
    sweep_rows=[{'sample':qid,**s} for qid,s in sweeps]
    timings=[q['benchmark_average_us'] for q in queries]
    policies=raw['building_policy']
    log=log_path.read_text(encoding='utf-8-sig',errors='replace')
    warnings=[line for line in log.splitlines() if re.search(r'(?:Error:|Warning:|Fatal error|Missing package|Failed to load)',line,re.I)]
    dynamic=raw['dynamic_simulation']
    return {
        'process_id':raw['process_id'],'launch_id':host['launch_id'],
        'executable_sha256':host['executable_sha256'],'elapsed_seconds':host['elapsed_seconds'],
        'plan_step_count':len(raw['steps']),'all_streaming_complete':all(s['streaming_completed'] for s in raw['steps']),
        'audited_tile_count':raw['audited_tile_count'],
        'original_trace_flag_counts':counts(p['original_trace_flag_enum'] for p in policies),
        'effective_trace_flag_counts':counts(p['effective_trace_flag_enum'] for p in policies),
        'physics_state_recreated_component_count':raw['physics_state_recreated_component_count'],
        'body_resource_bytes_total':sum(p['body_resource_bytes'] for p in policies),
        'convex_primitive_count':sum(p['convex_count'] for p in policies),
        'positive_count':len(positives),
        'positive_building_hit_count':sum(1 for q in positives if q['hit']),
        'positive_expected_tile_match_count':sum(1 for q in positives if q['hit'] and q.get('building_tile')==q['expected_tile']),
        'positive_requires_expected_tile_identity':True,'positive_failures':pos_fail,
        'negative_count':len(negatives),'negative_blocked_count':len(neg_block),'negative_blocked_ids':neg_block,
        'sweeps':sweep_rows,'dynamic_simulation':dynamic,
        'query_timing_us':{'sample_count':len(timings),'repetitions_per_sample':raw['query_repetitions'],
            'median_average':statistics.median(timings),'p95_average':percentile(timings,.95),'max_average':max(timings)},
        'frame_time_ms':raw['frame_time'],'max_streaming_wait_ms':raw['max_streaming_wait_ms'],
        'runtime_peak_process_memory_bytes':raw['peak_process_memory_bytes'],
        'host_peak_working_set_bytes':host['peak_working_set_bytes'],'host_peak_private_bytes':host['peak_private_bytes'],
        'host_memory_sample_count':host['memory_sample_count'],
        'package_total_bytes':host['package_total_bytes'],'pak_bytes':host['pak_bytes'],
        'runtime_diagnostic_line_count':len(warnings),'runtime_diagnostic_lines':[x[:400] for x in warnings[:25]],
    }


def counts(values):
    result={}
    for value in values:result[str(value)]=result.get(str(value),0)+1
    return result


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--run-root',type=Path,required=True)
    ap.add_argument('--plan-name',default='10-collision-plan.json')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();run=args.run_root.resolve();plan_path=run/args.plan_name
    plan=json.loads(plan_path.read_text(encoding='utf-8-sig'))
    baseline_raw,baseline_host,baseline_log=load_run(run,'Baseline')
    candidate_raw,candidate_host,candidate_log=load_run(run,'ComplexAsSimple')
    for raw,host in [(baseline_raw,baseline_host),(candidate_raw,candidate_host)]:
        if raw['run_id']!=run.name or host['run_id']!=run.name or host['plan_sha256']!=sha(plan_path):
            raise ValueError('Run/plan provenance mismatch')
        if raw['primary_trace_complex'] is not False or len(raw['steps'])!=101:
            raise ValueError('Candidate must use normal/simple queries over exact corpus')
        if [x['id'] for x in raw['steps']] != [x['id'] for x in plan['steps']]:
            raise ValueError('Plan order mismatch')
    if baseline_host['executable_sha256']!=candidate_host['executable_sha256']:
        raise ValueError('A/B executable mismatch')

    repo=run.parents[3]
    source=repo/'unreal/Saved/XinyiUnrealV2Inputs/run-35822928983/unreal/Saved/XinyiUnrealV2Contract'
    contract_path=source/'xinyi_unreal_v2_contract.json'
    contract=json.loads(contract_path.read_text(encoding='utf-8'))
    placement=source/contract['outputs']['building_component_placement']['path']
    if sha(contract_path)!=plan['sources']['contract_sha256'] or sha(placement)!=plan['sources']['placement_sha256']:
        raise ValueError('Accepted source hash mismatch')
    with gzip.open(placement,'rt',encoding='utf-8') as f:
        header=json.loads(next(f))['header'];boxes=[json.loads(line) for line in f]
    if len(boxes)!=header['count'] or len(boxes)!=11130:raise ValueError('Placement count mismatch')
    certified=0
    for step in plan['steps']:
        for sample in step['building_samples']:
            if sample['expect_hit']:continue
            cert=sample['certificate'];margin=cert['minimum_aabb_clearance_cm'];x,y=sample['start_cm'][:2]
            if cert['manifest_sha256']!=sha(placement) or cert['global_component_count']!=len(boxes) or margin<500:
                raise ValueError(f'Invalid negative certificate {sample["id"]}')
            for box in boxes:
                lo,hi=box['expected_ue_bounds_min_cm'],box['expected_ue_bounds_max_cm']
                if lo[0]-margin<=x<=hi[0]+margin and lo[1]-margin<=y<=hi[1]+margin:
                    raise ValueError(f'Negative sample not empty {sample["id"]}')
            certified+=1
    if certified!=27:raise ValueError(f'Expected 27 certified negatives, got {certified}')

    baseline=summarize(baseline_raw,baseline_host,baseline_log)
    candidate=summarize(candidate_raw,candidate_host,candidate_log)
    expected_sweeps={('low_rise_wall','sphere_r50_cm'):True,
                     ('high_rise_wall','box_50_50_100_cm'):True,
                     ('gap_between_buildings_+000_+000','sphere_r50_cm'):False,
                     ('gap_between_buildings_+000_+000','box_50_50_100_cm'):False}
    observed={(x['sample'],x['shape']):x['hit'] for x in candidate['sweeps']}
    sweep_fail=[{'sample':k[0],'shape':k[1],'expected_hit':v,'actual_hit':observed.get(k)}
                for k,v in expected_sweeps.items() if observed.get(k)!=v]
    dynamic=candidate['dynamic_simulation']
    dynamic_pass=(dynamic['simulate_physics'] and dynamic['blocking_hit_observed'] and
                  dynamic['hit_tile']==dynamic['expected_tile'])
    candidate_correct=(candidate['positive_count']==15 and not candidate['positive_failures'] and
                       candidate['negative_count']==27 and candidate['negative_blocked_count']==0 and
                       not sweep_fail and dynamic_pass and candidate['audited_tile_count']==25 and
                       candidate['effective_trace_flag_counts']=={'3':25} and
                       candidate['all_streaming_complete'])
    ratios={
        'median_query_time':candidate['query_timing_us']['median_average']/max(baseline['query_timing_us']['median_average'],1e-9),
        'p95_query_time':candidate['query_timing_us']['p95_average']/max(baseline['query_timing_us']['p95_average'],1e-9),
        'frame_p95':candidate['frame_time_ms']['p95_ms']/max(baseline['frame_time_ms']['p95_ms'],1e-9),
        'frame_p99':candidate['frame_time_ms']['p99_ms']/max(baseline['frame_time_ms']['p99_ms'],1e-9),
        'peak_working_set':candidate['host_peak_working_set_bytes']/max(baseline['host_peak_working_set_bytes'],1),
        'peak_private':candidate['host_peak_private_bytes']/max(baseline['host_peak_private_bytes'],1),
        'streaming_wait':candidate['max_streaming_wait_ms']/max(baseline['max_streaming_wait_ms'],1e-9),
    }
    result={'schema':'xinyi-complex-as-simple-gate/v1','run_id':run.name,'status':'MEASURED',
            'candidate_correctness':'PASS' if candidate_correct else 'FAIL',
            'certified_negative_count':certified,'sweep_failures':sweep_fail,
            'dynamic_simulation_pass':dynamic_pass,'same_executable':True,
            'baseline':baseline,'candidate':candidate,'candidate_over_baseline_ratios':ratios,
            'performance_decision':'REQUIRES_EVIDENCE_INTERPRETATION',
            'verdict':'CORRECTNESS_PASS_PERFORMANCE_PENDING' if candidate_correct else 'FAIL'}
    with args.out.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({'run_id':run.name,'candidate_correctness':result['candidate_correctness'],
                      'positive_failures':candidate['positive_failures'],
                      'negative_blocked':candidate['negative_blocked_count'],
                      'sweep_failures':sweep_fail,'dynamic_pass':dynamic_pass,
                      'ratios':ratios,'receipt':str(args.out)}))


if __name__=='__main__':main()
