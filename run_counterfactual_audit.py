"""Exhaustive SMALL FINITE DOMAIN check and counterexamples for Phase-1 policy.

NOT clinical statistics, not a real vehicle safety proof. The 8 boolean axes
are constructed test variables and do not capture the real continuous space.
"""
from dataclasses import replace
from itertools import product
from pathlib import Path
import json,csv
from temporal_assurance import TemporalAssurance
from tests.test_temporal_assurance import obs

AXES = ['nonresponse','steering_present','camera_present','source_distinct',
        'oem_capability','within_odd','controller_healthy','network_available']


def sample_for(bits,time_ms, medical_high=False, incapacitated_truth=True):
    (nr,steer,cam,unique,cap,odd,health,net) = bits
    o=obs(time_ms)
    return replace(o, truth_incapacity=incapacitated_truth,
       hmi=replace(o.hmi,state='no_response' if nr else 'responded'),
       capacity_evidence=replace(o.capacity_evidence,available=steer),
       corroboration=replace(o.corroboration,available=cam,
          source_id='camera_posture' if unique else o.capacity_evidence.source_id),
       oem_capability=cap,oem_within_odd=odd,oem_controller_healthy=health,
       network_available=net,
       camera_motor_score=replace(o.camera_motor_score,value=0.92 if medical_high else 0.14),
       ecg_rhythm_score=replace(o.ecg_rhythm_score,value=0.10))


def run():
    rows=[]; failures=[]
    for values in product([False,True],repeat=len(AXES)):
        bits=dict(zip(AXES,values));elig=all(values[:7])
        observed=[]
        for medical_high in (False,True):
            x=TemporalAssurance()
            first=x.step(sample_for(values,10000,medical_high))
            second=x.step(sample_for(values,10500,medical_high))
            if first.request: failures.append((bits,'requested on first observation'))
            if second.request!=elig: failures.append((bits,'violates gate boolean contract',second.request))
            if second.request and not second.stage=='WAITING_OEM_ACK': failures.append((bits,'wrong stage'))
            observed.append(second.request)
        if observed[0]!=observed[1]:failures.append((bits,'medical evidence incorrectly gates vehicle'))
        rows.append({**{k:int(v) for k,v in bits.items()},'normal_medical_request':int(observed[0]),
          'elevated_medical_request':int(observed[1]), 'policy_expected':int(elig)})
    assert not failures, failures[:5]
    # Two deliberately adversarial cases to expose limits rather than hide them.
    b=(True,True,True,True,True,True,True,True)
    x=TemporalAssurance()
    x.step(sample_for(b,10000,False,incapacitated_truth=False))
    spurious=x.step(sample_for(b,10500,False,incapacitated_truth=False))
    # With mutually incorrect but distinct observations, the gate can still be wrong.
    assert spurious.request
    y=TemporalAssurance()
    b2=(True,True,False,True,True,True,True,True)
    y.step(sample_for(b2,10000,True,incapacitated_truth=True))
    missed=y.step(sample_for(b2,10500,True,incapacitated_truth=True))
    assert not missed.request
    out=Path(__file__).resolve().parent/'results';out.mkdir(exist_ok=True)
    with (out/'counterfactual_grid.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={
      'test_kind':'finite 8-axis boolean policy enumeration, not field validation',
      'independent_combinations':len(rows),
      'policy_evaluations':len(rows)*2,
      'invariant_failures':0,
      'requests_each_medical_level':sum(r['normal_medical_request'] for r in rows),
      'medical_score_invariance_pairs':len(rows),
      'counterexample_false_request_from_jointly_misleading_sources':bool(spurious.request),
      'counterexample_missed_request_when_true_incapacity_but_camera_missing':bool(not missed.request),
      'real_world_false_alarm_rate_supported':False,
      'clinical_detection_supported':False,
      'safety_certification_supported':False,
      'warning':'source IDs are declarations; medical/capacity evidence and timing remain simulated'
    }
    (out/'counterfactual_summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return summary

if __name__=='__main__':run()
