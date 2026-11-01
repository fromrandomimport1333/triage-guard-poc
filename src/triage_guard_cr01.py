"""CR-01 approved concept simulator (not medical software or vehicle controller).
All scores and evidence are synthetic; all thresholds/timings are illustrative.
No real CAN bus, OEM minimum-risk function, EMS endpoint or contacts are invoked.
"""
from dataclasses import dataclass
from typing import Literal
from .triage_guard import scenario_suite as previous_24_scenarios, SecureEnvelope

MEDICAL_SCORE_CUTOFF = 0.70   # synthetic comparator, NOT a clinical threshold
MIN_MEDICAL_QUALITY = 0.55  # arbitrary engineering test constant
MIN_CAPACITY_QUALITY = 0.75 # arbitrary engineering test constant
CAPACITY_SCORE_CUTOFF = 0.80
MAX_EVIDENCE_AGE_MS = 1500  # synthetic timing assumption, unvalidated
ONSET_PRECEDENCE_MS = 2000  # Delta in Eq. (1): rhythm onset must lead motor onset by this margin

@dataclass(frozen=True)
class Signal:
    source_id: str
    value: float
    quality: float
    at_ms: int
    available: bool = True
    onset_ms: int | None = None   # first time the expert's alarm crossed its cutoff; None = unknown
    # A signal is not independent of another feature with the same source_id.
    def trusted(self, now_ms:int, threshold:float) -> bool:
        age = now_ms - self.at_ms
        return self.available and 0 <= age <= MAX_EVIDENCE_AGE_MS and self.quality >= threshold

@dataclass(frozen=True)
class DriverResponse:
    state: Literal['responded', 'no_response', 'unknown']
    source_id: str
    at_ms: int
    valid: bool = True
    def trusted(self, now_ms: int) -> bool:
        age = now_ms - self.at_ms
        return self.valid and 0 <= age <= MAX_EVIDENCE_AGE_MS

@dataclass(frozen=True)
class CR01Observation:
    case_id: str
    time_ms: int
    truth_medical: str                 # scenario metadata, never provided to policy
    truth_incapacity: bool            # scenario metadata, never provided to policy
    camera_motor_score: Signal
    ecg_rhythm_score: Signal
    capacity_evidence: Signal
    hmi: DriverResponse
    corroboration: Signal             # source group independent of the HMI
    oem_capability: bool
    oem_within_odd: bool
    oem_controller_healthy: bool
    trusted_contact_opt_in: bool = True
    ems_interface_authorized: bool = True
    network_available: bool = True

@dataclass(frozen=True)
class CR01Decision:
    medical: str                     # normal / seizure_like / cardiac_rhythm / unknown
    capacity: str                    # responsive / corroborated_unresponsive / uncertain
    local_warning: bool
    oem_evaluation_request: bool     # request only, never any actuator value
    contact_submission_eligible: bool
    ems_submission_eligible: bool
    notification_status: str         # no real delivery or acknowledgement
    rationale: str


def medical_hypothesis(o:CR01Observation) -> str:
    cam_valid=o.camera_motor_score.trusted(o.time_ms, MIN_MEDICAL_QUALITY)
    ecg_valid=o.ecg_rhythm_score.trusted(o.time_ms, MIN_MEDICAL_QUALITY)
    s=cam_valid and o.camera_motor_score.value >= MEDICAL_SCORE_CUTOFF
    c=ecg_valid and o.ecg_rhythm_score.value >= MEDICAL_SCORE_CUTOFF
    if s and c:
        # Eq. (1) precedence term P: a rhythm disturbance that leads the motor
        # event by >= Delta is consistent with arrhythmic syncope (jerks follow
        # hypoperfusion). Motor-first or unknown onsets stay 'unknown'.
        tm, tc = o.camera_motor_score.onset_ms, o.ecg_rhythm_score.onset_ms
        if tm is not None and tc is not None and tm >= tc + ONSET_PRECEDENCE_MS:
            return 'cardiac_rhythm'
        return 'unknown'  # competing etiologies without established order
    if s: return 'seizure_like'
    if c: return 'cardiac_rhythm'
    # Unknown cause of independent incapacity is not normal driving.
    if (cam_valid and ecg_valid and o.hmi.trusted(o.time_ms) and
        o.hmi.state == 'responded'):
        return 'normal'
    return 'unknown'


def capacity_state(o:CR01Observation) -> str:
    if o.hmi.trusted(o.time_ms) and o.hmi.state=='responded':
        return 'responsive'
    if (o.hmi.trusted(o.time_ms) and o.hmi.state=='no_response' and
        o.capacity_evidence.trusted(o.time_ms,MIN_CAPACITY_QUALITY) and
        o.corroboration.trusted(o.time_ms,MIN_CAPACITY_QUALITY) and
        o.hmi.source_id != o.corroboration.source_id and
        o.capacity_evidence.value >= CAPACITY_SCORE_CUTOFF and
        o.corroboration.value >= CAPACITY_SCORE_CUTOFF):
        return 'corroborated_unresponsive'
    return 'uncertain'


def decide(o:CR01Observation) -> CR01Decision:
    m=medical_hypothesis(o)
    cap=capacity_state(o)
    unresp=(cap=='corroborated_unresponsive')
    # Medical class does NOT gate confirmed incapacity; medical event alone does NOT authorize action.
    authorized=unresp and o.oem_controller_healthy and o.oem_capability and o.oem_within_odd
    # Separate notification policy. No API call made; this is eligibility only.
    contact=unresp and o.trusted_contact_opt_in and o.network_available
    ems=unresp and o.ems_interface_authorized and o.network_available
    if not o.network_available and unresp:
        comm='network_unavailable_no_delivery'
    elif contact or ems:
        comm='simulation_eligible_no_transmission_or_ack'
    else:
        comm='no_notification_request'
    if authorized:
        reason='corroborated_incapacity_oem_evaluation_eligible'
    elif unresp and not o.oem_controller_healthy:
        reason='controller_unhealthy_no_new_maneuver_request'
    elif unresp and not (o.oem_capability and o.oem_within_odd):
        reason='missing_approved_capability_or_outside_odd'
    elif cap=='responsive':
        reason='driver_responsive'
    else:
        reason='incapacity_not_independently_corrobated'
    return CR01Decision(m,cap,m in ('seizure_like','cardiac_rhythm') or unresp,
                        authorized,contact,ems,comm,reason)


def convert_legacy_suite():
    """Traceable adapter for the PREVIOUS 24 synthetic situations.
    The original measurements and scenario labels remain synthetic. We reinterpret
    independent capacity observation as steering corroboration; this is a DESIGN ASSUMPTION.
    """
    observations=[]
    for v in previous_24_scenarios():
        now=10_000
        medical_t=now if v.sensor_fresh else now-4_000
        hmi=DriverResponse('responded' if v.driver_response else 'no_response', 'hmi_button',now)
        cam=Signal('camera',v.seizure_evidence,v.medical_quality,medical_t)
        ecg=Signal('ecg',v.cardiac_evidence,v.medical_quality,medical_t)
        cap=Signal('vehicle_steering',v.capacity_evidence,v.capacity_quality,now)
        corr=Signal('vehicle_steering',v.capacity_evidence if v.second_confirmation else 0.0,
                    v.capacity_quality,now,available=v.second_confirmation)
        observations.append(CR01Observation(v.id,now,v.truth_event,v.truth_incapacity,
                cam,ecg,cap,hmi,corr,v.capability,v.within_odd,v.controller_healthy))
    return observations


def cr01_extra_cases():
    """Explicit boundary/failure cases added after sponsor's CR-01 decisions."""
    from dataclasses import replace
    start={v.case_id:v for v in convert_legacy_suite()}
    good=start['C1']
    now=good.time_ms
    return [
        replace(good,case_id='X1_ECG_STALE',ecg_rhythm_score=replace(good.ecg_rhythm_score,at_ms=now-5_000)),
        replace(good,case_id='X2_CAMERA_STALE',camera_motor_score=replace(good.camera_motor_score,at_ms=now-5_000)),
        replace(good,case_id='X3_CAPACITY_STALE',capacity_evidence=replace(good.capacity_evidence,at_ms=now-5_000),corroboration=replace(good.corroboration,at_ms=now-5_000)),
        replace(good,case_id='X4_NO_NETWORK',network_available=False),
        replace(good,case_id='X5_NO_CONTACT_CONSENT',trusted_contact_opt_in=False),
        replace(good,case_id='X6_NO_EMS_AUTHORIZATION',ems_interface_authorized=False),
        replace(good,case_id='X7_HMI_SOURCE_COLLISION',hmi=replace(good.hmi,source_id='vehicle_steering')),
        replace(good,case_id='X8_HMI_UNVERIFIED',hmi=replace(good.hmi,valid=False)),
    ]


def onset_ordered_cases():
    """Both experts alarm; only the ORDER of onsets differs (Eq. (1) precedence term).
    Synthetic timings; the Delta margin is an engineering placeholder, not a clinical constant.
    """
    from dataclasses import replace
    good={v.case_id:v for v in convert_legacy_suite()}['C1']
    now=good.time_ms
    both_cam=replace(good.camera_motor_score,value=0.90)
    both_ecg=replace(good.ecg_rhythm_score,value=0.92)
    return [
        # rhythm first, jerks 6 s later: arrhythmic syncope pattern -> cardiac_rhythm
        replace(good,case_id='X9_CARDIAC_THEN_MOTOR',truth_medical='cardiac_rhythm',
                camera_motor_score=replace(both_cam,onset_ms=now-2_000),
                ecg_rhythm_score=replace(both_ecg,onset_ms=now-8_000)),
        # jerks first, rhythm change 5 s later: ictal pattern, but a sinus/narrow
        # morphology check is not modeled here, so the design abstains -> unknown
        replace(good,case_id='X10_MOTOR_THEN_CARDIAC',truth_medical='seizure_like',
                camera_motor_score=replace(both_cam,onset_ms=now-8_000),
                ecg_rhythm_score=replace(both_ecg,onset_ms=now-3_000)),
        # both alarms, onsets inside the Delta margin: no established order -> unknown
        replace(good,case_id='X11_ONSETS_UNRESOLVED',truth_medical='unknown',
                camera_motor_score=replace(both_cam,onset_ms=now-4_000),
                ecg_rhythm_score=replace(both_ecg,onset_ms=now-5_000)),
    ]


def all_cases():
    return convert_legacy_suite()+cr01_extra_cases()+onset_ordered_cases()


def run_cr01():
    records=[]
    for o in all_cases():
        d=decide(o)
        records.append({'scenario':o.case_id,'truth_event':o.truth_medical,
            'medical_output':d.medical,'capacity_output':d.capacity,
            'oem_request':d.oem_evaluation_request,'contact_eligible':d.contact_submission_eligible,
            'ems_eligible':d.ems_submission_eligible,'notification_status':d.notification_status,
            'reason':d.rationale})
    return records
