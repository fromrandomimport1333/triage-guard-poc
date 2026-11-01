# TRIAGE-GUARD proof of concept

CabinGuard-ADI Phase 1

Anonymous submission

This prototype contains synthetic decision policies, a virtual CAN FD message
demonstration, a PhysioNet/CinC 2015 cardiac alarm-verification benchmark,
an optional CUSUM monitor and an experimental camera front end.

## Installation and tests

Python 3.10 or newer. The verified environment uses Python 3.13.2.

```text
python -m venv .venv
```

Activate with `.venv\Scripts\Activate.ps1` in Windows PowerShell or
`source .venv/bin/activate` on Linux/macOS, then:

```text
python -m pip install -r requirements-lock.txt
python -m pytest tests -q
```

The complete suite contains 256 tests, including 46 camera rules-engine tests.
The 21-test subset reported in the paper consists of 6 legacy policy tests,
12 CR-01 tests and 3 CAN-demo tests.

## Demonstrations

| Command | Scope |
|---|---|
| `python run_cr01.py` | 35 synthetic legacy-policy and onset-order scenarios |
| `python run_experiment.py` | Baseline comparison on 24 synthetic legacy cases |
| `python run_assurance_cases.py` | 20 strict capacity-policy cases |
| `python -m src.can_demo` | 16-byte request frame, replay/tampering checks and sender-silence fallback |
| `python run_scenario_demo.py` | Five synthetic driver-state scenarios |
| `python run_temporal_demonstration.py` | Request/status timing and acknowledgement behavior |
| `python run_counterfactual_audit.py` | Finite-domain synthetic policy checks |
| `python run_cusum_demo.py --enable-cusum` | Optional synthetic sequential-monitor replay |

The CAN demo uses `python-can`'s virtual interface when installed, otherwise an
in-process queue. Neither connects to physical hardware. The camera script and
its separate dependencies are documented in `experimental/camera_frontend/README.md`.

## Evidence and implementation scope

The 35-case harness preserves the legacy capacity rule, which allows both
capacity fields to share a source. The paper's stricter requirement for HMI
nonresponse and two distinct corroborating sources is implemented separately in
`strict_safety_policy.py` and exercised by `run_assurance_cases.py`.
The strict medical rule abstains when both experts alarm; onset precedence is
implemented in the legacy harness. These are component experiments, not a single
integrated implementation of every proposed rule.

`results/cardiac/` contains the frozen features, splits, fitted JSON models,
predictions and benchmark metrics. `results/scientific_audit/` contains diagnostic
intervals, paired comparisons, abstention and false-negative analyses.
The ECG-plus-pulse model preserves 86/88 true alarms and suppresses 21/137 false
alarms on the 225-record test split, with 160/225 abstentions.

The benchmark measures ICU alarm verification, not driver-event detection.
Policy observations and vehicle responses are synthetic. The camera front end
has no measured performance on annotated driver recordings. No real vehicle
actuation, EMS delivery or clinical validation is claimed.

## Supporting documentation

- `docs/REPRODUCE.md`: benchmark and diagnostic commands; external data requirements.
- `docs/EVIDENCE_INDEX.md`: reported quantities and their result files.
- `docs/CARDIAC_PROTOCOL.md` and `docs/DATASET_PROVENANCE.md`: data and methodology.
- `docs/SCIENTIFIC_AUDIT.md` and `docs/FALSE_NEGATIVE_ANALYSIS.md`: benchmark limitations.
- `docs/SAFETY_AND_LIMITATIONS.md`: implemented checks and remaining risks.
- `docs/CUSUM_DESIGN.md`: uncalibrated sequential-monitor specification.
