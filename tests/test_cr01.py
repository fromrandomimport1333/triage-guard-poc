from dataclasses import replace
from src.triage_guard_cr01 import (
    convert_legacy_suite, cr01_extra_cases, onset_ordered_cases, all_cases, decide,
    medical_hypothesis,capacity_state, Signal,MAX_EVIDENCE_AGE_MS
)

def by_id(case_id):
    return {x.case_id:x for x in all_cases()}[case_id]

def test_rhythm_leading_motor_is_cardiac():
    x=by_id('X9_CARDIAC_THEN_MOTOR')
    assert medical_hypothesis(x)=='cardiac_rhythm'
    assert decide(x).oem_evaluation_request  # incapacity path unchanged by the label

def test_motor_leading_rhythm_abstains():
    assert medical_hypothesis(by_id('X10_MOTOR_THEN_CARDIAC'))=='unknown'

def test_unresolved_onsets_abstain_but_still_request():
    x=by_id('X11_ONSETS_UNRESOLVED')
    assert medical_hypothesis(x)=='unknown'
    assert decide(x).oem_evaluation_request

def test_unknown_etiology_not_normal():
    x=by_id('U1')
    assert medical_hypothesis(x)=='unknown'
    assert decide(x).oem_evaluation_request

def test_independent_capacity_with_stale_ecg():
    x=by_id('X1_ECG_STALE')
    assert medical_hypothesis(x)=='unknown'
    assert capacity_state(x)=='corroborated_unresponsive'
    assert decide(x).oem_evaluation_request

def test_camera_failure_does_not_erase_cardio_and_capacity():
    x=by_id('X2_CAMERA_STALE')
    assert medical_hypothesis(x)=='cardiac_rhythm'
    assert decide(x).oem_evaluation_request

def test_capacity_stale_blocks_new_request():
    assert not decide(by_id('X3_CAPACITY_STALE')).oem_evaluation_request

def test_response_or_oem_unavailable_blocks_request():
    for x in convert_legacy_suite():
        if x.hmi.state=='responded' or not x.oem_capability or not x.oem_within_odd or not x.oem_controller_healthy:
            assert not decide(x).oem_evaluation_request

def test_capacity_provenance_must_be_independent():
    for case in ['X7_HMI_SOURCE_COLLISION','X8_HMI_UNVERIFIED']:
        assert not decide(by_id(case)).oem_evaluation_request

def test_notifications_separate_consent_authorization_and_connectivity():
    assert (not decide(by_id('X4_NO_NETWORK')).contact_submission_eligible and
            not decide(by_id('X4_NO_NETWORK')).ems_submission_eligible)
    assert not decide(by_id('X5_NO_CONTACT_CONSENT')).contact_submission_eligible
    assert decide(by_id('X5_NO_CONTACT_CONSENT')).ems_submission_eligible
    assert decide(by_id('X6_NO_EMS_AUTHORIZATION')).contact_submission_eligible
    assert not decide(by_id('X6_NO_EMS_AUTHORIZATION')).ems_submission_eligible

def test_medical_suspicion_alone_never_authorizes_maneuver():
    assert all(not decide(x).oem_evaluation_request for x in convert_legacy_suite() if x.hmi.state=='responded')

def test_no_real_delivery_ever_claimed():
    for o in all_cases():
        assert decide(o).notification_status in ('no_notification_request',
           'simulation_eligible_no_transmission_or_ack','network_unavailable_no_delivery')
