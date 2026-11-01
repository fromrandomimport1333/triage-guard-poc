"""Execute software checks, integration and evidence recomputation assertions."""
import argparse,json,subprocess,sys
from pathlib import Path
import pandas as pd
import numpy as np
from run_cardiac_benchmark import metrics

def main():
    p=argparse.ArgumentParser();p.add_argument('--training-dir',required=True,type=Path);a=p.parse_args()
    out=Path('results');commands=[['-m','pytest','-q','tests','--junitxml=results/tests.xml'],
        ['run_cr01.py'],['run_assurance_cases.py'],['run_counterfactual_audit.py'],['run_temporal_demonstration.py'],
        ['run_cardiac_demo.py','--record',str(a.training_dir/'a103l'),'--alarm','Asystole',
         '--output','results/scientific_audit/integration_demo.json'],['run_scenario_demo.py'],
         ['run_cusum_demo.py'],['run_cusum_demo.py','--enable-cusum']]
    results=[]
    for i,args in enumerate(commands):
        r=subprocess.run([sys.executable,*args],capture_output=True,text=True)
        (out/f'qa_{i}.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
        results.append(dict(command='python '+' '.join(args),exit_code=r.returncode,log=f'qa_{i}.txt'))
        if r.returncode:raise RuntimeError(r.stdout+r.stderr)
    predictions=pd.read_csv(out/'cardiac/test_predictions.csv');benchmark=json.loads((out/'cardiac/benchmark.json').read_text())
    for name,df in predictions.groupby('method'):
        score=df.score.to_numpy() if df.score.notna().all() else None
        m=metrics(df.true_alarm,df.preserve_alarm,score,df.abstain)
        for k,v in m.items():
            assert np.isclose(v,benchmark['models'][name][k]),(name,k)
        assert m['tp']+m['tn']+m['fp']+m['fn']==225
    (out/'qa_execution.json').write_text(json.dumps(dict(commands=results,all_passed=True,metric_recomputation=True),indent=2))
    print('All commands and independent prediction-to-metric checks passed.')

if __name__=='__main__':main()
