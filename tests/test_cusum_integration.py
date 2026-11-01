from dataclasses import asdict,replace
import pytest
from cusum_integration import BehavioralReplay
from sequential_monitor import MonitorConfig,ResetRequest
from temporal_assurance import TemporalAssurance,demo_status_frame
from tests.test_temporal_assurance import obs,KEY
from tests.test_strict_hard_negatives import base

def cfg():
    return MonitorConfig(.1,.1,1.,5.,3.,2000,'camera_motion','synthetic_motor_v1',
        'illustrative_motor_norm_v1','dimensionless_synthetic_motor_score','shadow_v1','authored synthetic constants; not calibrated')

def make(t,responsive=True,value=.8,available=True):
    o=obs(t)
    return replace(o,hmi=replace(o.hmi,state='responded' if responsive else 'no_response'),
        camera_motor_score=replace(o.camera_motor_score,value=value,available=available))

def test_disabled_default_is_exact_legacy_result():
    expected=TemporalAssurance();wrapped=BehavioralReplay(TemporalAssurance())
    for t in [10000,10500,11000]:
        o=make(t,False)
        r=wrapped.step(o);assert r.safety==expected.step(o) and r.monitor is None

@pytest.mark.parametrize('fault',['responsive','missing_hmi','missing_corroboration','shared_source','outside_odd','unhealthy','no_capability','invalid_camera'])
def test_cusum_crossing_or_fault_never_bypasses_existing_gates(fault):
    expected=TemporalAssurance();wrapped=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg())
    for t in [10000,10500]:
        o=make(t,responsive=fault=='responsive',available=fault!='invalid_camera')
        if fault=='missing_hmi':o=replace(o,hmi=replace(o.hmi,valid=False))
        if fault=='missing_corroboration':o=replace(o,corroboration=replace(o.corroboration,available=False))
        if fault=='shared_source':o=replace(o,corroboration=replace(o.corroboration,source_id=o.capacity_evidence.source_id))
        if fault=='outside_odd':o=replace(o,oem_within_odd=False)
        if fault=='unhealthy':o=replace(o,oem_controller_healthy=False)
        if fault=='no_capability':o=replace(o,oem_capability=False)
        r=wrapped.step(o);assert r.safety==expected.step(o)
        if fault!='invalid_camera':assert not r.safety.request
    # Invalid camera medical input cannot authorize anything, but independently
    # corroborated capacity may still request under the unchanged legacy policy.
    if fault=='invalid_camera':assert r.behavioral_evidence=='unknown'

def test_monitor_does_not_write_observation_or_expose_actuation_fields():
    o=make(10000);before=asdict(o)
    r=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg()).step(o)
    assert asdict(o)==before and r.monitor.crossing and not r.safety.request
    assert not {'request','brake','steer','transmit','ems_eligible'} & set(asdict(r.monitor))

def test_unknown_remains_explicit_separate_from_legacy_medical_class():
    r=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg()).step(make(10000,available=False))
    assert r.monitor.state=='UNKNOWN' and r.behavioral_evidence=='unknown'

def test_stale_camera_never_accumulates_as_fresh():
    o=make(10000);o=replace(o,camera_motor_score=replace(o.camera_motor_score,at_ms=9999))
    r=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg()).step(o)
    assert not r.monitor.available and not r.monitor.crossing

def test_oem_authentication_and_ack_never_reset_cusum_or_retrigger():
    supervisor=TemporalAssurance({2:KEY});wrapped=BehavioralReplay(supervisor,enabled=True,config=cfg())
    a=wrapped.step(make(10000,False));b=wrapped.step(make(10500,False))
    assert a.monitor.crossing and not a.safety.request and b.safety.request
    bad=demo_status_frame(1,10600,b'wrong-secret-at-least-sixteen',supervisor.can_id)
    assert not supervisor.process_oem_status(bad,10600)[0]
    assert wrapped.monitor.snapshot.latched
    good=demo_status_frame(1,10600,KEY,supervisor.can_id)
    assert supervisor.process_oem_status(good,10600)[0]
    r=wrapped.step(make(11000,False))
    assert not r.safety.request and not r.monitor.crossing and r.monitor.latched
    assert r.safety.stage=='OEM_ACCEPTED_REQUEST'

def test_no_notification_from_responsive_driver_with_crossing():
    r=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg()).step(make(10000))
    assert r.monitor.crossing and not r.safety.contacts_eligible and not r.safety.ems_eligible

def test_versioned_shadow_input_uses_original_synthetic_motor_score():
    r=BehavioralReplay(TemporalAssurance(),enabled=True,config=cfg()).step(make(10000,value=.3))
    assert r.monitor.score==.3 and r.monitor.z==pytest.approx(2.)
    assert r.monitor.score_version=='synthetic_motor_v1'

def test_monitor_reset_never_rearms_terminal_safety_and_updates_session():
    supervisor=TemporalAssurance({2:KEY});wrapped=BehavioralReplay(supervisor,enabled=True,config=cfg())
    wrapped.step(make(10000,False));wrapped.step(make(10500,False))
    assert supervisor.process_oem_status(demo_status_frame(1,10600,KEY,supervisor.can_id),10600)[0]
    wrapped.reset_monitor(ResetRequest(11000,'next_session','new_session'))
    r=wrapped.step(make(11500,False))
    assert r.monitor.crossing and r.monitor.session_id=='next_session'
    assert not r.safety.request and r.safety.stage=='OEM_ACCEPTED_REQUEST'
