"""TRIAGE-GUARD Phase 1 deterministic policy simulation.
Not clinical software. No real CAN/vehicle actuation. Policy cutoffs are illustrative.
"""
from dataclasses import dataclass, asdict
from typing import Literal
import json, hmac, hashlib

Event = Literal['normal', 'seizure_like', 'cardiac_rhythm', 'uncertain']

@dataclass(frozen=True)
class Observation:
    id: str
    truth_event: str               # For experimental scenario labeling only
    truth_incapacity: bool        # For experimental scenario labeling only
    seizure_evidence: float       # Synthesized, NOT calibrated probability
    cardiac_evidence: float       # Synthesized, NOT calibrated probability
    medical_quality: float       # [0,1] illustrative
    capacity_evidence: float      # Synthesized incapacity evidence
    capacity_quality: float       # [0,1] illustrative
    driver_response: bool         # For simulation: verified responsiveness
    second_confirmation: bool    # From independent driver-capacity channel
    capability: bool             # Approved minimum risk maneuver capability
    within_odd: bool             # OEM validated operating design domain
    sensor_fresh: bool = True
    controller_healthy: bool = True
    note: str = ''

@dataclass(frozen=True)
class Decision:
    medical_class: str
    medical_warning: bool
    incapacity_confirmed: bool
    maneuver_request: bool       # ONLY a logical request, NEVER brake actuation
    reason: str


def medical_classification(o: Observation) -> str:
    if not o.sensor_fresh or o.medical_quality < .55:
        return 'uncertain'
    if o.seizure_evidence >= .7 and o.cardiac_evidence >= .7:
        return 'uncertain'  # Conflicting evidence is not arbitrarily assigned
    if o.seizure_evidence >= .7:
        return 'seizure_like'
    if o.cardiac_evidence >= .7:
        return 'cardiac_rhythm'
    return 'normal'


def triage_guard(o: Observation) -> Decision:
    """No model-controlled actuation; supervisor may only request a certified function.

    Verified driver response vetoes automated emergency request.
    Driver-unresponsive policy does NOT require a medical diagnosis.
    Medical measurement quality does NOT override independently verified capacity.
    """
    medical = medical_classification(o)
    warning = medical in ('seizure_like', 'cardiac_rhythm')
    capacity_valid = (o.sensor_fresh and o.controller_healthy and
                      o.capacity_quality >= .75)
    incapacity = (capacity_valid and not o.driver_response and
                  o.second_confirmation and o.capacity_evidence >= .8)
    permitted = (incapacity and o.capability and o.within_odd and
                 o.controller_healthy)
    if permitted:
        reason = 'verified_incapacity_and_authorized_capability'
    elif not o.controller_healthy:
        reason = 'controller_degraded_no_new_request'
    elif not capacity_valid:
        reason = 'capacity_evidence_untrusted'
    elif o.driver_response:
        reason = 'driver_responsive'
    elif not incapacity:
        reason = 'incapacity_not_independently_confirmed'
    else:
        reason = 'vehicle_capability_or_odd_unavailable'
    return Decision(medical, warning, incapacity, permitted, reason)


def baseline_single_sensor(o: Observation) -> bool:
    """Intentionally unsafe comparison: request on any alert evidence."""
    return max(o.seizure_evidence, o.cardiac_evidence,
               o.capacity_evidence) >= .7


def baseline_naive_fusion(o: Observation) -> bool:
    """Intentionally naive unweighted fusion with missing-quality blindness."""
    return (max(o.seizure_evidence, o.cardiac_evidence) +
            o.capacity_evidence) / 2 >= .63


def scenario_suite():
    """A manually specified test suite, not samples from a clinical distribution.
    Each case isolates a specific logic or fault condition.
    """
    O = Observation
    return [
      O('N1', 'normal', False,.1,.1,.95,.1,.95,True,False,True,True,note='normal'),
      O('N2', 'normal', False,.2,.2,.95,.3,.9,True,False,True,True,note='normal variation'),
      O('N3', 'normal', False,.85,.1,.95,.1,.9,True,False,True,True,note='motion artifact false seizure score'),
      O('N4', 'normal', False,.1,.85,.95,.1,.9,True,False,True,True,note='benign false cardiac score'),
      O('N5', 'normal', False,.1,.1,.95,.9,.9,True,False,True,True,note='responsive despite incapacity sensor high'),
      O('N6', 'normal', False,.1,.1,.15,.1,.9,True,False,True,True,note='low medical quality'),
      O('N7', 'normal', False,.8,.1,.2,.5,.9,True,False,True,True,note='motion artifact and poor medical quality'),
      O('N8', 'normal', False,.2,.1,.9,.85,.4,False,False,True,True,note='one low-quality capacity sensor'),
      O('N9', 'normal', False,.1,.1,.9,.85,.9,False,False,True,True,note='no independent corroboration'),
      O('N10','normal', False,.95,.95,.9,.15,.9,True,False,True,True,note='conflicting false medical clues'),
      O('S1','seizure_like',True,.92,.15,.95,.92,.95,False,True,True,True,note='confirmed incapacity'),
      O('S2','seizure_like',True,.85,.10,.85,.9,.9,False,True,True,True,note='confirmed incapacity'),
      O('S3','seizure_like',False,.91,.10,.9,.1,.9,True,False,True,True,note='event but driver responsive'),
      O('S4','seizure_like',True,.9,.1,.9,.92,.9,False,True,False,True,note='vehicle capability unavailable'),
      O('S5','seizure_like',True,.9,.1,.9,.92,.9,False,True,True,False,note='outside allowed ODD'),
      O('S6','seizure_like',True,.9,.1,.9,.92,.3,False,False,True,True,note='capacity sensor failed'),
      O('C1','cardiac_rhythm',True,.10,.95,.95,.91,.9,False,True,True,True,note='cardiac and incapacity'),
      O('C2','cardiac_rhythm',True,.10,.9,.9,.9,.8,False,True,True,True,note='cardiac and incapacity'),
      O('C3','cardiac_rhythm',False,.05,.94,.9,.1,.9,True,False,True,True,note='cardiac evidence but responsive'),
      O('C4','cardiac_rhythm',True,.05,.9,.12,.9,.92,False,True,True,True,note='ECG dropout but incapacity corroborated'),
      O('C5','cardiac_rhythm',True,.1,.9,.9,.91,.95,False,True,True,True,controller_healthy=False,note='controller fault'),
      O('C6','cardiac_rhythm',True,.1,.9,.9,.9,.9,False,True,True,True,sensor_fresh=False,note='stale sensor data'),
      O('U1','unknown',True,.1,.15,.9,.95,.9,False,True,True,True,note='incapacity etiology unknown'),
      O('U2','unknown',True,.1,.1,.9,.9,.9,False,True,False,True,note='incapacity but no maneuver capability'),
    ]


class SecureEnvelope:
    """Illustrative application-layer HMAC, not certified AUTOSAR SecOC.
    This protocol is not a CAN frame and is not a safe vehicle actuation interface.
    """
    def __init__(self, key: bytes):
        self.key = key
        self.highest_counter = {}
    def sign(self, sender: str, counter: int, expiry_ms: int, payload: dict) -> dict:
        obj = {'sender':sender, 'counter':counter, 'expiry_ms':expiry_ms, 'payload':payload}
        canonical = json.dumps(obj,sort_keys=True,separators=(',',':')).encode('utf8')
        return {**obj,'tag': hmac.new(self.key,canonical,hashlib.sha256).hexdigest()}
    def verify(self, msg:dict, now_ms:int, allowed_senders=('cabinguard',)) -> tuple[bool,str]:
        if msg.get('sender') not in allowed_senders:
            return False,'unauthorized_sender'
        unsigned = {k:v for k,v in msg.items() if k!='tag'}
        canonical = json.dumps(unsigned,sort_keys=True,separators=(',',':')).encode('utf8')
        expected = hmac.new(self.key,canonical,hashlib.sha256).hexdigest()
        if not isinstance(msg.get('tag'),str) or not hmac.compare_digest(expected,msg['tag']):
            return False,'invalid_integrity'
        if msg['expiry_ms'] < now_ms:
            return False,'expired'
        if msg['counter'] <= self.highest_counter.get(msg['sender'],-1):
            return False,'replay_or_out_of_order'
        self.highest_counter[msg['sender']] = msg['counter']
        return True,'accepted_for_policy_evaluation'


def run_scenarios():
    scenarios=scenario_suite()
    systems={'single_sensor':baseline_single_sensor,'naive_fusion':baseline_naive_fusion,
             'triage_guard':lambda o:triage_guard(o).maneuver_request}
    metrics={}
    for k,fn in systems.items():
        tp=fp=tn=fn_=0
        for o in scenarios:
            # Target: authorized request only when verified incapacitation and certified
            # maneuver capability, not just when 'truth_incapacity' is True.
            target = (o.truth_incapacity and o.capability and o.within_odd and
                      o.controller_healthy and o.sensor_fresh and
                      o.capacity_quality>=.75 and o.second_confirmation and not o.driver_response)
            p=bool(fn(o))
            if p and target: tp+=1
            elif p and not target: fp+=1
            elif not p and target: fn_+=1
            else:tn+=1
        metrics[k]={'scenario_count':len(scenarios),'correct_requests':tp,
                    'inappropriate_requests':fp,'missed_eligible_requests':fn_,
                    'correct_no_requests':tn}
    return metrics

if __name__ == '__main__':
    print(json.dumps(run_scenarios(),indent=2))
