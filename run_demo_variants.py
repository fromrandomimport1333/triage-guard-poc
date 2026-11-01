"""Additional replay paths selected only by predicted outputs, not true labels."""
import argparse,json
from pathlib import Path
import pandas as pd
from run_cardiac_demo import run

def main():
    p=argparse.ArgumentParser();p.add_argument('--training-dir',type=Path,required=True);args=p.parse_args()
    out=Path('results/cardiac');d=pd.read_csv(out/'test_predictions.csv');d=d[d.method=='multimodal']
    subsets={'supported':d[(~d.abstain)&(d.score>=.7)&(d.preserve_alarm==1)],
             'suppressed':d[(~d.abstain)&(d.preserve_alarm==0)]}
    for name,table in subsets.items():
        row=table.sort_values('record').iloc[0]
        r=run(args.training_dir/row.record,row.alarm,out/'model_multimodal.json')
        r['selection']='Lexicographically first held-out record with this predicted output; truth not used; functionality demonstration only'
        r['record']=row.record
        audit=Path('results/scientific_audit');audit.mkdir(exist_ok=True)
        (audit/f'integration_{name}_demo.json').write_text(json.dumps(r,indent=2))
        responsive=r['traces'][0];assert not responsive['request']
        if name=='supported':assert responsive['medical']=='cardiac_rhythm'
        else:assert responsive['medical']=='unknown'
        print(name,row.record,r['alarm_verification']['reason'],responsive['medical'])

if __name__=='__main__':main()
