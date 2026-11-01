"""CabinGuard Phase-1 TEMPORAL software-in-the-loop assurance demonstrator.

This is a policy experiment and authenticated message *simulation*, not medical
classification, a CAN transport, a minimum-risk maneuver or an EMS integration.
All timing/persistence constants and simulated events are hypothetical.

Safety ownership: OEM remains solely responsible for maneuver decisions and control.
The event gate can emit only an evaluation candidate, never actuator commands.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Optional
from strict_safety_policy import strict_decide
from src.triage_guard_cr01 import CR01Observation
from src.reference_canfd import ReferenceRequest, ReferenceReceiver, HEADER, STATUS, REQUEST, encode

# Purely illustrative engineering policy constants. NO validated clinical timing.
REQUIRED_SEQUENTIAL_CONFIRMATIONS = 2
MAX_CONFIRMATION_GAP_MS = 1500
OEM_ACK_TIMEOUT_MS = 1800
REQUEST_LIFETIME_MS = 1600

@dataclass(frozen=True)
class EventResult:
    time_ms: int
    medical: str
    capacity: str
    local_warning: bool
    stage: str
    request: bool
    event_id: Optional[int]
    contacts_eligible: bool
    ems_eligible: bool
    reason: str
    evidence_receipt_hash: str


class TemporalAssurance:
    """Serialized simulation policy with a minimal event and ACK lifecycle.

    Monotonic clock is an external assumption. Requires explicit restart/freshness
    strategy for real-world deployment. Event IDs are simple test identifiers.
    """
    def __init__(self, approved_controller_keys: dict[int, bytes] | None = None,
                 can_id: int = 0x121):
        self.time_ms = -1
        self.confirmations = 0
        self.last_confirmation_ms: Optional[int] = None
        self.pending_event: Optional[int] = None
        self.requested_at: Optional[int] = None
        self.completed_stage: Optional[str] = None
        self.next_event_id = 1
        self.can_id = can_id  # illustrative controller STATUS CAN context, not allocated
        self.request_can_id = 0x120  # illustrative distinct request CAN context
        self.receiver = ReferenceReceiver(approved_controller_keys or {}, can_id)
        self.receipts: list[dict] = []
        self.last_hash = '0' * 64
        self.last_eligible_decision = None

    def _receipt(self, time_ms: int, med: str, cap: str, stage: str,
                 event_id: Optional[int], reason: str) -> str:
        # Explicitly omit images, full ECG signals, raw scores, identities and location.
        entry = dict(time_ms=time_ms, medical_hypothesis=med, capacity=cap,
                     stage=stage, event_id=event_id, reason=reason, previous=self.last_hash)
        blob = json.dumps(entry, sort_keys=True, separators=(',', ':')).encode()
        entry['sha256'] = hashlib.sha256(blob).hexdigest()
        self.receipts.append(entry)
        self.last_hash = entry['sha256']
        return entry['sha256']

    def step(self, o: CR01Observation) -> EventResult:
        # An invalid ordering must not alter the event state or arm a new request.
        if not isinstance(o.time_ms, int) or o.time_ms <= self.time_ms:
            h = self._receipt(self.time_ms, 'unknown', 'uncertain',
                              'INPUT_REJECTED', self.pending_event, 'non_monotonic_time')
            return EventResult(self.time_ms, 'unknown', 'uncertain', False,
                               'INPUT_REJECTED', False, self.pending_event,
                               False, False, 'non_monotonic_time', h)
        self.time_ms = o.time_ms
        d = strict_decide(o)
        self.last_eligible_decision = d
        stage = 'MONITOR'
        reason = 'monitoring'
        request = False
        event_id = self.pending_event
        contacts = False
        ems = False

        if self.completed_stage:
            stage = self.completed_stage
            reason = 'event_terminal_no_implicit_retrigger'
            event_id = self.next_event_id - 1
        elif self.pending_event is not None:
            if self.requested_at is not None and self.time_ms - self.requested_at > OEM_ACK_TIMEOUT_MS:
                stage = 'ACK_TIMEOUT'
                reason = 'oem_ack_timeout_no_assumed_maneuver'
                self.pending_event = None
                self.completed_stage = stage
            else:
                stage = 'WAITING_OEM_ACK'
                reason = 'request_already_emitted_no_retry'
        elif d.oem_evaluation_request:
            if (self.last_confirmation_ms is None or
                self.time_ms - self.last_confirmation_ms > MAX_CONFIRMATION_GAP_MS):
                self.confirmations = 1
            else:
                self.confirmations += 1
            self.last_confirmation_ms = self.time_ms
            if self.confirmations >= REQUIRED_SEQUENTIAL_CONFIRMATIONS:
                self.pending_event = self.next_event_id
                event_id = self.pending_event
                self.next_event_id += 1
                self.requested_at = self.time_ms
                stage = 'WAITING_OEM_ACK'
                reason = 'new_evaluation_request_only'
                request = True
                contacts = bool(d.contact_submission_eligible)
                ems = bool(d.ems_submission_eligible)
            else:
                stage = 'VERIFYING'
                reason = 'first_of_two_temporary_confirmations'
        else:
            self.confirmations = 0
            self.last_confirmation_ms = None
            if d.medical in ('seizure_like', 'cardiac_rhythm'):
                stage = 'MEDICAL_WARNING'
                reason = 'medical_suspicion_without_capacity_confirmation'
            elif d.capacity == 'uncertain':
                stage = 'DEGRADED_MONITOR'
                reason = 'capacity_evidence_insufficient'
        receipt = self._receipt(self.time_ms, d.medical, d.capacity, stage,
                                event_id, reason)
        return EventResult(self.time_ms, d.medical, d.capacity,
                           bool(d.local_warning), stage, request, event_id,
                           contacts, ems, reason, receipt)

    def process_oem_status(self, frame: bytes, now_ms: int) -> tuple[bool, str]:
        """ACK accepts only a receiver-authenticated status PDU for the pending event.

        This is NOT a physical CAN ACK nor proof of successful vehicle maneuver.
        """
        if self.pending_event is None:
            return False, 'no_outstanding_request'
        if not isinstance(now_ms, int) or now_ms < self.time_ms:
            return False, 'invalid_time'
        if now_ms - self.requested_at > OEM_ACK_TIMEOUT_MS:
            self.completed_stage = 'ACK_TIMEOUT'
            self.pending_event = None
            return False, 'ack_after_timeout'
        # Validate ACK semantics BEFORE consuming the receiver's replay counter.
        # Otherwise even an authenticated but irrelevant event could consume a
        # legitimate counter and deny service to the awaited ACK.
        if len(frame) != HEADER.size + 16:
            return False, 'bad_length'
        payload = HEADER.unpack(frame[:HEADER.size])
        kind, event_id, requested_function, status_flags = payload[1], payload[3], payload[11], payload[12]
        if kind != STATUS:
            return False, 'not_a_controller_status'
        if event_id != self.pending_event:
            return False, 'event_id_mismatch'
        if requested_function != 1 or status_flags not in (1, 2):
            return False, 'unsupported_status'
        ok, reason = self.receiver.check(frame, now_ms)
        if not ok:
            return False, reason
        self.completed_stage = 'OEM_ACCEPTED_REQUEST' if status_flags == 1 else 'OEM_DECLINED_REQUEST'
        self.time_ms = now_ms  # accepted status advances the event time frontier
        self.pending_event = None
        self._receipt(now_ms, 'not_reassessed', 'not_reassessed', self.completed_stage,
                      event_id, 'authenticated_oem_status_not_maneuver_completion')
        return True, self.completed_stage


def verify_receipt_chain(receipts: list[dict]) -> bool:
    """Detect accidental alteration under a trusted starting digest.

    NOT a tamper-resistant or authenticated audit system: an attacker with full
    write access could rebuild all hashes. Use only as an illustrative check.
    """
    previous = '0' * 64
    for rec in receipts:
        if rec.get('previous') != previous or 'sha256' not in rec:
            return False
        payload = {k:v for k,v in rec.items() if k != 'sha256'}
        candidate = hashlib.sha256(json.dumps(payload,sort_keys=True,
                               separators=(',',':')).encode()).hexdigest()
        if rec['sha256'] != candidate:
            return False
        previous = candidate
    return True


def demo_status_frame(event_id: int, now_ms: int, key: bytes, can_id: int,
                      accepted: bool = True, counter: int = 1, sender: int = 2):
    """Make synthetic OEM status. Real ECUs must use OEM-defined authentication."""
    return encode(ReferenceRequest(sender_id=sender, event_id=event_id,
             counter=counter, created_ms=now_ms, valid_for_ms=REQUEST_LIFETIME_MS,
             medical_code=0, capacity_code=0, confidence_tier=0,
             sensor_health=0, requested_function=1,
             status_flags=(1 if accepted else 2), kind=STATUS), key, can_id)
