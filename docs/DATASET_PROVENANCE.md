# Dataset provenance and observed discrepancy

PhysioNet/CinC Challenge 2015 v1.0.0; DOI https://doi.org/10.13026/c9fg-a467.
Source: https://physionet.org/content/challenge-2015/1.0.0/ (checked 30 October 2026).
Archive SHA-256: `1f191ca45f555f05ae23be67c34923e2e1624051669bd24a0e49bdad7e5ef686` (338623761 bytes).

Observed: 750 indexed, 750 valid, 0 excluded;
294 true / 456 false. The supplied/reference 292/458 counts are NOT reproduced.
The official hosted ALARMS and SHA256SUMS exactly match the local files, as recorded
in `results/cardiac/official_metadata_verification.json`. The reason for the
historical distribution difference is not established. No relabeling was performed.
The prior release's VT 90/253 statement is superseded by the observed 89/252 (341).

All ALARMS targets are checked against explicit header comments. Alarm type is
monitor metadata, not the adjudication. No filename or ordering determines truth.
Every archive member passes CRC; each waveform/header matches both local and
official SHA-256 manifests. Every WFDB signal checksum and geometry passes.
WFDB physical units independently match the original mathematical calibration.
No exact full-waveform or pre-alarm digital duplicates were found. Near duplicates
and common-patient dependence remain unresolved.

375 records are 300 seconds and 375 are 330 seconds, all 250 Hz. Each has two ECG
channels. PLETH occurs in 627, ABP in 343, RESP in 278; availability overlaps.
Header-unit counts: {'mV': 1500, 'NU': 905, 'mmHg': 343}. Patient IDs are absent; header comments contain
only alarm type and truth. Index and checksum files contain no reliable grouping.

Dataset page license: Open Data Commons Attribution License v1.0,
https://physionet.org/content/challenge-2015/1.0.0/ (Access section).
The repository-level LICENSE.txt contains GPLv3, apparently associated with the
challenge software; we record this difference rather than silently treating it
as the dataset license. No third-party challenge algorithm source is copied and
no raw dataset files are redistributed. Derived feature and result tables carry
the dataset attribution here. Confirm terms before any future raw redistribution.

Required citations: Clifford et al., Computing in Cardiology 42:273-276, 2015,
doi:10.1109/CIC.2015.7408639; dataset DOI above; Pollard et al., Nature Health
1:792-795, 2026, doi:10.1038/s44360-026-00096-z (current resource attribution).


Benchmark diagnostics: SCIENTIFIC_AUDIT.md, FALSE_NEGATIVE_ANALYSIS.md and
VEHICLE_INTERFACE_AND_SAFETY.md. Exact intervals, paired comparisons,
coverage diagnostics and per-record plots are in results/scientific_audit/.
