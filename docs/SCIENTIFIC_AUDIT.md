# Cardiac benchmark diagnostics and limitations

These analyses concern the frozen ICU alarm-verification experiment. They
are descriptive software and statistical checks, not external accreditation
or clinical review. Diagnostic artifacts are in `results/scientific_audit/`.

## Dataset and protocol interpretation

Historical false/true counts (publication) versus current ALARMS are respectively:
Asystole 100/20 vs 100/22; Bradycardia 45/45 vs 43/46; Tachycardia 8/131 vs 9/131;
VT 253/90 vs 252/89; VF/flutter 52/6 vs 52/6. The explanation is unknown.
Sources: https://www.cinc.org/archives/2015/pdf/0273.pdf and
https://physionet.org/content/challenge-2015/1.0.0/ .
No original hidden challenge test set was used. The current 225-record split was
initially held out for the frozen benchmark; it has now been examined. Subsequent
plots, coverage curves and error review are post-selection diagnostics, not fresh
confirmation. No model, feature, threshold or abstention rule was changed.

## Missed genuine alarms

See FALSE_NEGATIVE_ANALYSIS.md for each record, physical-unit plots and measured
features. Pulse rule misses b832s. ECG misses v534s, v448s, a654s. Multimodal misses
v534s, a167l. Only v534s overlaps ECG and multimodal; the pulse miss is separate.
These are six method errors on five records. Waveform observations and feature
associations do not establish a clinical cause or justify relabeling.

## Abstention and coverage

Multimodal abstains on 160/225 (71.1%), leaving 65 accepted (28.9%). All records
have ECG and pulse modalities present. Zero abstentions arise from truly missing
modalities. Overlapping reasons: candidate-rate disagreement 138, near-threshold
score 30, ECG quality rejection 8, pulse quality rejection 3. Nineteen records have
both disagreement and score proximity. Exclusive counts are 119, 11, 8, 3, and 19
for disagreement only, proximity only, ECG quality only, pulse quality only, both.
Score proximity is an engineering margin, not calibrated uncertainty.
Nineteen records have partial missing features, handled by development-fitted
imputation; this is not an independent abstention reason. No invalid score caused
abstention in the saved test population.

Accepted records contain 32 true / 33 false: TP30/FN2/TN21/FP12, conditional
sensitivity 93.75%, specificity 63.64%, error 14/65=21.54%. This selected subset
must not replace overall results. Abstentions contain 56 true / 104 false and all
preserve alarms; overall TP86/FN2/TN21/FP116, sensitivity97.73%, specificity15.33%.
ECG abstains33 (25 score margin, 8 quality), accepts192, TP84/FN3/TN26/FP79.
Per-alarm/truth breakdowns: abstention_by_group.csv; all reason combinations:
abstention_analysis.json. coverage_risk.csv/png varies only the diagnostic score
margin; it is not used to choose a new policy or improve headline results.

| Multimodal group | Abstained / total | Rate |
|---|---:|---:|
| Asystole | 27/36 | 75.0% |
| Bradycardia | 19/27 | 70.4% |
| Tachycardia | 25/42 | 59.5% |
| Ventricular tachycardia | 73/102 | 71.6% |
| Ventricular flutter/fibrillation | 16/18 | 88.9% |
| True alarm | 56/88 | 63.6% |
| False alarm | 104/137 | 75.9% |

At the vehicle boundary abstention supplies unavailable cardiac evidence. A
preserved alarm alone never authorizes braking or an evaluation request. Existing
independent capacity and OEM gates may request evaluation with unknown etiology.

## Uncertainty and comparison

exact_intervals.csv supplies 95% Clopper-Pearson intervals for overall and each
alarm-type sensitivity, specificity/suppression and precision. They assume
independent records; unknown patient clustering can invalidate nominal coverage.
Original 1,000-resample intervals remain preserved as historical outputs; exact
intervals address boundary degeneracy, not patient dependence or selection bias.
paired_comparisons.csv uses the same sampled record indices for each pair, with
5,000 truth-stratified resamples. McNemar exact tests use paired discordances;
the score row's test explicitly concerns unweighted correctness, not weighted
challenge score. Multiple comparisons are unadjusted and descriptive.

Multimodal minus ECG sensitivity difference is +1.14 percentage points (paired
95% interval -2.27 to +5.68); specificity -3.65 points (-11.68 to +4.38); challenge
score -0.91 (-7.14 to +5.41). These do not establish superiority. Small true-alarm
subgroups and only six true VF/flutter records in the full archive limit inference.

## Scope

No live sensor validation, real vehicle maneuver, clinical driver performance,
real V2X or EMS delivery is established. The two adverse synthetic policy
counterexamples remain: jointly misleading source labels and missing corroboration.
Further model selection requires development data and new independent data
for confirmation; this inspected test split is not fresh validation.
