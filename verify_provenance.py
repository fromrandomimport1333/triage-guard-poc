"""Read-only official metadata checks; no raw waveform download."""
import hashlib,json,urllib.request
import argparse
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--training-dir',type=Path,default=Path('../training/training'));args=p.parse_args()
    out=Path('results/cardiac');report={}
    for name in ['ALARMS','SHA256SUMS']:
        url='https://physionet.org/files/challenge-2015/1.0.0/training/'+name
        raw=urllib.request.urlopen(url,timeout=60).read()
        local=(args.training_dir/name).read_bytes()
        report[name]=dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),local_exact_match=raw==local)
        if name=='ALARMS':
            rows=[line.split(',') for line in raw.decode().splitlines() if line]
            report['official_current_counts']={'true':sum(int(r[2]) for r in rows),'false':sum(1-int(r[2]) for r in rows),'n':len(rows)}
    report['checked_date']='2026-10-30'
    (out/'official_metadata_verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
