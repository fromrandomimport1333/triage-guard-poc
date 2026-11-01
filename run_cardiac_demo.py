"""Replay one ICU record into existing synthetic capacity/safety traces."""
import argparse
import json
from pathlib import Path
from cardiac_signal import infer
from run_temporal_demonstration import example
from src.triage_guard import SecureEnvelope

def run(prefix,alarm,model):
    result=infer(prefix,alarm,model)
    traces=[example(s,result) for s in ['responsive','confirmed_independent','camera_failure','network_failure','oem_decline','no_oem_ack']]
    transport=SecureEnvelope(b'example-local-emergency-key-only!!')
    payload=dict(suspected_category='cardiac_alarm' if result['preserve_alarm'] else 'unknown',
                 responsiveness='synthetic_unresponsive',vehicle_state='simulation',time_ms=10500)
    message=transport.sign('cabinguard',1,12000,payload)
    verified=transport.verify(message,10600)
    replay=transport.verify(message,10601)
    return dict(scope='Real stored ICU signal; synthetic driver capacity and software-only vehicle interface. No diagnosis, maneuver or external delivery.',
        alarm_verification=result,alarm_warning_retained=result['preserve_alarm'],
        traces=traces,local_emergency_message=dict(payload=payload,verified=verified,replay_rejected=not replay[0],
            transmitted=False,contains_waveforms=False,confidentiality='not implemented; authenticated local envelope only'),
        real_vehicle_response=False,real_emergency_delivery=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',required=True,type=Path);p.add_argument('--alarm',required=True)
    p.add_argument('--model',type=Path,default=Path('results/cardiac/model_multimodal.json'))
    p.add_argument('--output',type=Path,default=Path('results/scientific_audit/integration_demo.json'))
    a=p.parse_args();r=run(a.record,a.alarm,a.model);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))

if __name__=='__main__':main()
