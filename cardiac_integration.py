"""Adapter to existing synthetic medical/capacity policy; ICU != driver diagnosis."""
from dataclasses import replace
import math
from src.triage_guard_cr01 import Signal

def attach_cardiac(observation,result):
    # A rejected ICU alarm does not establish normal driving. Preserve as unknown.
    score=result.get('score')
    supported=(result.get('abstain') is False and result.get('preserve_alarm') is True
               and isinstance(score,(int,float)) and not isinstance(score,bool)
               and math.isfinite(score) and .7 <= score <= 1.)
    evidence=Signal('icu_replay_cardiac',.85 if supported else 0.,1. if supported else 0.,
                    observation.time_ms,available=supported)
    return replace(observation,ecg_rhythm_score=evidence)
