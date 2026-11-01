"""Validate original archive and local WFDB records without label-derived features."""
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
import numpy as np
from scipy.io import loadmat
import wfdb
from physionet2015_vt_benchmark import parse_alarm_index, parse_header
from cardiac_signal import ALARMS, load_pre_alarm

def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()

def audit(dataset,archive,out):
    dataset,archive,out=map(Path,(dataset,archive,out));out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad: raise ValueError('Archive CRC failure: '+bad)
        names=z.namelist()
        members={Path(n).name:n for n in names if not n.endswith('/')}
        if len(members)!=sum(not n.endswith('/') for n in names): raise ValueError('ambiguous archive basenames')
        archive_hashes={Path(n).name:hashlib.sha256(z.read(n)).hexdigest() for n in names if not n.endswith('/')}
    ix=parse_alarm_index(dataset/'ALARMS').sort_values('record')
    records=(dataset/'RECORDS').read_text().split()
    if set(records)!=set(ix.record) or len(records)!=len(set(records)): raise ValueError('RECORDS/ALARMS mismatch')
    if set(p.stem for p in dataset.glob('*.hea'))!=set(records): raise ValueError('unexpected/missing headers')
    supplied={line.split()[1]:line.split()[0] for line in (dataset/'SHA256SUMS').read_text().splitlines()}
    manifest=[];duplicates={};pre_duplicates={};errors=[];channels=Counter();units=Counter();comments=Counter()
    for row in ix.itertuples(index=False):
        item=dict(record=row.record,alarm=row.alarm,true_alarm=int(row.true_alarm),status='ok')
        try:
            if row.alarm not in ALARMS: raise ValueError('unknown alarm')
            for ext in ('.hea','.mat'):
                filename=row.record+ext;digest=sha(dataset/filename)
                if digest!=archive_hashes[filename] or digest!=supplied[filename]: raise ValueError('checksum mismatch '+filename)
                item[ext[1:]+'_sha256']=digest
            h=parse_header(dataset/(row.record+'.hea'))
            comment=[l.strip()[1:].strip() for l in (dataset/(row.record+'.hea')).read_text().splitlines() if l.strip().startswith('#')]
            comments.update(comment)
            if comment != [row.alarm,'True alarm' if row.true_alarm else 'False alarm']: raise ValueError('header/index label mismatch or extra metadata')
            val=loadmat(dataset/(row.record+'.mat'))['val']
            if val.shape!=(h['n_channels'],h['n_samples']): raise ValueError('waveform geometry mismatch')
            if h['fs']!=250 or h['n_samples'] not in (75000,82500): raise ValueError('unexpected duration/rate')
            wh=wfdb.rdheader(str(dataset/row.record))
            if any(int(val[i].astype(np.int64).sum())%65536!=int(wh.checksum[i])%65536 for i in range(len(wh.sig_name))): raise ValueError('WFDB checksum mismatch')
            s,fs,names_ch,units_ch=load_pre_alarm(dataset/row.record)
            manual=np.stack([(val[i,:75000].astype(float)-ch['baseline'])/ch['gain'] for i,ch in enumerate(h['channels'])],axis=1)
            manual[val[:,:75000].T==-32768]=np.nan
            if not np.allclose(s,manual,equal_nan=True): raise ValueError('WFDB/manual physical scaling mismatch')
            full=hashlib.sha256(val.tobytes()).hexdigest();pre=hashlib.sha256(val[:,:75000].tobytes()).hexdigest()
            if full in duplicates or pre in pre_duplicates: raise ValueError('duplicate full/prealarm record '+pre_duplicates.get(pre,duplicates.get(full,'')))
            duplicates[full]=row.record;pre_duplicates[pre]=row.record
            channels.update(names_ch);units.update(units_ch)
            item.update(fs=fs,duration_s=h['n_samples']/fs,channels=h['channels'],prealarm_sha256=pre,
                        prealarm_nonfinite=int((~np.isfinite(s)).sum()),patient_id=None)
        except Exception as exc:
            item.update(status='excluded',reason=str(exc));errors.append(dict(record=row.record,reason=str(exc)))
        manifest.append(item)
    for filename in ['ALARMS','RECORDS']:
        if sha(dataset/filename)!=archive_hashes[filename] or sha(dataset/filename)!=supplied[filename]: raise ValueError('index checksum mismatch')
    report=dict(dataset='PhysioNet/CinC Challenge 2015',version='1.0.0',doi='10.13026/c9fg-a467',
        source_url='https://physionet.org/content/challenge-2015/1.0.0/',
        archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,archive_entries=len(names),archive_crc_ok=True,
        license='Open Data Commons Attribution License v1.0 (dataset page)',
        n_indexed=len(ix),n_valid=sum(r['status']=='ok' for r in manifest),exclusions=errors,
        counts={str(k):int(v) for k,v in ix.true_alarm.value_counts().items()},
        alarm_counts=ix.groupby(['alarm','true_alarm']).size().unstack(fill_value=0).to_dict('index'),
        duration_counts=dict(Counter(str(r.get('duration_s')) for r in manifest)),channels=dict(channels),units=dict(units),
        unique_header_comments=sorted(comments),patient_ids_available=False,
        patient_metadata_assessment='Archive contains only record indexes, checksums and waveform/header pairs; header comments contain alarm type and adjudication only. No reliable patient grouping.',
        expected_distribution_matches=len(ix)==750 and int(ix.true_alarm.sum())==292,
        duplicate_check='Exact digital full and pre-alarm hashes; duplicates excluded before split; near duplicates/patient overlap unresolved',
        preprocessing=dict(boundary_seconds=300,windows_seconds=[30,10],filter='causal third-order Butterworth; ECG 5-25 Hz; pulse 0.5-8 Hz',normalization='window median after truncation',imputation='training only'))
    (out/'dataset_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (out/'dataset_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return ix,manifest,report
