# Evidence index

Paths are relative to the prototype root.

| Quantity or claim | Evidence |
|---|---|
| Current software tests | `tests/`; `results/tests.xml` |
| 35 legacy scenarios and their counts | `results/cr01_scenarios.csv`; `results/cr01_summary.json` |
| Separate 20-case strict capacity experiment | `results/strict_assurance_cases.csv`; `results/strict_assurance_summary.json` |
| Temporal and finite-domain policy behavior | `results/temporal_demonstration.json`; `results/counterfactual_summary.json` |
| Dataset identity, labels and checksums | `results/cardiac/dataset_audit.json`; `results/cardiac/dataset_manifest.json` |
| Official metadata verification | `results/cardiac/official_metadata_verification.json` |
| Development/test membership and folds | `results/cardiac/splits.csv` |
| Frozen features and fitted models | `results/cardiac/features.csv`; `results/cardiac/model_ecg.json`; `results/cardiac/model_multimodal.json` |
| Held-out predictions and aggregate metrics | `results/cardiac/test_predictions.csv`; `results/cardiac/comparison.csv`; `results/cardiac/benchmark.json` |
| Per-alarm metrics and exact intervals | `results/cardiac/per_alarm.csv`; `results/scientific_audit/exact_intervals.csv` |
| False negatives and coverage | `docs/FALSE_NEGATIVE_ANALYSIS.md`; `results/scientific_audit/false_negative_details.json`; `results/scientific_audit/coverage_risk.csv` |
| Historical raw-data reproduction record | `results/cardiac/reproduction_verification.json` |
| Offline timings and environment | `results/cardiac/latency.csv`; `results/cardiac/model_latency.csv`; `results/cardiac/environment.json` |
| Synthetic CUSUM behavior | `results/cusum/synthetic_verification.json`; `results/cusum/synthetic_traces.csv`; `results/cusum/integration_enabled.json`; `results/cusum/integration_disabled.json` |

ICU benchmark results, synthetic policy tests and camera-engine tests measure
different components. They do not establish clinical driver performance, physical
source independence or vehicle safety. The safety and benchmark documentation
records false negatives, high abstention, unmet targets and remaining limitations.
