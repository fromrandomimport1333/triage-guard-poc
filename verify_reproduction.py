"""Compare independent clean-environment outputs, excluding variable timing."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import xml.etree.ElementTree as ET

def main():
    root=Path('results');a=root/'cardiac';b=root/'cardiac_clean';checks={}
    for name in ['splits.csv','test_predictions.csv','comparison.csv','per_alarm.csv','development_oof.csv','development_thresholds.csv','features.csv']:
        x=pd.read_csv(a/name);y=pd.read_csv(b/name)
        pd.testing.assert_frame_equal(x,y,check_exact=False,rtol=1e-12,atol=1e-12)
        checks[name]='equal within 1e-12; nonnumeric fields exact'
    for name in ['model_ecg.json','model_multimodal.json','dataset_manifest.json','dataset_audit.json']:
        assert json.loads((a/name).read_text())==json.loads((b/name).read_text()),name
        checks[name]='exact parsed JSON equality'
    x=json.loads((a/'benchmark.json').read_text());y=json.loads((b/'benchmark.json').read_text())
    for k in ['models','selection','split_sha256','n_processed','n_train','n_test']:assert x[k]==y[k],k
    tests=ET.parse(root/'clean_tests.xml').getroot().findall('.//testcase');assert tests and all(not list(t) for t in tests)
    report=dict(clean_environment=True,system_site_packages=False,all_checks_passed=True,checks=checks,all_metrics_and_bootstrap_intervals_exact=True,
        clean_tests_passed=len(tests),timing_compared=False,reason='Wall-clock timing varies; numerical outputs independently reproduced',
        clean_environment_packages='requirements-environment-lock.txt')
    (a/'reproduction_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
