# Executed protocol and leakage assessment

Positive = TRUE original ICU alarm. False alarms are not healthy patients or normal
driving. This does not validate syncope, seizure, normal driving or clinical action.
All 750 records participate: 525 development and 225 originally held-out test records. Joint
alarm-type/truth stratification, seed 20261030. Exact IDs and development-only
3-fold assignments are saved in splits.csv. No patient IDs are available: only
record-disjoint generalization is tested, never patient independence or external
validation. All windows from a record remain together. Exact duplicates are
checked before splitting; no near-duplicate/patient-overlap claim is made.

The loader limits every inference read to samples [0,75000); features use final
30 and 10 seconds. No quality, normalization or filtering operation accesses
post-alarm samples. Dataset integrity auditing separately checks complete files,
including checksums and geometry; those full-file values are never model inputs.
Filtering is causal third-order Butterworth (ECG 5-25 Hz, pulse 0.5-8 Hz). Window
median subtraction uses only available pre-alarm samples. Existing provider
resampling/filtering cannot be audited as a live sensor implementation.
This is alarm-time verification, not early prediction or retrospective Event 2.

Each available ECG lead and first usable pulse supplies amplitude, flatness,
candidate rate, RR CV, maximum gap, spectral entropy and high-frequency power.
Missing/invalid channels supply NaNs with validity flags. Median imputation and
scaling fit separately inside development folds. Alarm-type one-hot encoding is
available from the triggering monitor and shared across learned models. Labels,
record IDs, duration suffixes, archive checksums and header comments do not enter X.
Logistic regression uses balanced class weights, C in {0.1,1,10}, max_iter=2000.
Development OOF ROC-AUC chooses C; the same development OOF predictions select
thresholds on a 0.01 grid for maximum local score with sensitivity >=0.98. These
OOF selection estimates may be optimistic; the frozen benchmark used held-out evaluation.
No probability calibration is fitted or claimed. Saved configuration identifies
multimodal as primary; no external preregistration is established. No winner is
selected from held-out outcomes. The 98% constraint is an internal target.

The fixed pulse baseline suppresses asystole/bradycardia/tachycardia only when
signals are usable and concordant, pulse rate is 45-130 bpm, RR CV <0.2 and gap <2s.
It always preserves VT/VF. The always-preserve baseline supplies the safety floor.
Model uncertainty band is +/-0.05 around its threshold. Missing ECG, missing
pulse (multimodal), >40 bpm modality disagreement, invalid scores or failures
cause abstention AND preserve. ECG bounds are +/-20 mV, ABP -20 to 350 mmHg,
spread >1e-6 and flat fraction <0.95; these are fixed engineering heuristics.

Metrics include fallback decisions on every held-out record, not just accepted
predictions. AUCs use raw uncalibrated model scores across the same test population;
they measure ranking, not the quality-gated operating policy. PR-AUC is trapezoidal;
average precision is separately reported. The score is 100*(TP+TN)/(TP+TN+FP+5*FN).
1000 truth-stratified record bootstraps produce percentile 95% intervals, conditional
on fixed models and observed case mix. No patient clustering or training uncertainty
is captured. Zero-error bootstrap intervals may be degenerate. The final audit adds
exact binomial intervals and paired record comparisons; see SCIENTIFIC_AUDIT.md.
The test set is now inspected; later diagnostics are descriptive only. Small alarm subgroups
must not support strong clinical conclusions. Test curves are descriptive only.


Benchmark diagnostics: SCIENTIFIC_AUDIT.md, FALSE_NEGATIVE_ANALYSIS.md and
VEHICLE_INTERFACE_AND_SAFETY.md. Exact intervals, paired comparisons,
coverage diagnostics and per-record plots are in results/scientific_audit/.
