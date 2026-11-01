# Architecture and trust boundaries

```mermaid
flowchart TD
  A[Stored ICU ECG and ABP or PLETH] --> B[WFDB physical units; read only before 300 s]
  B --> C[Preprocessing and per-channel quality]
  C --> D[Alarm verification; abstention preserves alarm]
  D --> E[Illustrative cardiac hypothesis adapter]
  F[Simulated seizure-like camera evidence] --> M[Medical hypothesis or unknown]
  E --> M
  H[Simulated HMI response] --> U[Independent functional-capacity evidence]
  I[Simulated steering and camera corroboration] --> U
  U --> G[Independent supervisor: health, capability, operating domain]
  M --> N[Local warning and minimal hypothesis field]
  G --> V[Authenticated request for OEM evaluation]
  V --> W[Simulated OEM accept, decline or timeout]
  G --> X[Separate consent and communication eligibility]
  N --> X
  X --> Y[Authenticated local emergency envelope; no transmission]
```

Only A-D are the measured ICU alarm-verification experiment. Driver-capacity
observations, the seizure branch and OEM behavior remain synthetic. Cardiac false
alarms never establish normal driving. The medical classifier has no actuator
interface. The original normal-driving policy remains available for simulations.
No raw physiology enters the emergency envelope. HMAC provides local authenticity
and integrity, not confidentiality or guaranteed anonymity. No motor command,
V2X stack, real CAN transport or EMS delivery is implemented.
