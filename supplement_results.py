"""Record coverage and failure counts without changing fitted models or thresholds."""
import json
from collections import Counter
from pathlib import Path
import pandas as pd
from cardiac_signal import decision

def main():
    out=Path('results/cardiac');f=pd.read_csv(out/'features.csv').set_index('record');pred=pd.read_csv(out/'test_predictions.csv')
    report={'all_records':dict(n=len(f),no_valid_ecg=int(((f.ecg0_valid==0)&(f.ecg1_valid==0)).sum()),
        no_valid_pulse=int((f.pulse_valid==0).sum()),rate_conflict=int((f.rate_disagreement>40).sum())),
        'methods':{},'note':'Quality failure can be genuine absent physiology or artifact; fallback preserves alarms. Counts may overlap.'}
    for name in ['ecg','multimodal']:
        a=json.loads((out/f'model_{name}.json').read_text());rows=pred[pred.method==name];reasons=Counter()
        for r in rows.itertuples():
            d=decision(r.score,f.loc[r.record].to_dict(),name,a['threshold'])
            reasons.update(d['reason'].split(','))
        failed=int(rows.score.isna().sum())
        report['methods'][name]=dict(n=len(rows),abstentions=int(rows.abstain.sum()),prediction_failure_count=failed,
            prediction_failure_rate=failed/len(rows),reason_counts=dict(reasons),calibration_assessed=False)
    (out/'operational_coverage.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
