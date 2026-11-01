# Executed safety evidence and remaining limitations

256 tests passed; see `results/tests.xml`. Controlled
faults exercise implemented behavior, including absent ECG, absent pulse,
nonfinite/flat/extreme samples, conflicts, low confidence, loading failure,
truncation, invalid model, changed model/input digest and late completion.
All tested inference failures preserve the alarm and abstain. The timeout is a
soft elapsed-time check, not an independently scheduled hard watchdog. A hung
native call remains untested; Phase 2 needs worker-process termination and stale
result rejection under a controller deadline.

Existing HMAC/CAN-reference and temporal tests cover forged/unauthorized messages,
wrong context/event, stale/replayed frames, OEM decline and missing acknowledgement.
Network-loss scenarios suppress external notification eligibility, without claiming
delivery or cancellation of an OEM-owned maneuver. The integrated demo uses the
real ICU loader/model with synthetic driver capacity, HMI and vehicle status.
Responsive drivers or missing corroboration block requests; independent synthetic
incapacity can still request evaluation when medical cause is unknown.

The cardiac adapter only emits a synthetic cardiac hypothesis for nonabstaining,
preserved alarms with finite numeric score in [0.7,1]. That mapping is illustrative, uncalibrated and
not clinically evaluated. Suppressed/uncertain ICU alarms never label normal driving.
The seizure expert and normal class remain the existing simulated policy; neither
is trained on ICU truth labels. A local minimal emergency envelope is authenticated
and replay-tested; it is not encrypted, transmitted or connected to EMS.

Model files use validated numeric JSON, avoiding executable pickle loading.
Optional file digests detect changes only against a trusted expected digest.
They do not authenticate a live sensor or protect against a compromised trusted
source. The reference HMAC keys are public test constants, counters are RAM-only,
the receipt chain is not an authenticated audit log, and real bus/vehicle security
is untested. Key rotation, secure storage, replay across restart, encryption and
EMS authorization need separate Phase 2 implementation and controlled testing.

The original two adverse counterexamples remain: jointly misleading independent
source labels can cause a false request, and missing corroboration can miss true
synthetic incapacity. No invariant proves road safety or clinical detection.

Clinical performance in drivers remains unmeasured. Patient overlap, ICU domain
shift, alarm-selection bias, rough beat features, uncalibrated scores and small
subgroups limit interpretation. The primary model misses the 98% held-out target;
no threshold was changed after seeing this failure. Its high abstention and true
alarms suppressed preclude any supported deployment claim.


Benchmark diagnostics: SCIENTIFIC_AUDIT.md, FALSE_NEGATIVE_ANALYSIS.md and
VEHICLE_INTERFACE_AND_SAFETY.md. Exact intervals, paired comparisons,
coverage diagnostics and per-record plots are in results/scientific_audit/.


The optional CUSUM extension is synthetic and uncalibrated. Its specification
is in CUSUM_DESIGN.md; results are in results/cusum/. Real-camera benefit
is unmeasured.
