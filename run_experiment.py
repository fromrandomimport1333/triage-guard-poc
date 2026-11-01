"""Run deterministic policy experiment. Standard library only."""
import json
from pathlib import Path
from src.triage_guard import run_scenarios,scenario_suite,triage_guard,SecureEnvelope

if __name__=='__main__':
    m=run_scenarios()
    out=Path(__file__).parent/'results'
    out.mkdir(exist_ok=True)
    (out/'synthetic_policy_results.json').write_text(json.dumps({
        'evaluation_scope':'24 hand-authored synthetic fault and driver-state cases, NOT clinical data',
        'metrics':m,'limitations':'The expected output is a safety policy oracle and overlaps proposed policy semantics; no clinical accuracy or real-world improvement can be inferred.'
    },indent=2),encoding='utf8')
    with (out/'scenario_log.csv').open('w') as f:
        f.write('id,truth_event,incapacitated,medical_output,incapacity_confirmed,maneuver_request,reason\n')
        for s in scenario_suite():
            d=triage_guard(s)
            f.write(f'{s.id},{s.truth_event},{int(s.truth_incapacity)},{d.medical_class},{int(d.incapacity_confirmed)},{int(d.maneuver_request)},{d.reason}\n')
    env=SecureEnvelope(b'test-key-not-for-production')
    base=env.sign('cabinguard',1,1000,{'request':'policy_evaluation'})
    valid=env.verify(base,500)
    replay=env.verify(base,501)
    changed=dict(base);changed['payload']={'request':'direct_brake'}
    tampered=SecureEnvelope(b'test-key-not-for-production').verify(changed,500)
    expired=SecureEnvelope(b'test-key-not-for-production').verify(base,1100)
    spoof=SecureEnvelope(b'test-key-not-for-production').verify(env.sign('attacker',2,1000,{'request':'policy_evaluation'}),500)
    cyber={'valid':valid,'replayed':replay,'tampered':tampered,'expired':expired,'unauthorized':spoof}
    (out/'security_checks.json').write_text(json.dumps(cyber,indent=2))
    print(json.dumps({'policy':m,'security':cyber},indent=2))
