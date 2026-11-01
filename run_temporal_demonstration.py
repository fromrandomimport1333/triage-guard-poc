"""Phase-1 software message-lifecycle simulation with explicit outputs.

No physical bus, ECU, camera, ECG, automation or emergency dispatch.
"""
from dataclasses import replace
from pathlib import Path
import json,csv
from temporal_assurance import TemporalAssurance,demo_status_frame
from tests.test_temporal_assurance import obs
from src.reference_canfd import ReferenceRequest,ReferenceReceiver,encode

KEY_OEM=b'example-ack-secret-is-not-for-use!!'
KEY_GATE=b'example-proposal-key-not-for-prod!!'
REQ_ID=0x120
STAT_ID=0x121


def example(name, cardiac_result=None):
    gate=TemporalAssurance({2:KEY_OEM},can_id=STAT_ID)
    b1=obs(10000)
    if cardiac_result is not None:
        from cardiac_integration import attach_cardiac
        b1=attach_cardiac(b1,cardiac_result)
    if name=='responsive':
        b1=replace(b1,hmi=replace(b1.hmi,state='responded'))
    elif name=='medical_unknown':
        b1=replace(b1,ecg_rhythm_score=replace(b1.ecg_rhythm_score,available=False),
                   camera_motor_score=replace(b1.camera_motor_score,available=False))
    elif name=='camera_failure':
        b1=replace(b1,corroboration=replace(b1.corroboration,available=False))
    elif name=='network_failure':
        b1=replace(b1,network_available=False)
    first=gate.step(b1)
    b2=replace(b1,time_ms=10500,
        hmi=replace(b1.hmi,at_ms=10500),
        capacity_evidence=replace(b1.capacity_evidence,at_ms=10500),
        corroboration=replace(b1.corroboration,at_ms=10500),
        camera_motor_score=replace(b1.camera_motor_score,at_ms=10500),
        ecg_rhythm_score=replace(b1.ecg_rhythm_score,at_ms=10500))
    second=gate.step(b2)
    transport='no_request'
    ack='not_applicable'
    if second.request:
        # Gateway acceptance is not a maneuver authorization.
        req=ReferenceRequest(sender_id=1,event_id=second.event_id,counter=1,
             created_ms=second.time_ms,valid_for_ms=1600,
             medical_code=0 if second.medical=='unknown' else 1,
             capacity_code=2,confidence_tier=0,sensor_health=3,requested_function=1)
        wire=encode(req,KEY_GATE,REQ_ID)
        gateway=ReferenceReceiver({1:KEY_GATE},REQ_ID)
        ok,transport=gateway.check(wire,10510)
        assert ok
        if name=='oem_decline':
            status=demo_status_frame(second.event_id,10600,KEY_OEM,STAT_ID,accepted=False)
            ack=gate.process_oem_status(status,10600)[1]
        elif name=='no_oem_ack':
            ack=gate.step(replace(b2,time_ms=13000,
              hmi=replace(b2.hmi,at_ms=13000),
              capacity_evidence=replace(b2.capacity_evidence,at_ms=13000),
              corroboration=replace(b2.corroboration,at_ms=13000))).stage
        else:
            status=demo_status_frame(second.event_id,10600,KEY_OEM,STAT_ID,accepted=True)
            ack=gate.process_oem_status(status,10600)[1]
    return dict(case=name,first_stage=first.stage,second_stage=second.stage,
                request=int(second.request),medical=second.medical,
                contacts_eligible=int(second.contacts_eligible),
                ems_eligible=int(second.ems_eligible),
                gateway_result=transport,oem_reply=ack,
                biometric_payload_in_receipt=0,
                real_vehicle_maneuver=0,real_notification_delivered=0)


def main():
    scenarios=['confirmed_independent','medical_unknown','camera_failure',
             'responsive','network_failure','oem_decline','no_oem_ack']
    result=[example(s) for s in scenarios]
    out=Path(__file__).resolve().parent/'results';out.mkdir(exist_ok=True)
    with (out/'temporal_demonstration.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    (out/'temporal_demonstration.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
