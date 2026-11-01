# Observable events, vehicle authority and secure interfaces

Project scenarios are suspected syncope/transient loss of responsiveness,
generalized tonic-clonic seizure/seizure-like motor activity, and normal driving.
Observable patterns are not diagnoses. Syncope can have convulsive movements;
cardiac rhythm evidence may support physiological suspicion but cannot establish
syncope or consciousness. The synthetic scenario mapper is separate from the
legacy supporting cardiac code and is never read by the authority gate.

Sensors -> timestamped acquisition -> pre-alarm preprocessing/quality -> features
-> observable medical evidence/unknown -> independent responsiveness verification
-> safety supervisor -> authenticated OEM evaluation request -> matched status
or timeout. A separate minimal emergency envelope is generated locally.

## Safety decision table

| Situation | Medical evidence / capacity | Executed software response | Phase 2 vehicle response |
|---|---|---|---|
| Normal responsive driver; benign quiet steering | Usable low event evidence, valid response | No new request | Continue normal operation |
| Suspected transient loss of responsiveness | Prior response then HMI nonresponse plus two source-distinct corroborations | Verification; request only if health/capability/ODD gates pass twice | Approved OEM function assesses controlled assistance/deceleration/stop given road context |
| Seizure-like motor pattern | Motion suspicion; capacity evaluated independently | Responsive driver blocks request; corroborated incapacity can request evaluation | Same vehicle-owned assessment, no seizure-specific braking command |
| Uncertain/conflicting event | Cause unknown | Preserve ICU alarm; uncertainty does not authorize action; verified capacity can independently request evaluation | Warn/verify and apply approved fallback policy |
| Sensor failure or bad/stale evidence | Evidence unavailable; corroboration may be insufficient | No new request without required independent evidence | Diagnose fault, degrade under approved safety concept |
| Missing network / missing OEM status | Delivery unavailable / acceptance unknown | No claimed delivery; ACK timeout never means stopped; no duplicate request | Gateway/controller owns existing maneuver and recovery |
| Tampered, stale, replayed or wrong-event message | Untrusted | Reject; no accepted status | Isolation, logging and authorized recovery |

The first-stage policy demo does not simulate vehicle kinematics. Temporal tests
simulate verification, request, accept/decline and timeout states, not deceleration
or a completed safe stop. An accepted request is not maneuver completion. Terminal
states do not automatically rearm; authenticated recovery and persistent state
are Phase 2 requirements. Distinct declared source IDs are not proof of physical
independence. Two misleading sources and missing corroboration remain adverse cases.

## Executed CAN-FD reference payload

`src/reference_canfd.py`: 48 payload bytes, big endian; no live bus. A safety
supervisor is the proposed request sender; an authorized OEM gateway is recipient.
An OEM status endpoint replies to the supervisor; status must match the event.
CAN identifier is caller-provided illustrative context, not an assigned vehicle ID.
The reference envelope is not an AUTOSAR SecOC implementation or homologated format.

| Offset / size (bytes) | Field | Meaning / units |
|---|---|---|
| 0 / 1 | version | 1 |
| 1 / 1 | kind | 1=request, 2=status |
| 2 / 2 | sender | approved key-map endpoint ID; no physical identity guarantee |
| 4 / 4 | event | event identifier, matched on reply |
| 8 / 4 | counter | monotonic unsigned message counter per sender in RAM |
| 12 / 8 | created | milliseconds in simulated common clock |
| 20 / 2 | lifetime | milliseconds, positive; expired/future rejected |
| 22 / 1 | medical | provisional supporting code, 0 unknown; not driver diagnosis |
| 23 / 1 | capacity | provisional capacity enumeration |
| 24 / 1 | confidence | tier, not calibrated probability |
| 25 / 2 | health | sensor-health bit mask |
| 27 / 1 | function | 0 none, 1 evaluate existing approved function |
| 28 / 1 | status | provisional status flags |
| 29 / 3 | reserved | zero |
| 32 / 16 | MAC | truncated HMAC-SHA256 over protocol context, CAN ID and header |

Enum allocation beyond documented constants is provisional; demo mappings do not
encode a clinically validated multi-etiology diagnosis. Receiver authentication
checks precede independent policy evaluation and never authorize actuators.
Alteration, unknown key-map sender, wrong context, bad length/version/reserved,
future/expired timestamp and out-of-order/replayed counter are rejected. Event
matching occurs in the temporal supervisor. Counter rollover/restart recovery,
clock synchronization and key lifecycle require a production protocol design.

## Threat model, confidentiality and external communication

Trust boundaries separate sensors, model storage/inference, safety verification,
vehicle gateway and external communication. Threats include spoofed sensors,
altered model files, replay, malicious commands, stale observations, denial of
service and disclosure of medical/location data. Optional trusted model/input
digests detect changed files; they do not authenticate live sensors. HMAC provides
integrity/authentication, not encryption. Demo keys are public, counters volatile,
and the local receipt chain is not a tamper-proof audit log.

The local JSON emergency envelope authenticates sender/counter/expiry/payload
and rejects replay. No external connection or message is sent. A proposed V2X/IP
gateway must use authorized endpoints, authenticated encrypted transport, protected
keys, persistent anti-replay, least privilege, consent/retention policy and minimal
category/responsiveness/time/authorized location fields; raw ECG/video stay local
unless separately authorized. No radio protocol interoperability is claimed.
Location plus time remain identifying. Availability faults require a controlled
fallback, not trust in a missing or delayed acknowledgement. Production controller
isolation, a hard watchdog and security validation remain unimplemented.

## Phase 1 rubric traceability

Reliability/robustness (10): paper III–IV, frozen benchmark and audit diagnostics.
Multi-etiology (10): paper I–II, scenario reasoning and clinical distinctions.
Clinical grounding (10): ESC syncope and ILAE tonic-clonic evidence; limits explicit.
Vehicle architecture (10): paper II, independent capacity/safety gates and diagram.
CAN/V2X integrability (10): paper V, this field specification and reference tests.
Fail-safe (5): decision table, temporal fault tests and adverse counterexamples.
This maps coverage of criteria, not an awarded score or clinical readiness claim.
