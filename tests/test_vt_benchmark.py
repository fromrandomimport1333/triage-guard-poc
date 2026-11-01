from pathlib import Path
import numpy as np
import pytest
from scipy.io import savemat
from physionet2015_vt_benchmark import (
    parse_alarm_index,parse_header,read_waveform,lead_features,features_for_record,
    is_ecg_channel,evaluate
)
import pandas as pd


def make_record(tmp_path, name='v111l'):
    fs=250; n=int(330*fs)
    t=np.arange(n)/fs
    # Explicitly synthetic ECG-like waveforms, not patient signal.
    y1=np.sin(2*np.pi*1.8*t)*.7
    y2=np.sin(2*np.pi*1.8*t)*.55
    y3=np.cos(2*np.pi*.9*t)*.1
    dig=np.stack([np.round(y1*1000),np.round(y2*1000),np.round(y3*1000)],axis=0).astype('int16')
    savemat(tmp_path/f'{name}.mat',{'val':dig})
    (tmp_path/f'{name}.hea').write_text(f'{name} 3 {fs} {n}\n'
       f'{name}.mat 16+24 1000/mV 16 0 0 0 0 II\n'
       f'{name}.mat 16+24 1000/mV 16 0 0 0 0 V\n'
       f'{name}.mat 16+24 1000/NU 16 0 0 0 0 PLETH\n'
       '#Ventricular_Tachycardia\n#False alarm\n')
    return tmp_path/name


def test_alarm_index_and_true_false(tmp_path):
    (tmp_path/'ALARMS').write_text('v111l,Ventricular_Tachycardia,0\nv131l,Ventricular_Tachycardia,1\n')
    ix=parse_alarm_index(tmp_path/'ALARMS')
    assert ix.shape==(2,3)
    assert ix.true_alarm.tolist()==[0,1]


def test_alarm_index_rejects_malformed(tmp_path):
    (tmp_path/'ALARMS').write_text('v111l,Ventricular_Tachycardia,maybe\n')
    with pytest.raises(ValueError):parse_alarm_index(tmp_path/'ALARMS')


def test_header_and_signal_scaling(tmp_path):
    p=make_record(tmp_path)
    z,h=read_waveform(p)
    assert h['fs']==250 and z.shape==(82500,3)
    assert abs(z[10,0]-(np.round(np.sin(2*np.pi*1.8*10/250)*.7*1000)/1000))<1e-9


def test_excludes_pleth_from_ecg():
    assert is_ecg_channel('II') and is_ecg_channel('V')
    assert not is_ecg_channel('PLETH')
    assert not is_ecg_channel('ABP')


def test_pre_alarm_ignores_after_alarm_data(tmp_path):
    p=make_record(tmp_path)
    f1=features_for_record(p)
    d=savemat
    from scipy.io import loadmat
    raw=loadmat(str(p)+'.mat')['val']
    raw[:,75000:]=np.iinfo(np.int16).max
    savemat(str(p)+'.mat',{'val':raw})
    f2=features_for_record(p)
    assert all(np.isclose(f1[k],f2[k],equal_nan=True) for k in f1)


def test_rejects_missing_ecg_or_incomplete_record(tmp_path):
    p=make_record(tmp_path)
    h=(tmp_path/'v111l.hea').read_text().replace(' 82500\n',' 20000\n')
    (tmp_path/'v111l.hea').write_text(h)
    with pytest.raises(ValueError): features_for_record(p)


def test_flat_signal_yields_flatline_feature():
    f=lead_features(np.zeros(5000),250)
    assert f['flat_fraction']==1.0


def test_eval_record_disjoint_and_explicit_scope():
    rng=np.random.default_rng(4)
    n=80
    x=pd.DataFrame({'record':[f'v{i:03d}l' for i in range(n)],
        'true_alarm':[0,1]*(n//2),
        'lead0_mad':rng.normal(size=n),
        'lead1_mad':rng.normal(size=n)})
    out=evaluate(x)
    assert out['n_train']+out['n_test']==80
    assert not out['clinical_or_driver_validation']
    assert out['tp']+out['tn']+out['fp']+out['fn']==out['n_test']
