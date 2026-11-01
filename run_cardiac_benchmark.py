"""Complete pre-alarm benchmark. Run --help for external data configuration."""
import argparse
import importlib.metadata
import json
import os
import platform
import time
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve, auc
from cardiac_audit import audit,sha
from cardiac_signal import (SEED,ALARMS,load_pre_alarm,prepare,extract_prepared,decision,rule,model_score)

def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')

def metrics(y,p,scores=None,abstain=None):
    y=np.asarray(y);p=np.asarray(p)
    tp=int(((y==1)&(p==1)).sum());tn=int(((y==0)&(p==0)).sum())
    fp=int(((y==0)&(p==1)).sum());fn=int(((y==1)&(p==0)).sum())
    div=lambda a,b:float(a/b) if b else None
    se=div(tp,tp+fn);sp=div(tn,tn+fp)
    result=dict(n=len(y),true=int(y.sum()),false=int(len(y)-y.sum()),tp=tp,fp=fp,tn=tn,fn=fn,
        sensitivity=se,specificity=sp,precision=div(tp,tp+fp),f1=div(2*tp,2*tp+fp+fn),
        balanced_accuracy=(se+sp)/2 if se is not None and sp is not None else None,
        false_alarm_suppression_rate=sp,true_alarms_suppressed=fn,true_alarms_suppressed_percent=div(100*fn,tp+fn),
        challenge_score=div(100*(tp+tn),tp+tn+fp+5*fn),
        abstention_rate=float(np.mean(abstain)) if abstain is not None else 0.)
    if scores is not None and len(np.unique(y))==2:
        precision,recall,_=precision_recall_curve(y,scores)
        result.update(roc_auc=float(roc_auc_score(y,scores)),average_precision=float(average_precision_score(y,scores)),pr_auc=float(auc(recall,precision)))
    return result

def intervals(y,p,scores,abstain,seed=SEED):
    # Conditional record bootstrap, stratified by truth to preserve the case mix.
    rng=np.random.default_rng(seed);y=np.asarray(y);p=np.asarray(p);abstain=np.asarray(abstain)
    groups=[np.flatnonzero(y==v) for v in (0,1)]
    vals={}
    for _ in range(1000):
        ix=np.concatenate([rng.choice(g,len(g),replace=True) for g in groups])
        m=metrics(y[ix],p[ix],None if scores is None else np.asarray(scores)[ix],abstain[ix])
        for k,v in m.items():
            if v is not None and k not in {'n','true','false','tp','fp','tn','fn','true_alarms_suppressed'}: vals.setdefault(k,[]).append(v)
    return {k:np.percentile(v,[2.5,97.5]).tolist() for k,v in vals.items()}

def make_splits(df):
    strat=df.alarm+'_'+df.true_alarm.astype(str)
    train,test=train_test_split(np.arange(len(df)),test_size=.30,random_state=SEED,stratify=strat)
    folds=np.full(len(df),-1)
    for fold,(_,valid) in enumerate(StratifiedKFold(3,shuffle=True,random_state=SEED).split(train,strat.iloc[train])):
        folds[train[valid]]=fold
    assert not set(df.record.iloc[train])&set(df.record.iloc[test])
    return train,test,folds

def model(C):
    return make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler(),
        LogisticRegression(C=C,class_weight='balanced',max_iter=2000,random_state=SEED))

def select_threshold(y,score,features,mode):
    rows=[]
    for th in np.linspace(0,1,101):
        ds=[decision(s,f,mode,float(th)) for s,f in zip(score,features)]
        rows.append(dict(threshold=float(th),**metrics(y,[d['preserve_alarm'] for d in ds],abstain=[d['abstain'] for d in ds])))
    feasible=[r for r in rows if r['sensitivity']>=.98]
    # Fixed objective and tie-breaker chosen before held-out evaluation.
    selected=max(feasible,key=lambda r:(r['challenge_score'],r['specificity'],-r['threshold']))
    return selected,rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--training-dir',required=True,type=Path)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path('results/cardiac'))
    args=parser.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    ix,manifest,audit_report=audit(args.training_dir,args.archive,out)
    print('Audit:',audit_report['n_valid'],'valid /',audit_report['n_indexed'],flush=True)
    records=[];latency=[];failures=[]
    for item in manifest:
        if item['status']!='ok':continue
        row={k:item[k] for k in ('record','alarm','true_alarm')}
        t=time.perf_counter()
        try:
            signals,fs,names,units=load_pre_alarm(args.training_dir/item['record']);t1=time.perf_counter()
            prepared=prepare(signals,fs,names,units);t2=time.perf_counter()
            f=extract_prepared(prepared,fs,item['alarm']);t3=time.perf_counter()
            row.update(f)
            latency.append(dict(record=item['record'],load_ms=(t1-t)*1000,preprocess_ms=(t2-t1)*1000,feature_ms=(t3-t2)*1000))
        except Exception as exc:
            # Keep failed valid records in evaluation, with all scores gated to preserve.
            failures.append(dict(record=item['record'],reason=str(exc)))
            dummy=np.zeros((75000,0));row.update(extract_prepared([],250,item['alarm']))
        records.append(row)
    df=pd.DataFrame(records);df.to_csv(out/'features.csv',index=False)
    train,test,folds=make_splits(df)
    splits=df[['record','alarm','true_alarm']].copy();splits['partition']='development';splits.loc[test,'partition']='test';splits['cv_fold']=folds
    splits.to_csv(out/'splits.csv',index=False)
    pd.DataFrame(latency).to_csv(out/'latency.csv',index=False)
    y=df.true_alarm.to_numpy();fl=df.to_dict('records');predictions=[];results={};selections={};cv_rows=[];threshold_rows=[];artifacts={}
    methods={'always_preserve':([1]*len(test),[False]*len(test),None),
        'pulse_rule':([rule(fl[i],df.alarm.iloc[i])['preserve_alarm'] for i in test],
                      [rule(fl[i],df.alarm.iloc[i])['abstain'] for i in test],None)}
    for mode in ('ecg','multimodal'):
        cols=[c for c in df.columns if c.startswith(('ecg','alarm_')) or (mode=='multimodal' and c.startswith(('pulse','rate_disagreement')))]
        X=df[cols];candidates=[]
        for C in (.1,1.,10.):
            oof=np.full(len(train),np.nan)
            for fold in range(3):
                fit=train[folds[train]!=fold];valid=train[folds[train]==fold]
                clf=model(C).fit(X.iloc[fit],y[fit])
                oof[folds[train]==fold]=clf.predict_proba(X.iloc[valid])[:,1]
            candidates.append((float(roc_auc_score(y[train],oof)),C,oof))
        _,C,oof=max(candidates,key=lambda c:(c[0],-c[1]))
        selected,tradeoff=select_threshold(y[train],oof,[fl[i] for i in train],mode)
        selections[mode]=dict(C=C,threshold=selected['threshold'],oof_operating_metrics=selected,
            candidates=[dict(C=c,roc_auc=a) for a,c,_ in candidates],sensitivity_target=.98,
            selection='3-fold development OOF AUC selects C; OOF constrained score selects threshold; fixed 0.05 uncertainty band',
            nontrivial_suppression=selected['tn']>0)
        cv_rows.extend(dict(mode=mode,record=df.record.iloc[i],true_alarm=int(y[i]),score=float(s)) for i,s in zip(train,oof))
        threshold_rows.extend(dict(mode=mode,**r) for r in tradeoff)
        clf=model(C).fit(X.iloc[train],y[train]);imputer,scaler,lr=clf.steps[0][1],clf.steps[1][1],clf.steps[2][1]
        a=dict(schema='cabinguard-logistic-v1',mode=mode,features=cols,impute=imputer.statistics_.tolist(),mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),coef=lr.coef_[0].tolist(),intercept=float(lr.intercept_[0]),threshold=selected['threshold'],C=C,seed=SEED,calibrated=False)
        dump(out/f'model_{mode}.json',a);artifacts[mode]=a
        scores=np.array([model_score(a,fl[i]) for i in test])
        np.testing.assert_allclose(scores,clf.predict_proba(X.iloc[test])[:,1],rtol=1e-10,atol=1e-12)
        ds=[decision(s,fl[i],mode,a['threshold']) for s,i in zip(scores,test)]
        methods[mode]=([d['preserve_alarm'] for d in ds],[d['abstain'] for d in ds],scores)
        # Descriptive held-out threshold curves: never feed back into selection.
        test_curve=[]
        for th in np.linspace(0,1,21):
            decisions=[decision(s,fl[i],mode,float(th)) for s,i in zip(scores,test)]
            test_curve.append(dict(threshold=float(th),**metrics(y[test],[d['preserve_alarm'] for d in decisions],abstain=[d['abstain'] for d in decisions])))
        pd.DataFrame(test_curve).to_csv(out/f'test_threshold_{mode}.csv',index=False)
    pd.DataFrame(cv_rows).to_csv(out/'development_oof.csv',index=False)
    pd.DataFrame(threshold_rows).to_csv(out/'development_thresholds.csv',index=False)
    per_alarm=[]
    for name,(pred,abstain,scores) in methods.items():
        pred=np.asarray(pred);abstain=np.asarray(abstain)
        m=metrics(y[test],pred,scores,abstain)
        m['ci95']=intervals(y[test],pred,scores,abstain)
        results[name]=m
        for a in ALARMS:
            mask=df.alarm.iloc[test].eq(a).to_numpy()
            per_alarm.append(dict(method=name,alarm=a,**metrics(y[test][mask],pred[mask],None if scores is None else scores[mask],abstain[mask])))
        for pos,i in enumerate(test):
            predictions.append(dict(method=name,record=df.record.iloc[i],alarm=df.alarm.iloc[i],true_alarm=int(y[i]),preserve_alarm=int(pred[pos]),abstain=bool(abstain[pos]),score=None if scores is None else float(scores[pos])))
    pd.DataFrame(predictions).to_csv(out/'test_predictions.csv',index=False)
    pd.DataFrame(per_alarm).to_csv(out/'per_alarm.csv',index=False)
    pd.DataFrame([{k:v for k,v in m.items() if k!='ci95'}|{'method':name} for name,m in results.items()]).to_csv(out/'comparison.csv',index=False)
    # Time pure JSON model execution record by record, 10 passes on the held-out population.
    model_times=[]
    for _ in range(10):
        for i in test:
            t=time.perf_counter();model_score(artifacts['multimodal'],fl[i]);model_times.append((time.perf_counter()-t)*1000)
    pd.DataFrame({'model_ms':model_times}).to_csv(out/'model_latency.csv',index=False)
    timing={k:dict(median=float(np.median([r[k] for r in latency])),p95=float(np.percentile([r[k] for r in latency],95))) for k in ('load_ms','preprocess_ms','feature_ms')}
    timing['model_ms']=dict(median=float(np.median(model_times)),p95=float(np.percentile(model_times,95)))
    env=dict(python=platform.python_version(),os=platform.platform(),processor=platform.processor(),logical_cpus=os.cpu_count(),
        packages={p:importlib.metadata.version(p) for p in ['numpy','scipy','pandas','scikit-learn','wfdb','matplotlib']})
    dump(out/'environment.json',env)
    report=dict(seed=SEED,task='Internal public-training ICU alarm verification; positive=TRUE alarm',n_processed=len(df),n_excluded=len(audit_report['exclusions']),feature_failures=failures,n_train=len(train),n_test=len(test),
        patient_disjoint=False,post_alarm_used=False,models=results,selection=selections,timing=timing,
        interval_method='1000 truth-stratified record bootstrap percentile 95% intervals; conditional on fixed model/split and observed case mix; patient dependence unresolved; zero observed errors may produce degenerate intervals',
        primary_model='multimodal (predeclared, no held-out winner selection)',split_sha256=sha(out/'splits.csv'))
    dump(out/'benchmark.json',report)
    dump(out/'config.json',dict(seed=SEED,test_size=.3,cv_folds=3,C_grid=[.1,1,10],uncertainty_band=.05,threshold_grid='0:0.01:1',sensitivity_target=.98,bootstrap=1000))
    plot(out,results)
    print(json.dumps(report,indent=2),flush=True)

def plot(out,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,4,figsize=(11,2.8))
    for axis,(name,m) in zip(ax,results.items()):
        a=np.array([[m['tn'],m['fp']],[m['fn'],m['tp']]])
        axis.imshow(a,cmap='Blues',vmin=0,vmax=150)
        for (i,j),v in np.ndenumerate(a):axis.text(j,i,str(v),ha='center',va='center')
        axis.set(title=name,xticks=[0,1],xticklabels=['Suppress','Preserve'],yticks=[0,1],yticklabels=['False','True'])
    fig.tight_layout();fig.savefig(out/'confusion_matrices.png',dpi=180);plt.close(fig)
    fig,ax=plt.subplots(figsize=(5,3))
    for mode in ('ecg','multimodal'):
        d=pd.read_csv(out/f'test_threshold_{mode}.csv');ax.plot(d.sensitivity,d.specificity,'o-',label=mode)
    ax.set(xlabel='True-alarm sensitivity',ylabel='False-alarm suppression',title='Held-out descriptive tradeoff (not used for tuning)',xlim=(0,1.03),ylim=(0,1.03));ax.legend();fig.tight_layout();fig.savefig(out/'threshold_tradeoff.png',dpi=180);plt.close(fig)

if __name__=='__main__':main()
