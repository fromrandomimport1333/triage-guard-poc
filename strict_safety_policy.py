"""Supplemental CabinGuard Phase-1 strict provenance gate.

Only a formal synthetic test of request eligibility, NOT medical diagnosis.
It intentionally rejects legacy cases whose two supposedly corroborating
observations originate from the same physical source. This is a stricter
policy than triage_guard_cr01 and does not replace OEM safety judgment.
"""
from dataclasses import replace
import math
from src.triage_guard_cr01 import (
    CR01Observation, CR01Decision,decide,MIN_CAPACITY_QUALITY, MIN_MEDICAL_QUALITY,
    MEDICAL_SCORE_CUTOFF,CAPACITY_SCORE_CUTOFF,MAX_EVIDENCE_AGE_MS
)


def valid_signal(s, at_ms, cutoff):
    return (bool(s.source_id and s.source_id.strip())
            and isinstance(s.at_ms,int) and isinstance(at_ms,int)
            and isinstance(s.value,(int,float)) and math.isfinite(s.value)
            and 0 <= float(s.value) <= 1
            and isinstance(s.quality,(int,float)) and math.isfinite(s.quality)
            and 0 <= float(s.quality) <= 1
            and s.trusted(at_ms,cutoff))


def strict_capacity(o:CR01Observation):
    """Requires valid HMI nonresponse plus TWO source-distinct corroborations.

    This three-source policy is a deliberately conservative design hypothesis.
    There is NO empirical claim that it is clinically optimal.
    """
    hmi=o.hmi
    if hmi.state=='responded' and hmi.trusted(o.time_ms) and hmi.source_id.strip():
        return 'responsive'
    if hmi.state!='no_response' or not hmi.trusted(o.time_ms) or not hmi.source_id.strip():
        return 'uncertain'
    samples=(o.capacity_evidence,o.corroboration)
    if len({hmi.source_id,*[s.source_id for s in samples]})!=3:
        return 'uncertain'
    if all(valid_signal(s,o.time_ms,MIN_CAPACITY_QUALITY)
           and s.value>=CAPACITY_SCORE_CUTOFF for s in samples):
        return 'corroborated_unresponsive'
    return 'uncertain'


def strict_medical_hypothesis(o: CR01Observation) -> str:
    """Finite, bounded evidence only. This is NOT a medical diagnostic model."""
    cv = valid_signal(o.camera_motor_score, o.time_ms, MIN_MEDICAL_QUALITY)
    ev = valid_signal(o.ecg_rhythm_score, o.time_ms, MIN_MEDICAL_QUALITY)
    seizure = cv and o.camera_motor_score.value >= MEDICAL_SCORE_CUTOFF
    cardiac = ev and o.ecg_rhythm_score.value >= MEDICAL_SCORE_CUTOFF
    if seizure and cardiac:
        return 'unknown'  # contradictory or simultaneous hypotheses
    if seizure:
        return 'seizure_like'
    if cardiac:
        return 'cardiac_rhythm'
    if cv and ev and o.hmi.trusted(o.time_ms) and o.hmi.state == 'responded':
        return 'normal'
    return 'unknown'


def strict_decide(o: CR01Observation) -> CR01Decision:
    baseline = decide(o)
    cap = strict_capacity(o)
    med = strict_medical_hypothesis(o)
    if cap == 'corroborated_unresponsive':
        # Baseline can emit a *request for evaluation*, never actuator values.
        return replace(baseline, medical=med, capacity=cap, local_warning=True)
    # Insufficient corroboration blocks newly requested vehicle functions.
    return replace(baseline, medical=med, capacity=cap, oem_evaluation_request=False,
                   contact_submission_eligible=False, ems_submission_eligible=False,
                   notification_status='no_notification_request',
                   local_warning=med in ('seizure_like','cardiac_rhythm'),
                   rationale='strict_declared_source_corroboration_insufficient')
