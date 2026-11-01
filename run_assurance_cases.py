"""Deterministic synthetic hard-negative trace, independent of clinical validation.

The *test labels* and injected defects are explicitly authored by the team.
Outputs are decisions from the strict source-tag policy. Source tags do not
establish physical independence of real sensors.
"""
from dataclasses import replace
from pathlib import Path
import csv, json
from strict_safety_policy import strict_decide
from tests.test_strict_hard_negatives import base


def case(name):
    x=base();t=x.time_ms
    if name=='nominal':return x
    if name=='driver_responded':return replace(x,hmi=replace(x.hmi,state='responded'))
    if name=='hmi_invalid':return replace(x,hmi=replace(x.hmi,valid=False))
    if name=='hmi_future':return replace(x,hmi=replace(x.hmi,at_ms=t+1))
    if name=='hmi_stale':return replace(x,hmi=replace(x.hmi,at_ms=t-1501))
    if name=='steering_stale':return replace(x,capacity_evidence=replace(x.capacity_evidence,at_ms=t-1600))
    if name=='camera_stale':return replace(x,corroboration=replace(x.corroboration,at_ms=t-1600))
    if name=='duplicated_steering_source':return replace(x,corroboration=replace(x.corroboration,source_id='vehicle_controls'))
    if name=='same_hmi_source':return replace(x,corroboration=replace(x.corroboration,source_id='hmi_button'))
    if name=='camera_quality_low':return replace(x,corroboration=replace(x.corroboration,quality=.1))
    if name=='steering_quality_low':return replace(x,capacity_evidence=replace(x.capacity_evidence,quality=.1))
    if name=='camera_nan':return replace(x,corroboration=replace(x.corroboration,value=float('nan')))
    if name=='camera_infinite':return replace(x,corroboration=replace(x.corroboration,value=float('inf')))
    if name=='camera_quality_invalid':return replace(x,corroboration=replace(x.corroboration,quality=1.5))
    if name=='no_vehicle_capability':return replace(x,oem_capability=False)
    if name=='outside_odd':return replace(x,oem_within_odd=False)
    if name=='controller_unhealthy':return replace(x,oem_controller_healthy=False)
    if name=='medical_ecg_stale':return replace(x,ecg_rhythm_score=replace(x.ecg_rhythm_score,at_ms=0))
    if name=='network_failure':return replace(x,network_available=False)
    if name=='medical_conflict':return replace(x,camera_motor_score=replace(x.camera_motor_score,value=.95),ecg_rhythm_score=replace(x.ecg_rhythm_score,value=.95))
    raise KeyError(name)


NAMES=['nominal','driver_responded','hmi_invalid','hmi_future','hmi_stale',
       'steering_stale','camera_stale','duplicated_steering_source','same_hmi_source',
       'camera_quality_low','steering_quality_low','camera_nan','camera_infinite',
       'camera_quality_invalid','no_vehicle_capability','outside_odd',
       'controller_unhealthy','medical_ecg_stale','network_failure','medical_conflict']


def run():
    rows=[]
    for name in NAMES:
        d=strict_decide(case(name))
        rows.append({'case':name,'medical':d.medical,'capacity':d.capacity,
          'oem_evaluation_request':int(d.oem_evaluation_request),
          'contact_submission_eligible':int(d.contact_submission_eligible),
          'ems_submission_eligible':int(d.ems_submission_eligible),
          'local_warning':int(d.local_warning),'reason':d.rationale})
    assert rows[0]['oem_evaluation_request']==1
    assert all(not r['oem_evaluation_request'] for r in rows[1:17])
    assert rows[17]['oem_evaluation_request']==1  # ECG-only fault
    assert rows[18]['oem_evaluation_request']==1  # communications-only fault
    assert rows[19]['medical']=='unknown'         # contradictory medical evidence
    out=Path(__file__).parent/'results';out.mkdir(exist_ok=True)
    with (out/'strict_assurance_cases.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    info={'scope':'20 deterministic synthetic cases, NOT observed patients or validation accuracy',
          'n_cases':len(rows),'hard_negative_cases_blocked':16,
          'positive_control_request_eligible':True,
          'ecg_failure_did_not_erase_independent_capacity_evidence':True,
          'network_failure_did_not_erase_local_vehicle_evaluation_eligibility':True,
          'source_ids_only_declare_independence_not_prove_it':True,
          'clinical_accuracy_claim':False}
    (out/'strict_assurance_summary.json').write_text(json.dumps(info,indent=2))
    print(json.dumps(info,indent=2))
    return rows

if __name__=='__main__':run()
