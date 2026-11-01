# Executed cardiac benchmark

Population: 750 public training records, 525 development,
225 internal held-out test. No official hidden test or driving data.

Multimodal sensitivity is 97.7% (95% interval 92.0%--99.7%); false-alarm suppression is 15.3% (9.7%--22.5%). Its ROC-AUC is 0.893, versus 0.862 for ECG-only, but its local score is lower (45.92 versus 46.84). Multimodal and ECG-only suppress 2 and 3 true alarms, respectively. Neither achieves 98% held-out sensitivity. The multimodal threshold is 0.29, selected with C=0.1; ECG uses 0.12 and C=10.0. Thresholds were not adjusted after test evaluation.

On a Windows 11 Intel Core i5-13450HX host (Python 3.13.2), median loading, preprocessing and feature times are 5.424, 2.314 and 3.951 ms per record, respectively. Pure model execution has median 0.0126 ms and 95th percentile 0.0330 ms across ten passes over the 225 test records. Loading/filter/feature times cover all 750 recordings.

Prediction extraction failures: 0; excluded records:
0. Abstentions are included as preserve-alarm decisions.

Benchmark counts come from benchmark.json / per_alarm.csv. Current proportion
intervals come from scientific_audit/exact_intervals.csv (exact binomial).

n,true,false,tp,fp,tn,fn,sensitivity,specificity,precision,f1,balanced_accuracy,false_alarm_suppression_rate,true_alarms_suppressed,true_alarms_suppressed_percent,challenge_score,abstention_rate,method,roc_auc,average_precision,pr_auc

225,88,137,88,137,0,0,1.0,0.0,0.3911111111111111,0.5623003194888179,0.5,0.0,0,0.0,39.11111111111112,0.0,always_preserve,,,

225,88,137,87,126,11,1,0.9886363636363636,0.0802919708029197,0.4084507042253521,0.5780730897009967,0.5344641672196416,0.0802919708029197,1,1.1363636363636365,42.79475982532751,0.6622222222222223,pulse_rule,,,

225,88,137,85,111,26,3,0.9659090909090908,0.1897810218978102,0.4336734693877551,0.5985915492957746,0.5778450564034505,0.1897810218978102,3,3.409090909090909,46.83544303797469,0.1466666666666666,ecg,0.8623921698739218,0.8148781940391525,0.8129347061775352

225,88,137,86,116,21,2,0.9772727272727272,0.1532846715328467,0.4257425742574257,0.593103448275862,0.565278699402787,0.1532846715328467,2,2.272727272727273,45.92274678111588,0.7111111111111111,multimodal,0.8934140676841407,0.8583408717822159,0.8575068819477552



Benchmark diagnostics: SCIENTIFIC_AUDIT.md, FALSE_NEGATIVE_ANALYSIS.md and
VEHICLE_INTERFACE_AND_SAFETY.md. Exact intervals, paired comparisons,
coverage diagnostics and per-record plots are in results/scientific_audit/.
