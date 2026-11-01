"""CabinGuard-ADI Phase 1 supplementary cardiac benchmark.

Purpose: exploratory discrimination of adjudicated true vs false *existing* ventricular
 tachycardia alarms from PhysioNet/CinC 2015. It DOES NOT detect acute medical
 incapacitation, validate in-cabin ECG, or prove clinical reliability.

References:
  Clifford et al., Computing in Cardiology 2015, pp 273-276.
  https://physionet.org/content/challenge-2015/1.0.0/

External data are not distributed with this script. Download the PhysioNet
2015 TRAINING files, preserving ALARMS and .hea/.mat names. The challenge's
original hidden test set is unavailable. Without verified patient IDs, the
internal split is only RECORD-disjoint and MUST NOT be described as
patient-disjoint validation.

Requires: numpy, scipy, scikit-learn, pandas; no AI service/API calls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
import pandas as pd
from scipy.io import loadmat
from scipy.signal import butter, sosfiltfilt, find_peaks
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import confusion_matrix, balanced_accuracy_score, precision_score, recall_score, average_precision_score

ALARM = 'Ventricular_Tachycardia'
FS_EXPECTED = 250.0
ALARM_TIME_S = 300.0
FEATURE_SECONDS = 20.0
RANDOM_STATE = 20261030


def parse_alarm_index(path: Path) -> pd.DataFrame:
    rows = []
    for line_no, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith('#'): continue
        bits = [v.strip() for v in raw.split(',')]
        if len(bits) != 3 or bits[2] not in {'0','1'} or not re.fullmatch(r'[a-z][0-9]{3}[ls]', bits[0]):
            raise ValueError(f'Invalid ALARMS line {line_no}: {raw!r}')
        rows.append({'record':bits[0], 'alarm':bits[1], 'true_alarm':int(bits[2])})
    df = pd.DataFrame(rows)
    if df.empty or df.record.duplicated().any():
        raise ValueError('Missing or duplicate ALARMS records')
    return df


def parse_header(path: Path):
    # Official 2015 .hea includes record, channel count, fs, sample count and
    # the last text token in each signal row is the channel name.
    lines = [line.strip() for line in path.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    head = lines[0].split()
    if len(head) < 4: raise ValueError(f'Malformed header: {path}')
    name, n_channels, fs, n_samples = head[:4]
    n_channels, fs, n_samples = int(n_channels), float(fs), int(n_samples)
    if n_channels < 2 or len(lines) < n_channels + 1 or fs <= 0 or n_samples <= 0:
        raise ValueError(f'Invalid signal geometry: {path}')
    channels=[]
    for line in lines[1:1+n_channels]:
        tokens=line.split()
        if len(tokens) < 9: raise ValueError(f'Malformed signal line: {line}')
        gm=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(?:\(([-+]?\d+)\))?/([^\s]+)',tokens[2],flags=re.I)
        if gm is None: raise ValueError(f'Unrecognized ADC gain token: {tokens[2]}')
        gain=float(gm.group(1)); zero=int(tokens[4]); baseline=int(gm.group(2)) if gm.group(2) is not None else zero
        if gain <= 0: raise ValueError('Invalid ADC gain')
        channels.append({'name':tokens[-1], 'gain':gain, 'baseline':baseline, 'unit':gm.group(3)})
    return {'name':name,'n_channels':n_channels,'fs':fs,'n_samples':n_samples,'channels':channels}


def read_waveform(record_prefix: Path):
    h = parse_header(record_prefix.with_suffix('.hea'))
    if abs(h['fs']-FS_EXPECTED)>1e-6: raise ValueError('Unexpected sampling rate')
    val = loadmat(str(record_prefix.with_suffix('.mat')))['val']
    if val.ndim != 2 or val.shape != (h['n_channels'],h['n_samples']):
        raise ValueError(f'Waveform does not match .hea geometry: {val.shape}')
    out=[]
    for i, ch in enumerate(h['channels']):
        # Verified per WFDB: physical = (digital - baseline) / gain.
        out.append((val[i].astype(np.float64) - ch['baseline'])/ch['gain'])
    return np.stack(out, axis=1), h


def is_ecg_channel(name: str) -> bool:
    up=name.upper().replace(' ','').replace('-','')
    if any(x in up for x in ['PLETH','RESP','ABP','PAP','ART','PRESS','CO2']): return False
    return up in {'I','II','III','V','AVR','AVL','AVF','V1','V2','V3','V4','V5','V6','MCL','MCL1','MLII'} or 'ECG' in up


def lead_features(x: np.ndarray, fs: float) -> dict:
    """Quality and rough R-peak candidate statistics, not VT diagnosis."""
    x=np.asarray(x,dtype=float)
    if len(x)<int(5*fs) or not np.all(np.isfinite(x)):
        raise ValueError('Not enough finite samples')
    p5,p95=np.percentile(x,[5,95])
    spread=float(p95-p5)
    dx=np.diff(x)
    flat=float(np.mean(dx==0))
    # Dropout and artifact summaries. Values are NOT diagnostic clinical cutoffs.
    mad=float(np.median(np.abs(x-np.median(x))))
    dmad=float(np.median(np.abs(dx-np.median(dx))))
    try:
        sos=butter(3,[5,25],fs=fs,btype='bandpass',output='sos')
        band=sosfiltfilt(sos,x)
        envelope=np.abs(band)
        # Normalized prominence is a research feature, not a validated R-peak detector.
        prom=max(float(np.median(envelope)*2.0),float(np.percentile(envelope,75)-np.percentile(envelope,25)))
        peaks,_=find_peaks(envelope,distance=max(1,int(fs*.28)),prominence=prom)
        rr=np.diff(peaks)/fs
        valid_rr=rr[(rr>.25)&(rr<2.5)]
        peak_rate=float(len(peaks)/(len(x)/fs)*60.0)
        rr_median=float(np.median(valid_rr)) if len(valid_rr)>=3 else np.nan
        rr_cv=float(np.std(valid_rr)/np.mean(valid_rr)) if len(valid_rr)>=3 else np.nan
    except (ValueError, FloatingPointError):
        peak_rate=rr_median=rr_cv=np.nan
    return {'spread_5_95':spread,'mad':mad,'diff_mad':dmad,'flat_fraction':flat,
            'candidate_peak_rate':peak_rate,'rr_median':rr_median,'rr_cv':rr_cv}


def features_for_record(prefix: Path) -> dict:
    sig,h=read_waveform(prefix)
    fs=h['fs']
    if len(sig)<int(ALARM_TIME_S*fs): raise ValueError('Record too short for pre-alarm window')
    stop=int(ALARM_TIME_S*fs)
    start=stop-int(FEATURE_SECONDS*fs)
    if start<0: raise ValueError('Negative prealarm window')
    ecg=[i for i,ch in enumerate(h['channels']) if is_ecg_channel(ch['name'])]
    if len(ecg)<2: raise ValueError('Expected two ECG leads from challenge')
    # Hard block against retrospective leakage: always <= 300 seconds.
    if stop>int(ALARM_TIME_S*fs): raise AssertionError('Post-alarm leakage')
    out={}
    for j,i in enumerate(ecg[:2]):
        f=lead_features(sig[start:stop,i],fs)
        for k,v in f.items(): out[f'lead{j}_{k}']=v
    out['lead_diff_mad_abs']=abs(out['lead0_diff_mad']-out['lead1_diff_mad'])
    return out


def extract(dataset: Path, max_records: int|None = None):
    ix=parse_alarm_index(dataset/'ALARMS')
    vt=ix[ix.alarm.eq(ALARM)].copy().sort_values('record')
    if max_records is not None: vt=vt.head(max_records)
    records=[]; errors=[]
    for row in vt.itertuples(index=False):
        prefix=dataset/row.record
        try:
            feats=features_for_record(prefix)
            records.append({'record':row.record,'true_alarm':int(row.true_alarm),**feats})
        except (OSError,KeyError,ValueError,IndexError) as exc:
            errors.append({'record':row.record,'error':str(exc)})
    return pd.DataFrame(records),errors,int(len(vt)),{int(k):int(v) for k,v in vt.true_alarm.value_counts().items()}


def evaluate(df:pd.DataFrame, seed=RANDOM_STATE):
    if len(df)<40 or df.true_alarm.nunique()!=2:
        raise ValueError('Not enough varied records for an exploratory split')
    X=df.drop(columns=['record','true_alarm'])
    y=df.true_alarm.astype(int).to_numpy()
    splitter=StratifiedShuffleSplit(n_splits=1,test_size=.30,random_state=seed)
    a,b=next(splitter.split(X,y))
    assert not set(df.record.iloc[a])&set(df.record.iloc[b])
    if len(set(y[a]))<2 or len(set(y[b]))<2: raise ValueError('Split missing a class')
    # Do not fit preprocessing or thresholds on the test partition.
    model=make_pipeline(SimpleImputer(strategy='median'),StandardScaler(),
            LogisticRegression(max_iter=2000,class_weight='balanced',random_state=seed))
    model.fit(X.iloc[a],y[a])
    score=model.predict_proba(X.iloc[b])[:,1]
    pred=(score>=.5).astype(int) # uncalibrated, fixed exploratory comparator
    tn,fp,fn,tp=map(int,confusion_matrix(y[b],pred,labels=[0,1]).ravel())
    return {
        'interpretation':'record-disjoint EXPLORATORY benchmark only; patient independence unknown',
        'n_train':len(a),'n_test':len(b),'tp':tp,'tn':tn,'fp':fp,'fn':fn,
        'sensitivity':float(recall_score(y[b],pred,zero_division=0)),
        'specificity':tn/(tn+fp) if tn+fp else None,
        'precision':float(precision_score(y[b],pred,zero_division=0)),
        'balanced_accuracy':float(balanced_accuracy_score(y[b],pred)),
        'average_precision':float(average_precision_score(y[b],score)),
        'seed':seed,'post_alarm_data_used':False,
        'clinical_or_driver_validation':False
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--training-dir',required=True,type=Path)
    p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--max-records',type=int,default=None)
    p.add_argument('--evaluate-exploratory',action='store_true',
         help='Explicit acknowledgment: record split does NOT establish patient independence')
    args=p.parse_args()
    if not (args.training_dir/'ALARMS').exists():
        p.error('training-dir must contain original ALARMS plus .hea and .mat records')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    table,errors,n,counts=extract(args.training_dir,args.max_records)
    table.to_csv(args.output_dir/'vt_features.csv',index=False)
    info={'source':'PhysioNet Challenge 2015 version 1.0.0',
      'source_url':'https://physionet.org/content/challenge-2015/1.0.0/',
      'task':'VT alarm truth verification, NOT cardiac incapacitation',
      'n_vt_records_indexed':n,'true_false_index_counts':counts,
      'n_features_extracted':len(table),'n_failed_records':len(errors),'errors':errors,
      'pre_alarm_only':True,'window_seconds':FEATURE_SECONDS,'feature_end_second':ALARM_TIME_S,
      'external_dataset_not_redistributed':True,
      'dataset_metadata_sha256':hashlib.sha256((args.training_dir/'ALARMS').read_bytes()).hexdigest()}
    if args.evaluate_exploratory:
        if len(table)>39: info['model_evaluation']=evaluate(table)
        else: info['model_evaluation']='not run: fewer than 40 valid records'
    else:
        info['model_evaluation']='not run: must explicitly request record-disjoint exploratory evaluation'
    (args.output_dir/'evidence.json').write_text(json.dumps(info,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in info.items() if k!='errors'},indent=2))

if __name__=='__main__': main()
