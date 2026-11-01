# Record-level false-negative review

All traces show only [270,300) seconds in original physical units. Vertical marks
in the final ten seconds are algorithm candidate peaks, not adjudicated beats.
Labels remain the official ALARMS labels. Plots are in
results/scientific_audit/failure_RECORD.png; channels, per-lead features, model
scores, thresholds, negative logistic contributions and gates are in
false_negative_details.json and false_negative_records.csv. Contributions are
associations in a linear model, not causal physiological explanations.

| Record / method | Alarm / available channels | Findings and interpretation |
|---|---|---|
| b832s / pulse rule | Bradycardia; II,V,PLETH,RESP | ECG candidate rates 126/144 and pulse 120 bpm; RR CV 0.047, gap 0.52 s; mismatch 15 bpm. The stable-pulse rule suppresses. ECG is visibly noisy; periodic pulse oscillations are not validated beats. Feature/quality weakness is plausible; clinical failure mechanism unknown. |
| a654s / ECG | Asystole; II,V,PLETH,RESP | Score0.00206 below0.12; candidate ECG rates96/138 and pulse120; mismatch3 bpm. Noise and small fluctuations are counted, pulse is irregular. Displayed leads do not allow confident reconstruction of the adjudicated episode. Cause unknown without expert reference; do not relabel. |
| v448s / ECG | VT; II,V,PLETH | Score0.03293 below0.12. Near-flat ECG changes to large rapid complexes near292.5 s; noise is counted before transition. Last10 candidate rates114/102; gaps2.704/2.740 s. PLETH is flat0 and rejected, so multimodal abstains/preserves. Nonstationarity and missing morphology are plausible associations. |
| v534s / ECG and multimodal | VT; II,V,PLETH,RESP | Scores0.03545/0.14007 below thresholds0.12/0.29. ECG120/120 and pulse126; mismatch6 bpm. Earlier morphology/amplitude changes precede regular late complexes. Rate regularity can conceal rhythm risk; neither model represents validated VT morphology. Clinical mechanism remains unadjudicated. |
| a167l / multimodal | Asystole; II,V,PLETH,ABP | Score0.18670 below0.29. Large ECG complexes cease near293 s, but small oscillations generate candidate rates162/156. Near-flat PLETH passes broad gates and yields198 bpm. Difference39 bpm narrowly avoids the >40 gate. First usable PLETH is selected before low/irregular ABP (~14–21 mmHg). Basic quality/peak features are implicated; this is not independent clinical adjudication. |

All learned-model errors lie outside their ±0.05 abstention margins on the
suppression side. They are accepted errors, not abstention/default errors. A low
uncalibrated score does not mean a confident clinical exclusion. Changing any
threshold or quality rule in response to these records would consume test-set
information; no such change was made. No single mechanism is proven across cases.
