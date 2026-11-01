# Phase 2 medical validation protocol

Cardiac Phase 1 status: the complete five-alarm ICU benchmark has now executed.
See CARDIAC_PROTOCOL.md, DATASET_PROVENANCE.md and CARDIAC_RESULTS.md for the
implemented methods, observed labels and measured internal record-split results.
These supersede the earlier proposed VT-only experiment. Clinical driver
performance, patient-independent generalization and the seizure branch remain
unmeasured. No protocol here is registered with an external trial registry.

## Selected driver scenarios (authoritative scope)

Suspected syncope/transient loss of responsiveness, generalized tonic-clonic
seizure/seizure-like observable motor activity, and normal driving remain the
project scenarios. None is clinically validated by ICU alarm truth. Acquire
consented, expert-adjudicated loss/recovery of responsiveness and tonic-clonic
episodes with relevant mimics; group by patient and freeze causal features,
calibration, quality rules and thresholds on development patients only. Normal
driving negatives must include benign movement, quiet steering, occlusion and
sensor faults. Measure event sensitivity, false alerts per valid driving hour,
delay, coverage and confidence intervals clustered by patient. An independent
test cohort is required after development. Camera positives require aligned
clinical video labels; staged movements cannot establish clinical sensitivity.

The retained focal-seizure SeizeIT2 protocol below is a separate feasibility
study, not direct validation of generalized tonic-clonic seizures. ILAE/IFCN
guideline: https://doi.org/10.1111/epi.16818 . No clinical partnership is claimed.

## C. Cardiac next steps

Obtain reliable patient groups or an independent, appropriately authorized cohort;
freeze quality rules, features, calibration and safety thresholds on development
patients before external evaluation. Test electrode loss, movement, dangerous
rhythms and benign driver activity. Report false negatives, false alerts per valid
observation hour, onset delay, abstention and confidence intervals accounting for
patients. Do not treat rejected ICU alarms as normal driving or syncope labels.

## S. Focal seizure-related wearable-motion screening

**Source**: M. Bhagubai et al., SeizeIT2, Scientific Data (2025), DOI 10.1038/s41597-025-05580-x. Respect dataset and institutional privacy and download terms.

**Ground truth and inputs**: Use released seizure onset and offset annotations and subject identifiers. Accept accelerometer and gyroscope channels as *wearable motion* input. Behind-ear EEG may provide a clinician-generated reference and is not an input to the proposed movement-only benchmark. Any participant with missing motion data must appear in the missingness/coverage report; do not silently classify the absent signal as normal or remove them without disclosure. The original dataset covers 883 focal seizures in 125 patients, but availability of usable motion features is to be determined record by record. A seizure without a motor signature may be impossible to detect from motion alone; report it as missed within the evaluable coverage rather than silently excluding hard positives.

**Preprocessing and features**: Respect sample-rate metadata and axis units. Apply timestamp alignment, physical-signal quality checks and causal 4-second windows with a 2-second advance, as a starting design setting. Compute magnitude energy, movement changes, periodicity/autocorrelation, angular-velocity energy, validity fraction and artifact flags. Do not derive all overlapping windows from the same patient into different data folds.

**Split and model selection**: Five patient-grouped outer folds with fixed seed `20261030`; if class balance permits, a stratified grouped method. All preprocessing choices, class weights, calibration, thresholds and persistence are selected using only inner training-patient folds. Evaluate on each held-out patient group once, then aggregate event-level performance with explicit denominators and per-patient coverage. If a held-out fold lacks seizure events, state that and do not calculate undefined sensitivity.

**Baselines and proposed model**:
- S0: simple motion-energy threshold with persistence selected on development patients.
- S1: class-weighted logistic regression on motion features with training-only scaling.
- S2: S1 plus per-source signal-quality rejection and an independently defined sequential persistence rule.

**Event labels and alarm matching**: A causal window ends at time t. Define a seizure detection as an alarm from annotated onset through offset plus a predeclared 5-second tolerance; report late alarms distinctly. Merge predicted alarm bursts separated by less than 10 seconds into a single alarm episode. An alarm outside any seizure matching interval counts as false within evaluated nonictal time. All onset tolerance, matching and merging rules are proposed protocol choices to be agreed and frozen before running experiments, not clinical thresholds.

**Metrics**: Episode sensitivity `number of detected seizures/number of annotated seizures in eligible coverage`, median and upper-tail onset-to-first-alarm delay, false alarm episodes per annotated nonictal monitored hour, abstention and missing-channel coverage. Include per-subject and seizure-subtype breakdown where labels and sample size allow. Avoid claiming camera performance from wearable motion metrics.

**Camera validation is separate**: The real camera branch needs synchronized, ethically collected and clinically labeled video for positive seizure events plus independent benign driving recordings. Staged or acted seizure movements may be used for functionality/negative stress testing, *never as clinical positives*. If actual clinically annotated positive camera recordings remain unavailable, report camera seizure sensitivity as not measured. The camera system may still be evaluated on landmark quality, occlusion and response to normal driver movements.

## E. End-to-end safety evaluation

Use an authorized simulated vehicle function for actuation. The triage classifier emits only a request to evaluate the vehicle's independent minimum-risk maneuver. Compare B1 single-stream alarm, B2 ungated fusion, B3 quality-gated fusion and B4 full incapacity plus safety supervisor under matched held-out trajectories, normal/abnormal-but-responsive behavior, missing sensors, forged messages and connectivity loss. Outputs: unauthorized evaluation requests, warranted but missed evaluation requests, abstention, time to request, time to accepted/declined status, and completed maneuver metrics from the simulator. A positive policy result is not evidence that the vehicle stopped.

A joint clinical multi-etiology evaluation requires real synchronized multimodal measurements and independently established etiology and incapacity labels. It is a separate study, not a statistical merge of the two datasets above.
