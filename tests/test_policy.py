from src.triage_guard import scenario_suite,triage_guard,SecureEnvelope,medical_classification

def test_no_actuation_if_responsive():
    assert all(not triage_guard(o).maneuver_request for o in scenario_suite() if o.driver_response)

def test_no_actuation_without_oem_approval():
    assert all(not triage_guard(o).maneuver_request for o in scenario_suite() if not o.capability or not o.within_odd)

def test_no_request_on_controller_failure():
    assert all(not triage_guard(o).maneuver_request for o in scenario_suite() if not o.controller_healthy)

def test_independent_incapacity_no_medical_diagnosis_needed():
    x=next(o for o in scenario_suite() if o.id=='U1')
    assert medical_classification(x)=='normal' and triage_guard(x).maneuver_request

def test_quality_degradation_is_not_normal():
    for x in scenario_suite():
        if x.medical_quality<.55 or not x.sensor_fresh:
            assert medical_classification(x)=='uncertain'

def test_security_replay_tamper_expiration_and_authorization():
    env=SecureEnvelope(b'example_key_only_no_real_vehicle_use')
    m=env.sign('cabinguard',1,2000,{'function':'evaluate_mrm_request'})
    assert env.verify(m,1000)[0]
    assert env.verify(m,1001)==(False,'replay_or_out_of_order')
    e=SecureEnvelope(b'example_key_only_no_real_vehicle_use')
    bad=dict(m);bad['payload']={'function':'brake_directly'}
    assert e.verify(bad,1000)==(False,'invalid_integrity')
    e=SecureEnvelope(b'example_key_only_no_real_vehicle_use')
    assert e.verify(m,2001)==(False,'expired')
    e=SecureEnvelope(b'example_key_only_no_real_vehicle_use')
    other=env.sign('malicious',2,2000,{'function':'evaluate_mrm_request'})
    assert e.verify(other,1000)==(False,'unauthorized_sender')
