"""CabinGuard proposed 48-byte CAN-FD *payload* reference format (software-only).

No CAN controller, ECU, V2X, safety certification, automotive key storage,
or emergency service is used. This is a non-OEM design exercise for Phase 1.
Protocol fields/encodings and authentication truncation are engineering choices,
not mandated by the competition or an implemented AUTOSAR SecOC profile.
"""
from dataclasses import dataclass
import hashlib
import hmac
import struct

HEADER = struct.Struct('>BBHIIQHBBBHBB3s')  # 32 bytes big endian
TAG_BYTES = 16                                # HMAC-SHA256 truncated, illustrative
TOTAL_BYTES = HEADER.size + TAG_BYTES        # 48 = legal CAN-FD payload length
CONTEXT = b'CabinGuard-reference-pdu-v1'
REQUEST, STATUS = 1, 2

@dataclass(frozen=True)
class ReferenceRequest:
    sender_id: int                  # approved endpoint identifier, not identity
    event_id: int
    counter: int
    created_ms: int                # simulated common time base
    valid_for_ms: int
    medical_code: int              # provisional classification, 0=unknown
    capacity_code: int             # 0=unknown; site-defined enumeration
    confidence_tier: int           # 0=unknown; NOT a calibrated probability
    sensor_health: int             # bitmask
    requested_function: int        # 0=none, 1=evaluate existing approved function
    status_flags: int = 0
    kind: int = REQUEST


def encode(payload: ReferenceRequest, key: bytes, arbitration_id: int) -> bytes:
    """Encode a proposed PDU; arbitration ID is supplied by simulator, NOT assigned to vehicle."""
    if len(key) < 16: raise ValueError('demo key too short')
    if payload.kind not in (REQUEST, STATUS): raise ValueError('invalid kind')
    if not 0 <= arbitration_id <= 0x1FFFFFFF: raise ValueError('invalid CAN identifier')
    if payload.valid_for_ms <= 0: raise ValueError('invalid lifetime')
    head = HEADER.pack(1, payload.kind, payload.sender_id, payload.event_id,
                       payload.counter, payload.created_ms, payload.valid_for_ms,
                       payload.medical_code, payload.capacity_code,
                       payload.confidence_tier, payload.sensor_health,
                       payload.requested_function, payload.status_flags, b'\0'*3)
    tag = hmac.new(key, CONTEXT + arbitration_id.to_bytes(4,'big') + head,
                   hashlib.sha256).digest()[:TAG_BYTES]
    return head + tag

class ReferenceReceiver:
    """Simulates gateway authentication, freshness and authorization.

    The remembered counter is in RAM: production anti-replay must handle restarts,
    synchronization, key rotation, compromises and replay across endpoints.
    """
    def __init__(self, approved_sender_keys: dict[int, bytes], arbitration_id: int):
        self.keys = dict(approved_sender_keys)
        self.arbitration_id = arbitration_id
        self.last_counters = {}

    def check(self, frame: bytes, now_ms: int) -> tuple[bool, str]:
        if len(frame) != TOTAL_BYTES:
            return False, 'bad_length'
        header, tag = frame[:HEADER.size], frame[HEADER.size:]
        (version, kind, sender, event_id, counter, created, lifetime,
         medical, capacity, confidence, health, requested, flags, reserve) = HEADER.unpack(header)
        if version != 1 or kind not in (REQUEST,STATUS) or reserve != b'\0'*3:
            return False, 'invalid_schema'
        key = self.keys.get(sender)
        if key is None:
            return False, 'unauthorized_sender'
        expected = hmac.new(key, CONTEXT + self.arbitration_id.to_bytes(4,'big') + header,
                            hashlib.sha256).digest()[:TAG_BYTES]
        if not hmac.compare_digest(expected, tag):
            return False, 'invalid_mac_or_context'
        if created > now_ms or now_ms - created > lifetime or lifetime == 0:
            return False, 'expired_or_future'
        if counter <= self.last_counters.get(sender, -1):
            return False, 'replayed_or_out_of_order'
        # Valid message is an input to *later* independent policy checks, not an actuation authorization.
        self.last_counters[sender] = counter
        return True, 'authenticated_candidate_for_independent_safety_evaluation'
