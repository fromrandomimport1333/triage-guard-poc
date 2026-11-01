"""Independent v07 result audit; writes only results/scientific_audit.

Original predictions, fitted models and thresholds are never changed. Diagnostic
analyses of the already inspected test set are descriptive, not new validation.
"""
import argparse,hashlib,json,urllib.request,zipfile
from collections import Counter
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import beta,binomtest,rankdata
from scipy.signal import find_peaks
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from cardiac_signal import load_pre_alarm,prepare,features,model_score,decision,rule,is_ecg_channel

BASE=Path(__file__).resolve().parent/'results/cardiac'
OUT=Path(__file__).resolve().parent/'results/scientific_audit'

def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')

def exact_interval(k,n,alpha=.05):
    if n==0:return [None,None]
    return [0. if k==0 else float(beta.ppf(alpha/2,k,n-k+1)),1. if k==n else float(beta.ppf(1-alpha/2,k+1,n-k))]

def independent_metrics(y,p,score=None,abstain=None):
    y=np.asarray(y,dtype=int);p=np.asarray(p,dtype=int)
    tp=int(np.sum(y*p));fn=int(np.sum(y*(1-p)));tn=int(np.sum((1-y)*(1-p)));fp=int(np.sum((1-y)*p))
    ratio=lambda k,n:float(k/n) if n else None
    se=ratio(tp,tp+fn);sp=ratio(tn,tn+fp)
    m=dict(n=len(y),true=int(y.sum()),false=int(len(y)-y.sum()),tp=tp,fn=fn,tn=tn,fp=fp,
        sensitivity=se,specificity=sp,false_alarm_suppression_rate=sp,precision=ratio(tp,tp+fp),
        f1=ratio(2*tp,2*tp+fp+fn),balanced_accuracy=(se+sp)/2 if se is not None and sp is not None else None,
        challenge_score=ratio(100*(tp+tn),tp+tn+fp+5*fn),true_alarms_suppressed=fn,
        true_alarms_suppressed_percent=ratio(100*fn,tp+fn),
        abstention_rate=float(np.mean(abstain)) if abstain is not None and len(y) else 0.)
    if score is not None and len(np.unique(y))==2:
        score=np.asarray(score);rank=rankdata(score)
        m['roc_auc']=float((rank[y==1].sum()-y.sum()*(y.sum()+1)/2)/(y.sum()*(len(y)-y.sum())))
        order=np.argsort(-score,kind='stable');s=score[order];ys=y[order]
        ends=np.r_[np.flatnonzero(np.diff(s)!=0),len(s)-1]
        tp_curve=np.cumsum(ys)[ends];precision=tp_curve/(ends+1);recall=tp_curve/y.sum()
        m['average_precision']=float(np.sum(np.diff(np.r_[0.,recall])*precision))
        m['pr_auc']=float(np.trapezoid(np.r_[1.,precision],np.r_[0.,recall]))
    return m

def check_metrics(pred,b):
    checked={};intervals=[];per=[]
    for name,g in pred.groupby('method',sort=False):
        score=g.score.to_numpy() if g.score.notna().all() else None
        m=independent_metrics(g.true_alarm,g.preserve_alarm,score,g.abstain)
        for key,v in m.items():
            assert np.isclose(v,b['models'][name][key],atol=1e-12,rtol=1e-12),(name,key,v,b['models'][name][key])
        checked[name]=m
        for alarm,h in [('ALL',g),*list(g.groupby('alarm'))]:
            z=independent_metrics(h.true_alarm,h.preserve_alarm,abstain=h.abstain)
            per.append(dict(method=name,alarm=alarm,**z))
            for metric,k,n in [('sensitivity',z['tp'],z['tp']+z['fn']),('specificity',z['tn'],z['tn']+z['fp']),
                ('false_alarm_suppression',z['tn'],z['tn']+z['fp']),('precision',z['tp'],z['tp']+z['fp'])]:
                lo,hi=exact_interval(k,n);intervals.append(dict(method=name,alarm=alarm,metric=metric,successes=k,denominator=n,
                    estimate=k/n if n else None,ci_low=lo,ci_high=hi,method_ci='Clopper-Pearson 95%; record independence assumption'))
    save('baseline_metrics_verified.json',checked);pd.DataFrame(intervals).to_csv(OUT/'exact_intervals.csv',index=False)
    pd.DataFrame(per).to_csv(OUT/'per_alarm_verified.csv',index=False)
    return checked

def paired_comparisons(pred):
    pivot=pred.pivot(index='record',columns='method',values='preserve_alarm').sort_index()
    y=pred.drop_duplicates('record').set_index('record').loc[pivot.index].true_alarm.to_numpy()
    rng=np.random.default_rng(20261031);groups=[np.flatnonzero(y==c) for c in (0,1)]
    samples=np.array([np.concatenate([rng.choice(g,len(g),replace=True) for g in groups]) for _ in range(5000)])
    rows=[]
    for a,b in combinations(pivot.columns,2):
        pa=pivot[a].to_numpy();pb=pivot[b].to_numpy()
        ma=independent_metrics(y,pa);mb=independent_metrics(y,pb)
        differences={k:[] for k in ('sensitivity','specificity','challenge_score')}
        for ix in samples:
            x=independent_metrics(y[ix],pa[ix]);z=independent_metrics(y[ix],pb[ix])
            for k in differences:differences[k].append(z[k]-x[k])
        for k,values in differences.items():
            lo,hi=np.percentile(values,[2.5,97.5]);mask=y==1 if k=='sensitivity' else y==0 if k=='specificity' else np.ones(len(y),bool)
            ca=pa[mask]==y[mask];cb=pb[mask]==y[mask]
            aonly=int((ca&~cb).sum());bonly=int((~ca&cb).sum());discord=aonly+bonly
            rows.append(dict(reference=a,comparison=b,metric=k,difference=mb[k]-ma[k],ci_low=float(lo),ci_high=float(hi),
                correct_reference_only=aonly,correct_comparison_only=bonly,
                exact_mcnemar_p=float(binomtest(min(aonly,bonly),discord,.5).pvalue) if discord else 1.,
                mcnemar_scope='sensitivity' if k=='sensitivity' else 'specificity' if k=='specificity' else 'unweighted correctness, NOT weighted score',
                inference='descriptive paired record bootstrap; 5000 truth-stratified resamples; unadjusted multiple comparisons; patient dependence unresolved'))
    pd.DataFrame(rows).to_csv(OUT/'paired_comparisons.csv',index=False)

def channel_audit(sig,names,units):
    rows=[]
    for i,(name,unit) in enumerate(zip(names,units)):
        kind='ecg' if is_ecg_channel(name) else 'pulse' if name.upper() in {'ABP','ART','PLETH'} else 'unused'
        v=sig[67500:75000,i];finite=np.isfinite(v);reasons=[]
        if not finite.all():reasons.append('nonfinite_samples')
        if finite.all():
            spread=float(np.percentile(v,95)-np.percentile(v,5));flat=float(np.mean(np.diff(v)==0))
            if kind=='ecg' and (unit!='mV' or np.max(np.abs(v))>20):reasons.append('ecg_unit_or_amplitude_gate')
            if kind=='pulse' and name.upper() in {'ABP','ART'} and (unit!='mmHg' or v.min()<-20 or v.max()>350):reasons.append('pressure_unit_or_amplitude_gate')
            if kind=='pulse' and name.upper()=='PLETH' and unit not in {'NU','mV',''}:reasons.append('pulse_unit_gate')
            if spread<=1e-6:reasons.append('near_flat_spread')
            if flat>=.95:reasons.append('flat_sample_gate')
        else:spread=flat=None
        rows.append(dict(channel=name,kind=kind,unit=unit,nonfinite_count=int((~finite).sum()),
            minimum=float(v[finite].min()) if finite.any() else None,maximum=float(v[finite].max()) if finite.any() else None,
            spread=spread,flat_fraction=flat,gate_reasons=reasons,usable=kind!='unused' and not reasons))
    return rows

def peaks_for_plot(prepared,fs):
    output=[]
    for kind,v,f,valid in prepared:
        if not valid:output.append(np.array([],int));continue
        env=np.abs(f) if kind=='ecg' else f
        prominence=max(1e-9,float(np.percentile(env[-2500:],75)-np.percentile(env[-2500:],25)))
        ix,_=find_peaks(env[-2500:],distance=int(fs*.25),prominence=prominence)
        output.append(ix+5000)
    return output

def diagnose(dataset,pred,f):
    failures=pred[(pred.true_alarm==1)&(pred.preserve_alarm==0)]
    failed_ids=sorted(failures.record.unique());details=[];quality={};replayed=[]
    models={mode:json.loads((BASE/f'model_{mode}.json').read_text()) for mode in ('ecg','multimodal')}
    test=pred.drop_duplicates('record').sort_values('record')
    for row in test.itertuples():
        sig,fs,names,units=load_pre_alarm(dataset/row.record);ch=channel_audit(sig,names,units);quality[row.record]=ch
        regenerated=features(sig,fs,names,units,row.alarm);original=f.loc[row.record]
        for k,v in regenerated.items():assert np.isclose(v,original[k],rtol=1e-10,atol=1e-12,equal_nan=True),(row.record,k)
        for mode,artifact in models.items():
            score=model_score(artifact,regenerated);d=decision(score,regenerated,mode,artifact['threshold'])
            saved=pred[(pred.record==row.record)&(pred.method==mode)].iloc[0]
            assert np.isclose(score,saved.score,atol=1e-12) and d['preserve_alarm']==bool(saved.preserve_alarm) and d['abstain']==bool(saved.abstain)
            present_ecg=any(c['kind']=='ecg' for c in ch);present_pulse=any(c['kind']=='pulse' for c in ch)
            reasons=[]
            for cause in d['reason'].split(','):
                if cause=='missing_or_invalid_ecg':reasons.append('missing_ecg_modality' if not present_ecg else 'ecg_quality_rejection')
                elif cause=='missing_or_invalid_pulse':reasons.append('missing_pulse_modality' if not present_pulse else 'pulse_quality_rejection')
                elif cause=='threshold_uncertainty':reasons.append('score_near_threshold_uncalibrated')
                elif cause=='modality_rate_conflict':reasons.append('candidate_rate_disagreement')
                elif cause!='model_decision':reasons.append(cause)
            replayed.append(dict(method=mode,record=row.record,alarm=row.alarm,true_alarm=int(row.true_alarm),
                preserve_alarm=int(d['preserve_alarm']),abstain=d['abstain'],score=score,threshold=artifact['threshold'],
                threshold_distance=abs(score-artifact['threshold']),reason=';'.join(reasons) or 'accepted',
                raw_reason=d['reason'],missing_ecg=not present_ecg,missing_pulse=not present_pulse,
                invalid_feature_count=sum(not np.isfinite(regenerated[k]) for k in artifact['features']),
                feature_missingness_handling='NaNs imputed from development; not independently an abstention criterion'))
        if row.record not in failed_ids:continue
        record=dict(record=row.record,alarm=row.alarm,truth=1,missed_by=failures[failures.record==row.record].method.tolist(),
            channels=ch,features={k:(float(v) if np.isfinite(v) else None) for k,v in regenerated.items()},model_decisions={})
        for mode,artifact in models.items():
            p=model_score(artifact,regenerated);d=decision(p,regenerated,mode,artifact['threshold'])
            vec=np.array([regenerated[k] for k in artifact['features']]);vec=np.where(np.isnan(vec),artifact['impute'],vec)
            contributions=(vec-artifact['mean'])/artifact['scale']*artifact['coef']
            rank=np.argsort(contributions)[:5]
            record['model_decisions'][mode]=dict(**d,threshold=artifact['threshold'],uncertainty_band=.05,
                strongest_negative_logit_terms=[dict(feature=artifact['features'][j],contribution=float(contributions[j])) for j in rank],
                interpretation='Associations of this fitted model; not causal or clinical explanations')
        record['pulse_rule']=rule(regenerated,row.alarm)
        prepared=prepare(sig,fs,names,units);peaksets=peaks_for_plot(prepared,fs);active=0
        fig,axes=plt.subplots(len(names),1,figsize=(12,2.2*len(names)),sharex=True,squeeze=False)
        for i,(name,unit) in enumerate(zip(names,units)):
            ax=axes[i,0];v=sig[67500:75000,i];time=270+np.arange(len(v))/fs
            ax.plot(time,v,lw=.55,color='#244766');ax.set_ylabel(f'{name}\n{unit}');ax.grid(alpha=.2)
            if is_ecg_channel(name) or name.upper() in {'ABP','ART','PLETH'}:
                ix=peaksets[active];active+=1
                ax.scatter(time[ix],v[ix],s=10,color='#b8432e',label='Unvalidated candidate peaks, final 10 s')
            ax.axvline(290,color='grey',ls='--',lw=.7)
        axes[-1,0].set_xlabel('Seconds from record start; strictly before alarm at 300 s')
        axes[0,0].legend(loc='upper left',fontsize=8)
        fig.suptitle(f'{row.record} | adjudicated TRUE {row.alarm} | missed by: '+', '.join(record['missed_by'])+'\nDescriptive failure review; no beat annotations or clinical adjudication by this analysis',fontsize=10)
        fig.tight_layout(rect=(0,0,1,.93));fig.savefig(OUT/f'failure_{row.record}.png',dpi=160);plt.close(fig)
        details.append(record)
    save('heldout_channel_quality.json',quality);save('false_negative_details.json',details)
    pd.DataFrame(replayed).to_csv(OUT/'decision_replay.csv',index=False)
    failures.to_csv(OUT/'false_negative_records.csv',index=False)
    overlap={name:sorted(g.record.tolist()) for name,g in failures.groupby('method')}
    overlap['ecg_multimodal_intersection']=sorted(set(overlap.get('ecg',[]))&set(overlap.get('multimodal',[])))
    save('false_negative_overlap.json',overlap)
    return pd.DataFrame(replayed)

def coverage(replay,f):
    summaries={};by=[];reason_rows=[];curve=[]
    for mode,g in replay.groupby('method'):
        accepted=g[~g.abstain];abstained=g[g.abstain]
        reasons=Counter(r for text in abstained.reason for r in text.split(';'))
        combos=Counter(abstained.reason)
        summaries[mode]=dict(total=len(g),abstained=len(abstained),coverage=len(accepted)/len(g),
            reason_counts=dict(reasons),reason_combinations=dict(combos),
            conditional_accepted=independent_metrics(accepted.true_alarm,accepted.preserve_alarm),
            overall_with_fallback=independent_metrics(g.true_alarm,g.preserve_alarm,abstain=g.abstain),
            accepted_error_rate=float(np.mean(accepted.true_alarm!=accepted.preserve_alarm)),
            abstained_true=int(abstained.true_alarm.sum()),abstained_false=int(len(abstained)-abstained.true_alarm.sum()),
            missing_feature_rows=int((g.invalid_feature_count>0).sum()),
            invalid_feature_handling='Partial NaNs are imputed; only validity flags, rate conflict or score conditions cause abstention')
        for field in ['alarm','true_alarm']:
            for val,h in g.groupby(field):
                by.append(dict(method=mode,group=field,value=str(val),n=len(h),abstained=int(h.abstain.sum()),abstention_rate=float(h.abstain.mean())))
        for reason,n in reasons.items():reason_rows.append(dict(method=mode,reason=reason,count=n,percentage_all=100*n/len(g),overlap_allowed=True))
        # Descriptive selective-risk curve, no threshold/band selection or model update.
        for band in [0,.025,.05,.075,.1,.15,.2,.3,.5]:
            quality=g.raw_reason.str.contains('missing_or_invalid|modality_rate_conflict|invalid_score',regex=True)
            mask=~quality & (abs(g.score-g.threshold)>band)
            h=g[mask];err=float(np.mean(h.true_alarm!=h.preserve_alarm)) if len(h) else None
            # Recompute model decisions for this hypothetical band, not original fallback decisions.
            raw=(g.score>=g.threshold).astype(int);p=np.where(mask,raw,1)
            conditional_error=float(np.mean(g.true_alarm[mask]!=raw[mask])) if mask.any() else None
            total=independent_metrics(g.true_alarm,p)
            curve.append(dict(method=mode,uncertainty_band=band,coverage=float(mask.mean()),accepted_n=int(mask.sum()),
                conditional_error=conditional_error,overall_sensitivity=total['sensitivity'],false_alarm_suppression=total['specificity'],
                scope='already-inspected test data; descriptive only; original band stays 0.05'))
    save('abstention_analysis.json',summaries);pd.DataFrame(by).to_csv(OUT/'abstention_by_group.csv',index=False)
    pd.DataFrame(reason_rows).to_csv(OUT/'abstention_by_reason.csv',index=False);pd.DataFrame(curve).to_csv(OUT/'coverage_risk.csv',index=False)
    fig,axes=plt.subplots(1,2,figsize=(10,3.6));data=pd.DataFrame(curve)
    for mode,g in data.groupby('method'):
        axes[0].plot(g.coverage,g.conditional_error,'o-',label=mode)
        axes[1].plot(g.overall_sensitivity,g.false_alarm_suppression,'o-',label=mode)
    axes[0].set(xlabel='Coverage (accepted / all records)',ylabel='Error among accepted records',title='Conditional risk is selective')
    axes[1].set(xlabel='Overall true-alarm sensitivity',ylabel='False-alarm suppression',title='Abstentions preserve alarms')
    for ax in axes:ax.legend();ax.grid(alpha=.2)
    fig.suptitle('Descriptive variation of uncertainty band; no test-set tuning');fig.tight_layout();fig.savefig(OUT/'coverage_risk.png',dpi=180);plt.close(fig)

def metadata(dataset,archive):
    # Independently read targets, not the benchmark parser.
    labels=pd.read_csv(dataset/'ALARMS',header=None,names=['record','alarm','true_alarm'])
    assert len(labels)==750 and not labels.record.duplicated().any()
    assert set(labels.true_alarm)=={0,1}
    index={r.record:r for r in labels.itertuples()};supplied=dict(line.split()[::-1] for line in (dataset/'SHA256SUMS').read_text().splitlines())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in labels.itertuples():
            for ext in ['.hea','.mat']:
                file=row.record+ext;raw=(dataset/file).read_bytes();digest=hashlib.sha256(raw).hexdigest()
                assert digest==supplied[file] and raw==z.read('training/'+file)
            comments=[x.strip('# ').strip() for x in (dataset/(row.record+'.hea')).read_text().splitlines() if x.startswith('#')]
            assert comments==[row.alarm,'True alarm' if row.true_alarm else 'False alarm']
    report=dict(date='2026-10-31',records=len(labels),true=int(labels.true_alarm.sum()),false=int((1-labels.true_alarm).sum()),
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),all_record_header_labels_match=True,all_file_checksums_match=True,
        official={})
    for name in ['ALARMS','SHA256SUMS']:
        url='https://physionet.org/files/challenge-2015/1.0.0/training/'+name
        try:
            raw=urllib.request.urlopen(url,timeout=45).read();report['official'][name]=dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),matches_local=raw==(dataset/name).read_bytes())
            assert report['official'][name]['matches_local']
        except OSError as exc:report['official'][name]=dict(url=url,error=str(exc),status='retrieval not verified this run')
    historical={'Asystole':(100,20),'Bradycardia':(45,45),'Tachycardia':(8,131),'Ventricular_Tachycardia':(253,90),'Ventricular_Flutter_Fib':(52,6)}
    comparison=[]
    for name,g in labels.groupby('alarm'):
        oldfalse,oldtrue=historical[name];comparison.append(dict(alarm=name,paper_false=oldfalse,paper_true=oldtrue,
            current_false=int((1-g.true_alarm).sum()),current_true=int(g.true_alarm.sum())))
    report['published_table_source']='Clifford et al. CinC 2015 Table 1, p.275; https://www.cinc.org/archives/2015/pdf/0273.pdf'
    report['discrepancy_explanation']='Both a historical publication/current-file mismatch and changes in alarm-type totals are observed. No version history establishes cause; cannot attribute the difference solely to two relabeled records.'
    pd.DataFrame(comparison).to_csv(OUT/'historical_current_counts.csv',index=False);save('dataset_reverification.json',report)
    return labels

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--training-dir',type=Path,required=True);parser.add_argument('--archive',type=Path,required=True);args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in BASE.iterdir() if p.is_file()}
    save('baseline_preservation_manifest.json',before)
    labels=metadata(args.training_dir,args.archive)
    pred=pd.read_csv(BASE/'test_predictions.csv');splits=pd.read_csv(BASE/'splits.csv');f=pd.read_csv(BASE/'features.csv').set_index('record')
    bench=json.loads((BASE/'benchmark.json').read_text());test=splits[splits.partition=='test'];dev=splits[splits.partition=='development']
    assert len(test)==225 and len(dev)==525 and not set(test.record)&set(dev.record)
    assert set(test.cv_fold)=={-1} and set(dev.cv_fold)=={0,1,2}
    assert test.true_alarm.sum()==88 and set(splits.record)==set(labels.record)
    target=labels.set_index('record').true_alarm
    for _,g in pred.groupby('method'):
        assert len(g)==225 and not g.record.duplicated().any() and set(g.record)==set(test.record)
        assert np.array_equal(target.loc[g.record],g.true_alarm)
        assert (g.loc[g.abstain,'preserve_alarm']==1).all()
    counts=check_metrics(pred,bench);paired_comparisons(pred)
    replay=diagnose(args.training_dir,pred,f);coverage(replay,f)
    for p in BASE.iterdir():
        if p.is_file():assert hashlib.sha256(p.read_bytes()).hexdigest()==before[p.name],p.name
    save('audit_execution.json',dict(baseline_files_unchanged=True,all_four_method_metrics_recomputed=True,
        heldout_waveform_features_and_model_decisions_replayed=225,split_integrity=True,
        scope='Independent arithmetic and current-file checks plus replay of original functions; no external reviewer or clinical expert review claimed',
        saved_models_and_thresholds_unchanged=True))
    print(json.dumps(counts,indent=2));print('Original benchmark files preserved; audit and diagnostics complete.')

if __name__=='__main__':main()
