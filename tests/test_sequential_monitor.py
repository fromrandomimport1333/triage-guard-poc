from dataclasses import asdict,replace
import math
import pytest
from sequential_monitor import MonitorConfig,ScoreObservation,SequentialMonitor,ResetRequest

def config(**changes):
    return replace(MonitorConfig(0.,1.,1.,5.,3.,2000,'synthetic_camera',
        'synthetic_behavior_v1','synthetic_identity_v1','arbitrary_score_units',
        'demo_v1','technical note p.6 arithmetic only; not calibrated'),**changes)

def sample(t,a,**changes):
    return replace(ScoreObservation(t,'session_a','synthetic_camera',a,True,'synthetic_valid',
        'synthetic_behavior_v1','synthetic_identity_v1','arbitrary_score_units'),**changes)

def test_exact_page_six_example_and_equality():
    m=SequentialMonitor(config(),'session_a');r=[m.update(sample(i*500,a)) for i,a in enumerate([.5,1.5,2.5,2.5,2.5])]
    assert [x.statistic for x in r]==[0.,.5,2.,3.5,5.]
    assert [x.crossing for x in r]==[False]*4+[True]
    assert r[-1].state=='SUSPECTED_BEHAVIORAL_CHANGE'

def test_single_extreme_crosses_and_no_implicit_persistence_requirement():
    assert SequentialMonitor(config(),'session_a').update(sample(0,6.)).crossing

def test_standardization_once_no_double_centering():
    m=SequentialMonitor(config(mu0=10.,sigma0=2.),'session_a')
    r=m.update(sample(0,15.));assert r.z==2.5 and r.statistic==1.5

def test_negative_drift_returns_zero_without_crossing():
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,2.))
    r=m.update(sample(100,-5.));assert r.statistic==0. and not r.crossing

@pytest.mark.parametrize('changes',[{'sigma0':0.},{'sigma0':-1.},{'sigma0':math.inf},{'mu0':math.nan},
    {'k':-1.},{'h':0.},{'h':math.inf},{'fixed_threshold':math.nan},{'gap_timeout_ms':0},
    {'gap_timeout_ms':True},{'k':True},{'source_id':''},{'config_version':''},{'parameter_provenance':''}])
def test_invalid_configuration_rejected(changes):
    with pytest.raises(ValueError):config(**changes)

@pytest.mark.parametrize('a',[math.nan,math.inf,-math.inf,None,True,'2.0',10**1000])
def test_bad_scores_are_unknown_not_zero_or_event(a):
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,3.))
    r=m.update(sample(500,a));assert r.state=='UNKNOWN' and r.statistic==2. and not r.crossing and r.z is None

@pytest.mark.parametrize('changes',[{'source_id':'other'},{'score_version':'other'},{'normalization_id':'other'},
    {'score_units':'probability'},{'valid':1},{'quality_reason':''},{'session_id':'other'}])
def test_metadata_rejected(changes):
    m=SequentialMonitor(config(),'session_a')
    r=m.update(sample(0,100.,**changes));assert r.state=='UNKNOWN' and not r.crossing

def test_missing_fields_and_wrong_object():
    m=SequentialMonitor(config(),'session_a')
    assert m.update({'score':10}).reason=='malformed_observation'
    with pytest.raises(TypeError):ScoreObservation(at_ms=0)

@pytest.mark.parametrize('t',[100,99,-1,True,1.5,None])
def test_duplicate_out_of_order_and_invalid_time(t):
    m=SequentialMonitor(config(),'session_a');m.update(sample(100,2.));before=m.snapshot
    r=m.update(sample(t,100.));assert r.state=='UNKNOWN' and not r.crossing and m.snapshot==before

def test_irregular_cadence_changes_elapsed_time_not_recurrence():
    m=SequentialMonitor(config(),'session_a')
    r=[m.update(sample(t,a)) for t,a in zip([0,70,350,900,2000],[.5,1.5,2.5,2.5,2.5])]
    assert [x.statistic for x in r]==[0.,.5,2.,3.5,5.]
    assert r[-1].at_ms==2000

@pytest.mark.parametrize('reason',['face_occluded','tracking_failed','dropped_frame','blur','unreliable_motion'])
def test_short_quality_gap_holds_then_recovers(reason):
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,3.))
    r=m.update(sample(1000,None,valid=False,quality_reason=reason))
    assert r.statistic==2. and r.state=='UNKNOWN' and not r.needs_reset
    r=m.update(sample(2000,2.));assert r.statistic==3. and r.available

def test_long_gap_resets_evidence_and_requires_explicit_recovery():
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,3.))
    m.update(sample(1000,None,valid=False))
    r=m.update(sample(2001,100.));assert r.statistic==0. and r.needs_reset and not r.crossing
    r=m.update(sample(2100,100.));assert r.state=='UNKNOWN'
    r=m.reset(ResetRequest(2100,'session_a','sensor_recovery'));assert r.state=='UNKNOWN'
    r=m.update(sample(2200,2.));assert r.statistic==1. and r.available

def test_gap_clock_anchors_to_last_valid_not_repeated_invalid_samples():
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,3.))
    for t in [500,1000,1500,2000]:assert not m.update(sample(t,None,valid=False)).needs_reset
    assert m.update(sample(2001,None,valid=False)).needs_reset

def test_silent_stream_tick_and_duplicate_tick():
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,3.))
    assert m.tick(1000).statistic==2.
    assert m.tick(2001).needs_reset
    assert m.tick(2001).reason=='invalid_tick_timestamp'

def test_latch_survives_return_to_baseline_and_outage_without_repeated_crossings():
    m=SequentialMonitor(config(),'session_a');assert m.update(sample(0,6.)).crossing
    assert m.update(sample(100,0.)).state=='VERIFICATION_PENDING'
    assert not m.update(sample(200,100.)).crossing
    r=m.tick(2201);assert r.latched and r.state=='UNKNOWN' and r.needs_reset

def test_explicit_reset_rearms_and_next_valid_update_required():
    m=SequentialMonitor(config(),'session_a');m.update(sample(0,6.))
    r=m.reset(ResetRequest(10,'session_a','operator_review'))
    assert not r.latched and r.statistic==0. and r.state=='UNKNOWN'
    assert m.update(sample(11,6.)).crossing

def test_session_boundary_and_old_session_rejection():
    m=SequentialMonitor(config(),'session_a');m.update(sample(5000,6.))
    m.reset(ResetRequest(0,'session_b','new_session'))
    assert m.update(sample(1,100.)).state=='UNKNOWN'
    assert m.update(sample(1,2.,session_id='session_b')).statistic==1.

@pytest.mark.parametrize('reset_req',[{},ResetRequest(-1,'session_a','operator_review'),
    ResetRequest(0,'session_a','operator_review'),ResetRequest(500,'other','operator_review'),
    ResetRequest(500,'session_a','new_session'),ResetRequest(500,'session_a','auto_ack'),
    ResetRequest(500,'session_a','sensor_recovery')])
def test_invalid_reset_is_atomic(reset_req):
    m=SequentialMonitor(config(),'session_a');m.update(sample(100,2.));before=m.snapshot
    with pytest.raises(ValueError):m.reset(reset_req)
    assert m.snapshot==before

def test_state_corruption_and_overflow_degrade():
    m=SequentialMonitor(config(),'session_a');m._state=replace(m.snapshot,statistic=math.nan)
    assert m.update(sample(0,6.)).reason=='corrupted_state'
    assert m.snapshot.needs_reset
    m=SequentialMonitor(config(mu0=-1e308),'session_a')
    r=m.update(sample(0,1e308));assert r.reason=='numeric_overflow' and not r.crossing

@pytest.mark.parametrize('changes',[{'statistic':-1.},{'statistic':1.},{'last_valid_ms':500},
    {'last_seen_ms':'bad'},{'started_ms':100},{'latched':1}])
def test_inconsistent_finite_state_rejected(changes):
    m=SequentialMonitor(config(),'session_a');m._state=replace(m.snapshot,**changes)
    r=m.update(sample(0,100.));assert r.state=='UNKNOWN' and r.needs_reset and not r.crossing

def test_rejected_metadata_retains_input_and_expected_configuration():
    m=SequentialMonitor(config(),'session_a')
    r=m.update(sample(0,2.,score_units='wrong_unit'))
    assert r.input_metadata['score_units']=='wrong_unit' and r.score_units=='arbitrary_score_units'

def test_fixed_baseline_has_same_quality_time_and_latch_rules():
    m=SequentialMonitor(config(),'session_a',method='fixed')
    assert not m.update(sample(0,2.5)).crossing
    assert m.update(sample(500,3.)).crossing
    assert not m.update(sample(1000,100.)).crossing
    assert m.update(sample(1500,None,valid=False)).state=='UNKNOWN'
    assert m.tick(3001).needs_reset

def test_long_normal_sequence_reproducible_and_versions_logged():
    a=SequentialMonitor(config(),'session_a');b=SequentialMonitor(config(),'session_a')
    for t in range(10000):
        x=a.update(sample(t*10,.5));y=b.update(sample(t*10,.5))
        assert x==y and x.statistic==0. and not x.crossing
    assert x.config_version=='demo_v1' and len(x.config_sha256)==64
    assert x.score_version=='synthetic_behavior_v1' and x.normalization_id=='synthetic_identity_v1'

@pytest.mark.parametrize('z',[2.,2.5,6.])
def test_feasibility_audit_constant_increment_count(z):
    m=SequentialMonitor(config(),'session_a');n=math.ceil(5./(z-1.))
    results=[m.update(sample(i*100,z)) for i in range(n)]
    assert not any(r.crossing for r in results[:-1]) and results[-1].crossing

def test_reference_equality_has_zero_drift():
    m=SequentialMonitor(config(),'session_a')
    for i in range(100):
        r=m.update(sample(i*100,1.));assert r.statistic==0. and not r.crossing

def test_restart_does_not_restore_latch_and_is_explicitly_not_persistent():
    m=SequentialMonitor(config(),'session_a');assert m.update(sample(0,6.)).crossing
    restarted=SequentialMonitor(config(),'session_a')
    assert restarted.snapshot.statistic==0. and not restarted.snapshot.latched
    assert restarted.tick(0).state=='UNKNOWN'
    # A new process can repeat a crossing: durable restart suppression is NOT claimed.
    assert restarted.update(sample(1,6.)).crossing
