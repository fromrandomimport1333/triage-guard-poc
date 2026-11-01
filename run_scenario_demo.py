"""Deterministic authored scenarios: no trained driver detector or vehicle control."""
import json
from dataclasses import replace,asdict
from pathlib import Path
from tests.test_temporal_assurance import obs
from scenario_reasoning import observable_scenario
from strict_safety_policy import strict_decide

def main():
    rows=[]
    for name,motor,hmi,previous,corroboration in [
        ('normal_responsive',0.,'responded',False,True),
        ('suspected_loss_of_responsiveness',0.,'no_response',True,True),
        ('seizure_like_unresponsive',.95,'no_response',False,True),
        ('responsive_motor_confounder',.95,'responded',False,True),
        ('missing_corroboration',0.,'no_response',True,False)]:
        o=obs(10000);o=replace(o,camera_motor_score=replace(o.camera_motor_score,value=motor),
            ecg_rhythm_score=replace(o.ecg_rhythm_score,value=0.),hmi=replace(o.hmi,state=hmi),
            corroboration=replace(o.corroboration,available=corroboration))
        d=strict_decide(o)
        rows.append(dict(case=name,scenario=observable_scenario(o,previous),decision=asdict(d)))
        if hmi=='responded' or not corroboration:assert not d.oem_evaluation_request
    path=Path(__file__).resolve().parent/'results/scientific_audit/scenario_demo.json'
    path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(dict(evidence='authored synthetic observations; no diagnostic accuracy claim',cases=rows),indent=2))
    print('Five synthetic scenario cases executed; responsive and missing-corroboration cases block requests.')

if __name__=='__main__':main()
