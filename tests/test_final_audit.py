from dataclasses import replace
import pytest
from cardiac_integration import attach_cardiac
from scenario_reasoning import observable_scenario
from strict_safety_policy import strict_decide
from tests.test_temporal_assurance import obs
from scientific_audit import exact_interval,independent_metrics

@pytest.mark.parametrize('score',[float('inf'),float('-inf'),float('nan'),1.01,-.01,True,'0.9',None])
def test_adapter_invalid_score_never_creates_evidence(score):
    o=attach_cardiac(obs(10000),dict(abstain=False,preserve_alarm=True,score=score))
    assert not o.ecg_rhythm_score.available

def test_adapter_missing_payload_is_unavailable():
    assert not attach_cardiac(obs(10000),{}).ecg_rhythm_score.available

def test_supported_cardiac_does_not_establish_loss_of_responsiveness():
    o=obs(10000);o=replace(o,hmi=replace(o.hmi,state='responded'))
    o=attach_cardiac(o,dict(abstain=False,preserve_alarm=True,score=.9))
    assert not strict_decide(o).oem_evaluation_request
    assert observable_scenario(o)!='suspected_transient_loss_of_responsiveness'

def test_suspected_loss_requires_transition_and_capacity():
    o=obs(10000);o=replace(o,camera_motor_score=replace(o.camera_motor_score,value=0.))
    assert observable_scenario(o,True)=='suspected_transient_loss_of_responsiveness'
    assert observable_scenario(o,False)=='uncertain_event'
    o=replace(o,corroboration=replace(o.corroboration,available=False))
    assert observable_scenario(o,True)=='uncertain_event'

def test_motor_suspicion_with_responsive_driver_never_requests_vehicle():
    o=obs(10000);o=replace(o,camera_motor_score=replace(o.camera_motor_score,value=.95),hmi=replace(o.hmi,state='responded'))
    assert observable_scenario(o)=='seizure_like_motor_activity'
    assert not strict_decide(o).oem_evaluation_request

def test_normal_needs_valid_evidence_and_response():
    o=obs(10000);o=replace(o,hmi=replace(o.hmi,state='responded'),camera_motor_score=replace(o.camera_motor_score,value=0.),ecg_rhythm_score=replace(o.ecg_rhythm_score,value=0.))
    assert observable_scenario(o)=='normal_driving'
    assert not strict_decide(o).oem_evaluation_request
    assert observable_scenario(replace(o,camera_motor_score=replace(o.camera_motor_score,available=False)))=='uncertain_event'

def test_exact_intervals_do_not_degenerate_at_boundary():
    assert exact_interval(0,0)==[None,None]
    assert exact_interval(88,88)==pytest.approx([.95894737094,1.])
    assert exact_interval(0,137)==pytest.approx([0.,.026566851096])

def test_independent_metrics_known_tied_score_fixture():
    m=independent_metrics([1,0,1,0],[1,1,0,0],[.8,.8,.2,.2])
    assert [m[k] for k in ['tp','fn','tn','fp']]==[1,1,1,1]
    assert m['roc_auc']==.5 and m['average_precision']==.5
    assert m['challenge_score']==25.
