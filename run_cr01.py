"""Run CR-01 software-only assertions and export the ACTUAL scenario log."""
import json,csv
from pathlib import Path
from src.triage_guard_cr01 import run_cr01,convert_legacy_suite,cr01_extra_cases

if __name__=='__main__':
    r=run_cr01()
    output=Path(__file__).parent/'results'
    output.mkdir(exist_ok=True)
    (output/'cr01_scenarios.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    with (output/'cr01_scenarios.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(r[0]));writer.writeheader();writer.writerows(r)
    summary={
        'execution_scope':'35 synthetic decision scenarios: 24 adapted original + 8 CR-01 edge cases + 3 onset-ordered cases',
        'NOT':'clinical accuracy, independent outcome validation, real vehicle safety, actual SMS or EMS',
        'count':len(r),'oem_evaluation_requests':sum(x['oem_request'] for x in r),
        'contact_submission_eligible':sum(x['contact_eligible'] for x in r),
        'ems_submission_eligible':sum(x['ems_eligible'] for x in r),
        'medical_unknown':sum(x['medical_output']=='unknown' for x in r),
        'no_transport_or_dispatch_executed':True,
    }
    (output/'cr01_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
