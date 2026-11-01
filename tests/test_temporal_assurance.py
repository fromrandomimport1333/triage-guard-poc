"""Challenge-driven tests of the temporal assurance gate (synthetic only)."""
from dataclasses import replace
import pytest
from temporal_assurance import TemporalAssurance, demo_status_frame
from tests.test_strict_hard_negatives import base

KEY = b'example-ack-secret-is-not-for-use!!'

def obs(at_ms, **kwargs):
    b=base()
    # Match timestamps on all evidence, avoid false age failures.
    b=replace(b,time_ms=at_ms,
              camera_motor_score=replace(b.camera_motor_score,at_ms=at_ms),
              ecg_rhythm_score=replace(b.ecg_rhythm_score,at_ms=at_ms),
              capacity_evidence=replace(b.capacity_evidence,at_ms=at_ms),
              corroboration=replace(b.corroboration,at_ms=at_ms),
              hmi=replace(b.hmi,at_ms=at_ms))
    return replace(b, **kwargs)

def started_gate():
    x=TemporalAssurance({2:KEY})
    a=x.step(obs(10_000))
    b=x.step(obs(10_500))
    assert a.stage=='VERIFYING' and not a.request
    assert b.stage=='WAITING_OEM_ACK' and b.request
    return x,b

def test_requires_two_temporally_separate_valid_confirmations():
    x,b=started_gate()
    assert b.event_id==1

def test_evidence_gap_resets_confirmation_count():
    x=TemporalAssurance({2:KEY})
    x.step(obs(10000))
    s=x.step(obs(13000))
    assert s.stage=='VERIFYING' and not s.request

def test_driver_response_cancels_pre_request_streak():
    x=TemporalAssurance({2:KEY})
    x.step(obs(10000))
    responded=obs(10500); responded=replace(responded,hmi=replace(responded.hmi,state='responded'))
    assert not x.step(responded).request
    assert x.step(obs(11000)).stage=='VERIFYING'

def test_no_implicit_duplicate_requests_while_pending():
    x,b=started_gate()
    assert not x.step(obs(10700)).request
    assert not x.step(obs(10800)).request
    assert len([r for r in x.receipts if r['stage']=='WAITING_OEM_ACK' and r['reason']=='new_evaluation_request_only']) == 1

def test_wrong_event_authenticated_ack_cannot_complete():
    x,b=started_gate()
    wrong=demo_status_frame(999,10600,KEY,x.can_id)
    assert x.process_oem_status(wrong,10600) == (False,'event_id_mismatch')
    assert x.pending_event==1

def test_forged_ack_cannot_complete():
    x,b=started_gate()
    forged=demo_status_frame(1,10600,b'evil-fake-secret-is-not-genuine!!',x.can_id)
    assert x.process_oem_status(forged,10600)[0] is False
    assert x.pending_event==1

def test_valid_oem_ack_is_not_vehicle_maneuver():
    x,b=started_gate()
    frame=demo_status_frame(1,10600,KEY,x.can_id)
    assert x.process_oem_status(frame,10600)==(True,'OEM_ACCEPTED_REQUEST')
    assert x.step(obs(10900)).stage=='OEM_ACCEPTED_REQUEST'
    assert not x.step(obs(11500)).request

def test_valid_decline_keeps_single_request():
    x,b=started_gate()
    frame=demo_status_frame(1,10600,KEY,x.can_id,accepted=False)
    assert x.process_oem_status(frame,10600)==(True,'OEM_DECLINED_REQUEST')
    assert not x.step(obs(10900)).request

def test_oem_timeout_never_implies_success():
    x,b=started_gate()
    r=x.step(obs(13000))
    assert r.stage=='ACK_TIMEOUT' and not r.request
    assert x.step(obs(13200)).stage=='ACK_TIMEOUT'

def test_very_late_ack_is_refused():
    x,b=started_gate()
    frame=demo_status_frame(1,12500,KEY,x.can_id)
    assert x.process_oem_status(frame,12500)==(False,'ack_after_timeout')

def test_unordered_frame_refused_without_rearming():
    x,b=started_gate()
    r=x.step(obs(10000))
    assert r.stage=='INPUT_REJECTED' and not r.request
    assert x.pending_event==1

def test_medical_cause_unknown_still_allows_independent_capacity_path():
    b=obs(10000)
    b=replace(b,ecg_rhythm_score=replace(b.ecg_rhythm_score,at_ms=1000),
              camera_motor_score=replace(b.camera_motor_score,at_ms=1000))
    x=TemporalAssurance({2:KEY})
    r=x.step(b)
    assert r.medical=='unknown' and r.stage=='VERIFYING'
    b2=replace(b,time_ms=10500,capacity_evidence=replace(b.capacity_evidence,at_ms=10500),
               corroboration=replace(b.corroboration,at_ms=10500),hmi=replace(b.hmi,at_ms=10500))
    assert x.step(b2).request

def test_cannot_request_without_vehicle_capability_even_after_two_steps():
    x=TemporalAssurance({2:KEY})
    assert not x.step(obs(10000,oem_capability=False)).request
    assert not x.step(obs(10500,oem_capability=False)).request

def test_dropped_camera_is_not_corroboration():
    x=TemporalAssurance({2:KEY})
    a=obs(10000)
    assert not x.step(replace(a,corroboration=replace(a.corroboration,available=False))).request
    b=obs(10500)
    assert not x.step(replace(b,corroboration=replace(b.corroboration,available=False))).request

def test_simulated_receipt_omits_raw_biometric_and_is_chained():
    x,b=started_gate()
    r=x.receipts
    assert r[1]['previous']==r[0]['sha256']
    for field in ('camera_motor_score','ecg_rhythm_score','raw_image','patient_name','location'):
        assert field not in str(r)

def test_communications_failure_does_not_disable_local_request():
    x=TemporalAssurance({2:KEY})
    x.step(obs(10000,network_available=False))
    r=x.step(obs(10500,network_available=False))
    assert r.request and not r.contacts_eligible and not r.ems_eligible

def test_report_contact_and_ems_eligibility_not_delivery():
    x,b=started_gate()
    assert b.contacts_eligible and b.ems_eligible
    assert 'deliver' not in b.reason

def test_authenticated_status_replay_is_not_second_ack():
    x,b=started_gate()
    frame=demo_status_frame(1,10600,KEY,x.can_id)
    assert x.process_oem_status(frame,10600)[0]
    assert x.process_oem_status(frame,10620)==(False,'no_outstanding_request')

def test_status_request_confusion_is_blocked():
    x,b=started_gate()
    from src.reference_canfd import ReferenceRequest,encode
    frame=encode(ReferenceRequest(2,1,1,10600,1600,0,0,0,0,1,kind=1),KEY,x.can_id)
    assert x.process_oem_status(frame,10600)==(False,'not_a_controller_status')

def test_mismatched_event_does_not_consume_valid_ack_counter():
    x,b=started_gate()
    wrong=demo_status_frame(2,10600,KEY,x.can_id,counter=7)
    assert x.process_oem_status(wrong,10600)==(False,'event_id_mismatch')
    right=demo_status_frame(1,10610,KEY,x.can_id,counter=7)
    assert x.process_oem_status(right,10610)==(True,'OEM_ACCEPTED_REQUEST')


def test_receipt_chain_detects_accidental_edit_but_not_claimed_secure():
    from temporal_assurance import verify_receipt_chain
    x,b=started_gate()
    assert verify_receipt_chain(x.receipts)
    modified=[dict(row) for row in x.receipts]
    modified[0]['stage']='HIDDEN_EDIT'
    assert not verify_receipt_chain(modified)


def test_valid_status_advances_monotonic_time_frontier():
    x,b=started_gate()
    frame=demo_status_frame(1,10600,KEY,x.can_id)
    assert x.process_oem_status(frame,10600)[0]
    assert x.step(obs(10550)).stage=='INPUT_REJECTED'
