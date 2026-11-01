"""Pre-alarm ICU alarm verification features; no diagnosis or actuator authority."""
from pathlib import Path
import json
import time
import numpy as np
import wfdb
from scipy.signal import butter, sosfilt, find_peaks, welch
from scipy.special import expit
from physionet2015_vt_benchmark import is_ecg_channel

ALARMS = ['Asystole', 'Bradycardia', 'Tachycardia', 'Ventricular_Tachycardia', 'Ventricular_Flutter_Fib']
SEED = 20261030
BOUNDARY = 300
STATS = ['spread', 'flat', 'rate', 'rr_cv', 'max_gap', 'spectral_entropy', 'high_power']

def load_pre_alarm(prefix):
    h = wfdb.rdheader(str(prefix))
    if h.fs != 250 or h.sig_len < int(BOUNDARY*h.fs):
        raise ValueError('unexpected frequency or truncated pre-alarm waveform')
    # The waveform loader itself cannot return future samples.
    r = wfdb.rdrecord(str(prefix), sampfrom=0, sampto=int(BOUNDARY*h.fs), physical=True)
    return r.p_signal, h.fs, h.sig_name, h.units

def prepare(signals, fs, names, units):
    if fs != 250 or signals.ndim != 2 or len(signals) < int(BOUNDARY*fs):
        raise ValueError('invalid pre-alarm geometry')
    if signals.shape[1] != len(names) or len(names) != len(units):
        raise ValueError('invalid channel metadata')
    # Truncate BEFORE normalization, filtering, quality calculations or windowing.
    x = np.asarray(signals[:int(BOUNDARY*fs)], dtype=float)[int(270*fs):].copy()
    prepared = []
    for i, (name, unit) in enumerate(zip(names, units)):
        kind = 'ecg' if is_ecg_channel(name) else ('pulse' if name.upper() in {'ABP','ART','PLETH'} else None)
        if kind is None:
            continue
        v=x[:,i]
        valid = bool(np.isfinite(v).all())
        if not valid:
            prepared.append((kind,v,np.zeros_like(v),False))
            continue
        if kind=='ecg':
            valid &= unit=='mV' and np.nanmax(np.abs(v)) <= 20
        elif name.upper() in {'ABP','ART'}:
            valid &= unit=='mmHg' and np.nanmin(v)>=-20 and np.nanmax(v)<=350
        else:
            valid &= unit in {'NU','mV',''}
        spread=float(np.nanpercentile(v,95)-np.nanpercentile(v,5))
        flat=float(np.mean(np.diff(v)==0))
        valid &= spread>1e-6 and flat<.95
        if valid:
            band=(5,25) if kind=='ecg' else (.5,8)
            filtered=sosfilt(butter(3,band,fs=fs,btype='bandpass',output='sos'), v-np.median(v))
        else:
            filtered=np.zeros_like(v)
        prepared.append((kind, v, filtered, valid))
    return prepared

def stats(raw, filtered, fs, kind):
    envelope=np.abs(filtered) if kind=='ecg' else filtered
    prominence=max(1e-9, float(np.percentile(envelope,75)-np.percentile(envelope,25)))
    peaks,_=find_peaks(envelope, distance=int(fs*.25), prominence=prominence)
    rr=np.diff(peaks)/fs
    freq,power=welch(filtered,fs,nperseg=min(len(filtered),1024))
    normalized=power/(power.sum()+1e-30)
    return dict(spread=float(np.percentile(raw,95)-np.percentile(raw,5)),
        flat=float(np.mean(np.diff(raw)==0)), rate=float(len(peaks)*60/(len(raw)/fs)),
        rr_cv=float(np.std(rr)/np.mean(rr)) if len(rr)>2 else np.nan,
        max_gap=float(np.max(np.diff(np.r_[0,peaks,len(raw)])/fs)),
        spectral_entropy=float(-np.sum(normalized*np.log(normalized+1e-30))/np.log(len(power))),
        high_power=float(normalized[freq>15].sum()))

def extract_prepared(prepared, fs, alarm):
    if alarm not in ALARMS:
        raise ValueError('unknown alarm type')
    out={f'alarm_{a}':float(a==alarm) for a in ALARMS}
    ecg=[c for c in prepared if c[0]=='ecg'][:2]
    pulse=[c for c in prepared if c[0]=='pulse']
    # Fixed choice: first usable pulsatile channel in native header order.
    pulse=sorted(pulse,key=lambda c:not c[3])[:1]
    for prefix,c in [('ecg0',ecg[0] if ecg else None),('ecg1',ecg[1] if len(ecg)>1 else None),('pulse',pulse[0] if pulse else None)]:
        out[prefix+'_valid']=float(c is not None and c[3])
        for duration in (30,10):
            values=stats(c[1][-duration*int(fs):],c[2][-duration*int(fs):],fs,c[0]) if c is not None and c[3] else dict.fromkeys(STATS,np.nan)
            out.update({f'{prefix}_{duration}_{k}':v for k,v in values.items()})
    out['rate_disagreement']=abs(np.nanmean([out['ecg0_10_rate'],out['ecg1_10_rate']])-out['pulse_10_rate']) if out['ecg0_valid'] or out['ecg1_valid'] else np.nan
    return out

def features(signals,fs,names,units,alarm):
    return extract_prepared(prepare(signals,fs,names,units),fs,alarm)

def quality_reasons(f, mode):
    reasons=[]
    if not (f['ecg0_valid'] or f['ecg1_valid']): reasons.append('missing_or_invalid_ecg')
    if mode=='multimodal':
        if not f['pulse_valid']: reasons.append('missing_or_invalid_pulse')
        if np.isfinite(f['rate_disagreement']) and f['rate_disagreement']>40: reasons.append('modality_rate_conflict')
    return reasons

def decision(score, f, mode, threshold):
    reasons=quality_reasons(f,mode)
    if not np.isfinite(score): reasons.append('invalid_score')
    elif abs(score-threshold)<=.05: reasons.append('threshold_uncertainty')
    abstain=bool(reasons)
    return dict(preserve_alarm=bool(abstain or score>=threshold),abstain=abstain,
                reason=','.join(reasons) or 'model_decision',score=float(score) if np.isfinite(score) else None)

def rule(f,alarm):
    # Deliberately conservative rate heuristic. Never suppress VT/VF on rate alone.
    reasons=quality_reasons(f,'multimodal')
    hr=f['pulse_10_rate']; cv=f['pulse_10_rr_cv']; gap=f['pulse_10_max_gap']
    stable=np.isfinite(cv) and cv<.2 and 45<=hr<=130 and gap<2
    suppress=not reasons and stable and alarm in {'Asystole','Bradycardia','Tachycardia'}
    return dict(preserve_alarm=not suppress,abstain=bool(reasons),reason=','.join(reasons) or 'fixed_pulse_rate_rule')

def validate_artifact(a):
    if a['schema']!='cabinguard-logistic-v1' or a['mode'] not in {'ecg','multimodal'}: raise ValueError('invalid model schema')
    n=len(a['features'])
    if n==0 or len(set(a['features']))!=n: raise ValueError('invalid feature schema')
    for key in ['impute','mean','scale','coef']:
        z=np.asarray(a[key],float)
        if z.shape!=(n,) or not np.isfinite(z).all(): raise ValueError('invalid fitted array')
    if np.any(np.array(a['scale'])<=0) or not np.isfinite(a['intercept']) or not 0<=a['threshold']<=1: raise ValueError('invalid model parameters')
    return a

def model_score(a,f):
    z=np.array([f[k] for k in a['features']],float)
    z=np.where(np.isnan(z),a['impute'],z)
    return float(expit(np.dot((z-a['mean'])/a['scale'],a['coef'])+a['intercept']))

def infer(prefix,alarm,artifact_path,deadline_ms=1000,expected_sha256=None,expected_input_sha256=None):
    """Soft deadline checked after processing. Not a hard process watchdog."""
    import hashlib
    start=time.perf_counter(); times={}
    try:
        raw=Path(artifact_path).read_bytes()
        if expected_sha256 and hashlib.sha256(raw).hexdigest()!=expected_sha256: raise ValueError('model_digest_mismatch')
        a=validate_artifact(json.loads(raw))
        if expected_input_sha256:
            with Path(prefix).with_suffix('.mat').open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=expected_input_sha256: raise ValueError('input_digest_mismatch')
        t=time.perf_counter(); signals,fs,names,units=load_pre_alarm(prefix); times['load_ms']=(time.perf_counter()-t)*1000
        t=time.perf_counter(); prepared=prepare(signals,fs,names,units); times['preprocess_ms']=(time.perf_counter()-t)*1000
        t=time.perf_counter(); f=extract_prepared(prepared,fs,alarm); times['feature_ms']=(time.perf_counter()-t)*1000
        t=time.perf_counter(); p=model_score(a,f); times['model_ms']=(time.perf_counter()-t)*1000
        result=decision(p,f,a['mode'],a['threshold'])
        if (time.perf_counter()-start)*1000>deadline_ms: raise TimeoutError('prediction_deadline_exceeded')
    except Exception as exc:
        result=dict(preserve_alarm=True,abstain=True,score=None,reason=f'{type(exc).__name__}:{exc}')
    result['timing_ms']=times
    result['total_ms']=(time.perf_counter()-start)*1000
    return result
