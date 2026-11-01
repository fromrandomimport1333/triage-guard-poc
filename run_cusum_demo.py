"""Deterministic synthetic arithmetic/fault replay. No camera performance metrics."""
import argparse,csv,json,platform,time
from dataclasses import asdict,replace
from pathlib import Path
from sequential_monitor import MonitorConfig,ScoreObservation,SequentialMonitor,ResetRequest
from cusum_integration import BehavioralReplay
from temporal_assurance import TemporalAssurance,demo_status_frame
from tests.test_temporal_assurance import obs,KEY

ROOT=Path(__file__).resolve().parent

def arithmetic_config():
    return MonitorConfig(0.,1.,1.,5.,3.,2000,'synthetic_camera','synthetic_behavior_v1',
        'synthetic_identity_v1','arbitrary_score_units','arithmetic_v1',
        'mu0=0 sigma0=1 identity fixture; k=1 h=5 note p.6; fixed=3 and gap=2000ms authored uncalibrated settings')

def sample(t,a,valid=True,reason='synthetic_valid'):
    return ScoreObservation(t,'synthetic_session','synthetic_camera',a,valid,reason,
        'synthetic_behavior_v1','synthetic_identity_v1','arbitrary_score_units')

def replay_scores(name,values,times=None,invalid=None):
    times=times or [i*500 for i in range(len(values))];invalid=invalid or {}
    monitors={m:SequentialMonitor(arithmetic_config(),'synthetic_session',m) for m in ('cusum','fixed')}
    rows=[]
    for t,a in zip(times,values):
        o=sample(t,a,t not in invalid,invalid.get(t,'synthetic_valid'))
        for method,monitor in monitors.items():
            r=monitor.update(o)
            rows.append(dict(case=name,**asdict(r),original_score_repr=repr(a)))
    return rows

def integration(enabled):
    c=MonitorConfig(.1,.1,1.,5.,3.,2000,'camera_motion','synthetic_motor_v1',
        'illustrative_motor_norm_v1','dimensionless_synthetic_motor_score','shadow_v1',
        'authored synthetic scaling and thresholds; no camera data fitting')
    result=[]
    for scenario in ['responsive','independent_incapacity','missing_corroboration','camera_failure','network_failure','outside_odd']:
        original=TemporalAssurance({2:KEY});gate=TemporalAssurance({2:KEY})
        wrapper=BehavioralReplay(gate,enabled=enabled,config=c)
        for t in [10000,10500,11000]:
            o=obs(t);o=replace(o,camera_motor_score=replace(o.camera_motor_score,value=.8))
            if scenario=='responsive':o=replace(o,hmi=replace(o.hmi,state='responded'))
            if scenario=='missing_corroboration':o=replace(o,corroboration=replace(o.corroboration,available=False))
            if scenario=='camera_failure':o=replace(o,camera_motor_score=replace(o.camera_motor_score,available=False))
            if scenario=='network_failure':o=replace(o,network_available=False)
            if scenario=='outside_odd':o=replace(o,oem_within_odd=False)
            expected=original.step(o);r=wrapper.step(o);assert r.safety==expected
            result.append(dict(case=scenario,input=asdict(o),**asdict(r),legacy_result_identical=True))
    return dict(feature_enabled=enabled,score_configuration=asdict(c),traces=result)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--enable-cusum',action='store_true')
    p.add_argument('--output-dir',type=Path,default=ROOT/'results/cusum');a=p.parse_args();out=a.output_dir;out.mkdir(parents=True,exist_ok=True)
    cases=[('note_page6',[.5,1.5,2.5,2.5,2.5],None,{}),
        ('isolated_moderate_spike',[0.,3.,0.,0.],None,{}),('single_extreme',[6.,0.,0.],None,{}),
        ('persistent_moderate',[2.]*8,None,{}),('rapid_return',[2.,2.,0.,0.],None,{}),
        ('repeated_overlapping_proxy',[2.5]*8,None,{}),('cadence_fast',[2.]*8,list(range(0,800,100)),{}),
        ('irregular_cadence',[.5,1.5,2.5,2.5,2.5],[0,70,350,900,2000],{}),
        ('normal_sequence',[.5]*100,None,{}),('noisy_crossing',[0.,4.,0.,4.,0.],None,{}),
        ('short_gap',[3.,None,2.],[0,500,1000],{500:'face_occlusion'}),
        ('long_gap',[3.,None,6.],[0,500,3000],{500:'tracking_failure'}),
        ('nonfinite',[2.,float('nan'),float('inf'),2.],None,{}),
        ('duplicate_time',[2.,6.,2.],[0,0,500],{}),('out_of_order',[2.,6.,2.],[500,100,1000],{})]
    rows=[]
    for name,values,times,invalid in cases:rows.extend(replay_scores(name,values,times,invalid))
    example=[r for r in rows if r['case']=='note_page6' and r['method']=='cusum']
    assert [r['statistic'] for r in example]==[0.,.5,2.,3.5,5.]
    assert [r['crossing'] for r in example]==[False]*4+[True]
    with (out/'synthetic_traces.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary=[]
    for name,_,_,_ in cases:
        for method in ('cusum','fixed'):
            selected=[r for r in rows if r['case']==name and r['method']==method]
            summary.append(dict(case=name,method=method,synthetic_crossing_timestamps_ms=[r['at_ms'] for r in selected if r['crossing']],
                unavailable_updates=sum(not r['available'] for r in selected),ending_statistic=selected[-1]['statistic']))
    m=SequentialMonitor(arithmetic_config(),'synthetic_session');lifecycle=[]
    lifecycle.append(asdict(m.update(sample(0,6.))))
    lifecycle.append(asdict(m.update(sample(500,6.))))
    lifecycle.append(asdict(m.tick(3000)))
    lifecycle.append(asdict(m.reset(ResetRequest(3000,'synthetic_session','sensor_recovery'))))
    lifecycle.append(asdict(m.update(sample(3500,2.))))
    lifecycle.append(asdict(m.reset(ResetRequest(0,'second_session','new_session'))))
    # CPU benchmark excludes camera acquisition/feature generation and recording I/O.
    timings={};n=20000
    for method in ('cusum','fixed'):
        monitor=SequentialMonitor(arithmetic_config(),'synthetic_session',method);observations=[sample(i*10,.5) for i in range(n)]
        start=time.perf_counter_ns()
        for o in observations:monitor.update(o)
        timings[method+'_mean_us_per_update']=(time.perf_counter_ns()-start)/n/1000
    report=dict(evidence='SIMULATED arithmetic and fault injection only; no empirical benefit claim',
        configuration=asdict(arithmetic_config()),configuration_sha256=arithmetic_config().digest,
        exact_example_statistics=[r['statistic'] for r in example],example_crossing_observation=5,
        cases=summary,lifecycle=lifecycle,clinical_and_camera_metrics={key:'NOT MEASURED' for key in
        ['event_sensitivity','false_alerts_per_eligible_non_event_hour','behavioral_detection_delay_seconds','missed_annotated_events',
         'real_feature_availability','real_unknown_frequency','improvement_over_fixed_threshold','maximum_safe_delay']},
        runtime=dict(**timings,updates_per_method=n,python=platform.python_version(),platform=platform.platform(),
            interpretation='Measured local Python update overhead only, not live latency or a deadline guarantee'),
        baseline_comparison='Identical synthetic inputs and lifecycle; arbitrary thresholds not matched for false-alert rate; not an empirical performance comparison')
    (out/'synthetic_verification.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    mode='enabled' if a.enable_cusum else 'disabled'
    (out/f'integration_{mode}.json').write_text(json.dumps(integration(a.enable_cusum),indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(example=report['exact_example_statistics'],crossing_observation=5,synthetic_cases=len(cases),
        feature_enabled=a.enable_cusum,legacy_policy_comparisons=18,all_identical=True,runtime=timings),indent=2))

if __name__=='__main__':main()
