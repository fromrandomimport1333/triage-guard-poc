from src.can_demo import run_demo, SecOCSender, SecOCGateway, Assessment, REQUEST, crc8, E2E_DATA_ID

def test_virtual_bus_demo_outcomes():
    r = run_demo()['checks']
    assert r['heartbeat_none'][0] and r['eval_mrm_request'][0]
    assert r['eval_mrm_request'][2]['request'] == 'EVAL_MRM'
    # a replay trips the safety layer (alive counter) first; the security layer would catch it too
    assert r['replayed_frame'][0] is False
    assert r['replayed_frame'][1] in ('e2e_alive_counter_repeat', 'freshness_replay_or_out_of_window')
    assert r['tampered_request_bits'] == [False, 'authenticator_mismatch']
    assert r['unauthorized_sender'] == [False, 'authenticator_mismatch']
    assert r['bit_error_e2e'] == [False, 'e2e_crc_fail']
    assert r['supervisor_silent_fallback'][-1] == 'NONE'

def test_frame_is_16_bytes_and_roundtrips_fields():
    tx, gw = SecOCSender(b'k'), SecOCGateway(b'k')
    a = Assessment(request='VERIFY', capacity='uncertain', etiology='seizure_like', confidence_tier=2,
                   evidence_age_100ms=12, reason='incapacity_uncorroborated', event_id=3)
    a.health['ecg'] = False
    f = tx.pack(a)
    assert len(f) == 16
    ok, why, d = gw.receive(f)
    assert ok and d['request'] == 'VERIFY' and d['etiology'] == 'seizure_like'
    assert d['health']['ecg'] is False and d['health']['camera'] is True
    assert d['evidence_age_100ms'] == 12 and d['event_id'] == 3

def test_out_of_order_freshness_rejected():
    tx, gw = SecOCSender(b'k'), SecOCGateway(b'k')
    f1 = tx.pack(Assessment()); f2 = tx.pack(Assessment())
    assert gw.receive(f2)[0]
    assert gw.receive(f1) == (False, 'freshness_replay_or_out_of_window', None)
