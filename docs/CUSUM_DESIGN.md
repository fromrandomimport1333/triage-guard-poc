# CabinGuard-ADI sequential monitoring specification

## Role and available inputs

The monitor consumes synthetic `Signal(source_id,value,quality,at_ms,available)`
and `CR01Observation.camera_motor_score` inputs. The separate experimental
camera front end does not provide a calibrated continuous anomaly score or
annotated participant/session data for this monitor.
The new module accepts an explicitly versioned scalar stream; it neither extracts
features nor chooses a medical etiology. The optional integration is observation
and reporting only: existing medical reasoning and `TemporalAssurance` receive
their original observations. CUSUM never replaces capacity evidence or sends a
command, message, brake request or emergency notification.

## Exact formulation

Use the standardized-score formulation only:

`z_t = (a_t - mu0) / sigma0`, with finite `sigma0 > 0`.

`S_t = max(0, S_(t-1) + z_t - k)`, `S_0 = 0`, crossing when `S_t >= h`.

`a_t` is an external score in declared arbitrary score units; higher means more
of the specified observable pattern. `mu0` and `sigma0` have those same units;
`z`, `k`, `h` and S are dimensionless. Centering occurs exactly once. No Gaussian
distribution, likelihood ratio or disease probability is assumed. There is no
learned camera score or empirical normalization in this release. Synthetic replay
declares `mu0=0,sigma0=1,k=1,h=5`; these reproduce the note, not selected parameters.
The fixed baseline compares the same z against an explicit per-window threshold,
with identical inputs, quality, session, timeout and latch/reset rules.

No minimum-duration rule is added. A single z >= k+h crosses from zero. The update
is per eligible observation, not time-weighted; timestamps govern gaps, not a
silent modification to the equation. Changing window stride/overlap changes
operating behavior. The replay's nominal cadence is illustrative, never a validated
camera cadence. Parameter configuration requires version/provenance identifiers.

## Quality, time and state policy

Inputs carry session/source, timestamp in milliseconds, score and units, score
version, normalization ID, boolean validity and a quality reason. Reject malformed
objects, nonfinite scores, metadata/units mismatch, duplicate/out-of-order times
and unexpected session/source. Every rejected input returns UNKNOWN, no crossing.
An invalid score is not replaced with zero. Nonmonotonic/invalid times do not
advance the clock. Explicit scheduler `tick` calls let absence become observable;
there is no background timer or hard real-time watchdog.

Short invalid intervals hold S but report UNKNOWN even if an alarm was latched.
When elapsed time since the last valid sample (or session start) exceeds the
configured gap limit, clear S, retain any alarm latch, and require an explicit
sensor-recovery/operator reset before new evidence is accumulated. A valid sample
arriving after a long silent gap is itself rejected into this recovery state.
Demonstration limit 2000 ms is an unvalidated engineering setting. It does not
establish an acceptable medical detection delay. No such maximum is validated.

The first valid sample yields MONITORING or a crossing. MONITORING means only
below-threshold monitoring, never normal driving or health. A first crossing emits
SUSPECTED_BEHAVIORAL_CHANGE and latches. Subsequent valid samples return
VERIFICATION_PENDING without repeated crossing events, even if S falls below h.
No automatic cooldown or auto-rearm. UNKNOWN overrides current availability;
historical latch state remains explicitly visible. ALERT/ESCALATION is a separate
existing supervisor state, not a state the CUSUM module can authorize.

Reset is an explicit local API request with timestamp, session and reason:
operator_review; sensor_recovery (only after degradation); new_session (must name
a different session). Within-session clocks cannot move backwards. New sessions
may start a new clock and discard prior evidence; old-session inputs are rejected.
Reset clears S/latch and returns UNKNOWN until a fresh valid sample. OEM accept,
decline or timeout never automatically resets the monitor or rearms the supervisor.
Reset API callers are trusted local orchestration, not authenticated remote senders.
No state import/restart persistence is implemented. Frozen state snapshots are
read-only telemetry. Detectable state corruption or arithmetic overflow forces
UNKNOWN and explicit recovery; this is not tamper-proof memory protection.
A fresh process starts with S=0 and no latch and can repeat a prior crossing;
restart-wide suppression requires persistent authorized state in Phase 2.

## Evaluation and safety boundary

No relevant annotated chronological recordings exist here. Event sensitivity,
false alerts per eligible non-event hour, clinical/behavioral detection delay,
real feature availability and empirical benefit versus fixed threshold are
NOT MEASURED. Synthetic traces verify arithmetic/failure handling only; threshold
choices are not matched for false-alert rate and cannot establish superiority.
No ICU recording is repurposed as camera-session data.

Future protocol: fit score/scaling on training participants, select both methods'
parameters and reset policy on whole validation sessions under a prespecified
false-alert/delay objective, freeze, evaluate held-out participants/sessions.
Match first qualifying alert within each eligible annotation [onset,end], count
an event once, retain missed events, count unmatched crossing alerts in eligible
non-event time, and divide by that measured duration in hours. Report delay of
detected events with misses, and availability/UNKNOWN separately. A latched alarm
cannot count later events; reset episodes and eligibility must be specified before
evaluation. No overlap-window random split, test tuning or iid ARL-to-hour shortcut.
