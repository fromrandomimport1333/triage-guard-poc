from dataclasses import replace
import numpy as np
import pytest
from src.triage_guard_cr01 import Signal,DriverResponse,CR01Observation
from strict_safety_policy import strict_decide,strict_capacity


def base():
    t=10000
    return CR01Observation(
      case_id='synthetic_true_incapacity',time_ms=t,
      truth_medical='unknown',truth_incapacity=True,
      camera_motor_score=Signal('camera_motion',0.1,0.9,t),
      ecg_rhythm_score=Signal('ecg',0.1,0.9,t),
      capacity_evidence=Signal('vehicle_controls',0.95,0.92,t),
      hmi=DriverResponse('no_response','hmi_button',t),
      corroboration=Signal('camera_pose',0.95,0.90,t),
      oem_capability=True,oem_within_odd=True,oem_controller_healthy=True,
      trusted_contact_opt_in=True,ems_interface_authorized=True,network_available=True)


def test_nominal_three_distinct_groups_can_request():
    d=strict_decide(base())
    assert d.capacity=='corroborated_unresponsive'
    assert d.oem_evaluation_request
    assert d.medical=='unknown'


def test_original_legacy_duplicate_source_must_not_count_as_independent():
    from src.triage_guard_cr01 import convert_legacy_suite
    old=[x for x in convert_legacy_suite() if x.case_id=='C1'][0]
    assert old.capacity_evidence.source_id==old.corroboration.source_id
    assert not strict_decide(old).oem_evaluation_request

@pytest.mark.parametrize('case',[
 'hmi_response','hmi_invalid','hmi_future','hmi_stale',
 'steering_stale','camera_stale','shared_source','shared_hmi_source',
 'camera_quality_low','steering_quality_low','camera_nan',
 'camera_infinite','camera_quality_over_one','no_oem_capability',
 'odd_outside','controller_unhealthy'])
def test_hard_negative_no_new_request(case):
    x=base()
    t=x.time_ms
    if case=='hmi_response':x=replace(x,hmi=replace(x.hmi,state='responded'))
    if case=='hmi_invalid':x=replace(x,hmi=replace(x.hmi,valid=False))
    if case=='hmi_future':x=replace(x,hmi=replace(x.hmi,at_ms=t+1))
    if case=='hmi_stale':x=replace(x,hmi=replace(x.hmi,at_ms=t-1501))
    if case=='steering_stale':x=replace(x,capacity_evidence=replace(x.capacity_evidence,at_ms=t-1600))
    if case=='camera_stale':x=replace(x,corroboration=replace(x.corroboration,at_ms=t-1600))
    if case=='shared_source':x=replace(x,corroboration=replace(x.corroboration,source_id='vehicle_controls'))
    if case=='shared_hmi_source':x=replace(x,corroboration=replace(x.corroboration,source_id='hmi_button'))
    if case=='camera_quality_low':x=replace(x,corroboration=replace(x.corroboration,quality=.1))
    if case=='steering_quality_low':x=replace(x,capacity_evidence=replace(x.capacity_evidence,quality=.1))
    if case=='camera_nan':x=replace(x,corroboration=replace(x.corroboration,value=float('nan')))
    if case=='camera_infinite':x=replace(x,corroboration=replace(x.corroboration,value=float('inf')))
    if case=='camera_quality_over_one':x=replace(x,corroboration=replace(x.corroboration,quality=1.5))
    if case=='no_oem_capability':x=replace(x,oem_capability=False)
    if case=='odd_outside':x=replace(x,oem_within_odd=False)
    if case=='controller_unhealthy':x=replace(x,oem_controller_healthy=False)
    assert not strict_decide(x).oem_evaluation_request,case


def test_high_medical_scores_with_responsive_driver_do_not_request():
    x=replace(base(),hmi=replace(base().hmi,state='responded'),
         camera_motor_score=replace(base().camera_motor_score,value=.99),
         ecg_rhythm_score=replace(base().ecg_rhythm_score,value=.99))
    assert strict_decide(x).medical=='unknown'
    assert not strict_decide(x).oem_evaluation_request


def test_stale_ecg_does_not_erase_independent_capacity_evidence():
    x=replace(base(),ecg_rhythm_score=replace(base().ecg_rhythm_score,at_ms=0))
    assert strict_decide(x).oem_evaluation_request


def test_network_failure_leaves_local_oem_request_eligible():
    x=replace(base(),network_available=False)
    d=strict_decide(x)
    assert d.oem_evaluation_request
    assert not d.contact_submission_eligible and not d.ems_submission_eligible


def test_consent_and_ems_permissions_separate():
    x=replace(base(),trusted_contact_opt_in=False)
    d=strict_decide(x)
    assert not d.contact_submission_eligible and d.ems_submission_eligible
    x=replace(base(),ems_interface_authorized=False)
    d=strict_decide(x)
    assert d.contact_submission_eligible and not d.ems_submission_eligible
