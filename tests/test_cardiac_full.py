import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
import cardiac_signal as cs
from cardiac_integration import attach_cardiac
from strict_safety_policy import strict_decide
from tests.test_temporal_assurance import obs
from run_cardiac_benchmark import metrics,make_splits

@pytest.fixture
def signal():
    t=np.arange(82500)/250
    return np.stack([np.sin(2*np.pi*1.3*t),np.sin(2*np.pi*1.3*t+.2),np.sin(2*np.pi*1.3*t)],axis=1)

@pytest.fixture
def artifact(tmp_path):
    names=['alarm_Asystole'];a=dict(schema='cabinguard-logistic-v1',mode='multimodal',features=names,impute=[0],mean=[0],scale=[1],coef=[1],intercept=0,threshold=.4)
    p=tmp_path/'model.json';p.write_text(json.dumps(a));return p

def getf(signal):return cs.features(signal,250,['II','V','PLETH'],['mV','mV','NU'],'Asystole')

def test_full_features_and_prediction_ignore_future(signal):
    a=getf(signal);signal[75000:]=np.nan;b=getf(signal)
    np.testing.assert_allclose(list(a.values()),list(b.values()),equal_nan=True)
    assert cs.decision(.2,a,'multimodal',.4)==cs.decision(.2,b,'multimodal',.4)

def test_wfdb_loader_cannot_read_future(monkeypatch):
    class H:fs=250;sig_len=82500;sig_name=['II'];units=['mV']
    class R:p_signal=np.zeros((75000,1))
    seen={}
    monkeypatch.setattr(cs.wfdb,'rdheader',lambda _:H())
    def read(*a,**kw):seen.update(kw);return R()
    monkeypatch.setattr(cs.wfdb,'rdrecord',read);cs.load_pre_alarm('unused')
    assert seen['sampto']==75000 and seen['sampfrom']==0

@pytest.mark.parametrize('fault',['missing_ecg','missing_pulse','nonfinite','flat','unphysiological','conflict','uncertain'])
def test_faults_preserve_alarm(signal,fault):
    names=['II','V','PLETH'];units=['mV','mV','NU']
    if fault=='missing_ecg':names=['RESP','RESP','PLETH']
    if fault=='missing_pulse':names[-1]='RESP'
    if fault=='nonfinite':signal[70000,0:2]=np.nan
    if fault=='flat':signal[:75000]=0
    if fault=='unphysiological':signal[:75000,:2]*=1000
    f=cs.features(signal,250,names,units,'Asystole')
    if fault=='conflict':f['rate_disagreement']=100
    d=cs.decision(.4 if fault=='uncertain' else .1,f,'multimodal',.4)
    assert d['preserve_alarm'] and d['abstain']

@pytest.mark.parametrize('fault',['loading','truncated','corrupt_artifact','invalid_artifact','timeout','model_tamper','input_tamper'])
def test_inference_failures(signal,artifact,monkeypatch,fault):
    if fault=='loading':
        def fail(_):raise OSError('controlled load failure')
        monkeypatch.setattr(cs,'load_pre_alarm',fail)
    else:monkeypatch.setattr(cs,'load_pre_alarm',lambda _:(signal[:100] if fault=='truncated' else signal,250,['II','V','PLETH'],['mV','mV','NU']))
    if fault=='corrupt_artifact':artifact.write_text('not JSON')
    if fault=='invalid_artifact':
        a=json.loads(artifact.read_text());a['scale']=[0];artifact.write_text(json.dumps(a))
    if fault=='input_tamper':artifact.with_suffix('.mat').write_bytes(b'tampered waveform')
    d=cs.infer(artifact,'Asystole',artifact,deadline_ms=-1 if fault=='timeout' else 10000,
        expected_sha256='wrong' if fault=='model_tamper' else None,
        expected_input_sha256='wrong' if fault=='input_tamper' else None)
    assert d['preserve_alarm'] and d['abstain'] and d['score'] is None
    if fault=='input_tamper':assert 'input_digest_mismatch' in d['reason']
    if fault=='model_tamper':assert 'model_digest_mismatch' in d['reason']

def test_exported_model_prediction_ignores_future(signal):
    model_path=Path('results/cardiac/model_multimodal.json')
    if not model_path.exists():pytest.skip('requires executed benchmark artifact')
    a=cs.validate_artifact(json.loads(model_path.read_text()));f=getf(signal)
    score=cs.model_score(a,f);prediction=cs.decision(score,f,a['mode'],a['threshold'])
    signal[75000:]=1e30;g=getf(signal)
    assert cs.model_score(a,g)==score
    assert cs.decision(cs.model_score(a,g),g,a['mode'],a['threshold'])==prediction

def test_uncertain_cardio_cannot_authorize_vehicle():
    b=obs(10000);b=replace(b,hmi=replace(b.hmi,state='responded'))
    d=strict_decide(attach_cardiac(b,dict(abstain=True,preserve_alarm=True,score=.9)))
    assert not d.oem_evaluation_request and d.medical!='normal'

def test_false_icu_alarm_is_not_normal_driver():
    b=obs(10000);b=replace(b,hmi=replace(b.hmi,state='responded'))
    d=strict_decide(attach_cardiac(b,dict(abstain=False,preserve_alarm=False,score=.1)))
    assert d.medical!='normal' and not d.oem_evaluation_request

def test_metric_conventions():
    m=metrics([1,1,0,0],[1,0,1,0]);assert (m['tp'],m['fn'],m['fp'],m['tn'])==(1,1,1,1)
    assert m['challenge_score']==25 and m['sensitivity']==.5 and m['specificity']==.5

def test_deterministic_split_no_record_crossing():
    import pandas as pd
    df=pd.DataFrame([dict(record=f'{a}_{y}_{i}',alarm=a,true_alarm=y) for a in cs.ALARMS for y in [0,1] for i in range(15)])
    a,b,f=make_splits(df);a2,b2,f2=make_splits(df)
    np.testing.assert_array_equal(a,a2);np.testing.assert_array_equal(b,b2);np.testing.assert_array_equal(f,f2)
    assert not set(a)&set(b) and set(f[b])=={-1}
