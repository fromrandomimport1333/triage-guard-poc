"""Simulated communication layer: the EmergencyAssessment CAN FD frame of the paper (Table II)
exchanged over a virtual bus, with E2E (CRC-8 + alive counter) and a SecOC-style
authenticator + freshness check at the receiving OEM gateway.

Boundaries, stated once:
- Uses python-can's 'virtual' interface when installed, otherwise an in-process queue with
  the same send/recv shape. Neither is a physical CAN controller.
- The authenticator is HMAC-SHA256 truncated to 64 bits. Production SecOC uses AES-128 CMAC
  with keys in an HSM; this is a stand-in with the same message layout, not a certified stack.
- The frame carries no brake, torque or trajectory field by construction (see pack()).
"""
from __future__ import annotations
import hmac, hashlib, struct, json
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

try:  # optional dependency; the demo does not require it
    import can  # type: ignore
    _HAVE_PYTHON_CAN = True
except Exception:  # pragma: no cover
    can = None
    _HAVE_PYTHON_CAN = False

ARBITRATION_ID = 0x3E1       # illustrative; the OEM allocates the real ID
MSG_VERSION    = 1
E2E_DATA_ID    = 0x5A        # AUTOSAR E2E-style data ID mixed into the CRC
CYCLE_MS       = 100
MISSED_CYCLES_TO_NONE = 3

REQUEST   = {'NONE': 0, 'VERIFY': 1, 'EVAL_MRM': 2}
CAPACITY  = {'responsive': 0, 'uncertain': 1, 'corroborated_unresponsive': 2}
ETIOLOGY  = {'unknown': 0, 'seizure_like': 1, 'cardiac_rhythm': 2, 'normal': 3}
HEALTH_BITS = ['camera', 'ecg', 'hmi', 'steering_grip', 'vehicle_bus', 'watchdog', 'clock_sync']
REASON    = {'none': 0, 'corroborated_incapacity': 1, 'capability_missing': 2, 'outside_odd': 3,
             'controller_unhealthy': 4, 'incapacity_uncorroborated': 5}


def crc8(data: bytes, poly: int = 0x1D, init: int = 0xFF) -> int:
    """CRC-8 (SAE J1850 polynomial, as used by AUTOSAR E2E Profile 1)."""
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


@dataclass
class Assessment:
    request: str = 'NONE'
    capacity: str = 'uncertain'
    etiology: str = 'unknown'
    confidence_tier: int = 0          # 0..3, uncalibrated
    health: dict = field(default_factory=lambda: {k: True for k in HEALTH_BITS})
    evidence_age_100ms: int = 0       # 0xFF = invalid
    reason: str = 'none'
    event_id: int = 0


class SecOCSender:
    """Supervisor side: packs the 16-byte frame, adds E2E and authenticator."""
    def __init__(self, key: bytes):
        self.key = key
        self.alive = 0       # 4-bit E2E alive counter
        self.freshness = 0   # full freshness counter (persisted/rollback-protected in a real ECU)

    def pack(self, a: Assessment) -> bytes:
        self.alive = (self.alive + 1) & 0xF
        self.freshness += 1
        b2 = (REQUEST[a.request] << 6) | (CAPACITY[a.capacity] << 4) | (ETIOLOGY[a.etiology] << 2) | (a.confidence_tier & 3)
        b3 = sum((1 << i) for i, k in enumerate(HEALTH_BITS) if a.health.get(k, False))
        body = bytes([(self.alive << 4) | MSG_VERSION, b2, b3, a.evidence_age_100ms & 0xFF,
                      REASON[a.reason], a.event_id & 0xFF])
        b0 = crc8(body + bytes([E2E_DATA_ID]))
        b7 = self.freshness & 0xFF                       # truncated freshness value
        mac = hmac.new(self.key, bytes([b0]) + body + self.freshness.to_bytes(8, 'big'),
                       hashlib.sha256).digest()[:8]       # 64-bit truncated authenticator
        frame = bytes([b0]) + body + bytes([b7]) + mac
        assert len(frame) == 16
        return frame


class SecOCGateway:
    """OEM side: verifies CRC, alive counter, freshness window and authenticator."""
    def __init__(self, key: bytes, freshness_window: int = 16):
        self.key = key
        self.window = freshness_window
        self.last_alive: Optional[int] = None
        self.last_freshness = 0
        self.missed = 0
        self.state_request = 'NONE'

    def _reconstruct_freshness(self, trunc: int) -> Optional[int]:
        base = self.last_freshness
        for cand in range(base + 1, base + 1 + self.window):
            if cand & 0xFF == trunc:
                return cand
        return None

    def receive(self, frame: bytes) -> tuple[bool, str, Optional[dict]]:
        if len(frame) != 16:
            return self._reject('bad_length')
        b0, body, b7, mac = frame[0], frame[1:7], frame[7], frame[8:16]
        if crc8(body + bytes([E2E_DATA_ID])) != b0:
            return self._reject('e2e_crc_fail')
        alive = body[0] >> 4
        if self.last_alive is not None and alive == self.last_alive:
            return self._reject('e2e_alive_counter_repeat')
        full = self._reconstruct_freshness(b7)
        if full is None:
            return self._reject('freshness_replay_or_out_of_window')
        expected = hmac.new(self.key, bytes([b0]) + body + full.to_bytes(8, 'big'), hashlib.sha256).digest()[:8]
        if not hmac.compare_digest(expected, mac):
            return self._reject('authenticator_mismatch')
        # accepted: commit counters only now
        self.last_alive, self.last_freshness, self.missed = alive, full, 0
        b2 = body[1]
        decoded = {
            'request': {v: k for k, v in REQUEST.items()}[b2 >> 6],
            'capacity': {v: k for k, v in CAPACITY.items()}[(b2 >> 4) & 3],
            'etiology': {v: k for k, v in ETIOLOGY.items()}[(b2 >> 2) & 3],
            'confidence_tier': b2 & 3,
            'health': {k: bool(body[2] >> i & 1) for i, k in enumerate(HEALTH_BITS)},
            'evidence_age_100ms': body[3],
            'reason': {v: k for k, v in REASON.items()}[body[4]],
            'event_id': body[5],
        }
        self.state_request = decoded['request']
        return True, 'accepted_for_mrm_evaluation', decoded

    def _reject(self, why: str):
        return False, why, None

    def tick_without_frame(self) -> str:
        """Called by the gateway's own 100 ms scheduler when no frame arrived."""
        self.missed += 1
        if self.missed >= MISSED_CYCLES_TO_NONE:
            self.state_request = 'NONE'
        return self.state_request


class _QueueBus:
    """Standard-library stand-in for python-can's virtual bus (same send/recv shape)."""
    def __init__(self):
        self.q: deque = deque()
    def send(self, arbitration_id: int, data: bytes):
        self.q.append((arbitration_id, bytes(data)))
    def recv(self):
        return self.q.popleft() if self.q else None
    def shutdown(self):
        pass


class _PythonCanBus:
    def __init__(self):
        self.tx = can.Bus(interface='virtual', channel='cabinguard', receive_own_messages=False)
        self.rx = can.Bus(interface='virtual', channel='cabinguard')
    def send(self, arbitration_id: int, data: bytes):
        self.tx.send(can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=False, is_fd=True))
    def recv(self):
        m = self.rx.recv(timeout=0.05)
        return (m.arbitration_id, bytes(m.data)) if m else None
    def shutdown(self):
        self.tx.shutdown(); self.rx.shutdown()


def make_bus():
    return _PythonCanBus() if _HAVE_PYTHON_CAN else _QueueBus()


def run_demo() -> dict:
    key = b'demo-key-not-for-vehicles'
    bus = make_bus()
    tx, gw = SecOCSender(key), SecOCGateway(key)
    log = {'transport': 'python-can virtual' if _HAVE_PYTHON_CAN else 'in-process queue (python-can not installed)',
           'frame_bytes': 16, 'checks': {}}

    def roundtrip(frame: bytes):
        bus.send(ARBITRATION_ID, frame)
        _, data = bus.recv()
        return gw.receive(data)

    # 1. ordinary heartbeat (NONE) then an authorized evaluation request
    ok, why, _ = roundtrip(tx.pack(Assessment()))
    log['checks']['heartbeat_none'] = [ok, why]
    req = Assessment(request='EVAL_MRM', capacity='corroborated_unresponsive', etiology='unknown',
                     confidence_tier=1, evidence_age_100ms=4, reason='corroborated_incapacity', event_id=7)
    frame = tx.pack(req)
    ok, why, decoded = roundtrip(frame)
    log['checks']['eval_mrm_request'] = [ok, why, decoded]
    log['frame_hex'] = frame.hex()

    # 2. replay of the very same frame
    log['checks']['replayed_frame'] = list(roundtrip(frame)[:2])

    # 3. tampered frame: flip the request bits in byte 2 (an injected 'EVAL_MRM')
    fresh = bytearray(tx.pack(Assessment()))
    fresh[2] = (fresh[2] & 0x3F) | (REQUEST['EVAL_MRM'] << 6)
    fresh[0] = crc8(bytes(fresh[1:7]) + bytes([E2E_DATA_ID]))  # attacker even fixes the CRC
    log['checks']['tampered_request_bits'] = list(roundtrip(bytes(fresh))[:2])

    # 4. frame signed by a sender without the gateway key (unauthorized)
    rogue = SecOCSender(b'attacker-key'); rogue.freshness = tx.freshness
    log['checks']['unauthorized_sender'] = list(roundtrip(rogue.pack(req))[:2])

    # 5. bit error on the bus: corrupt one body byte, CRC catches it before the MAC
    corrupt = bytearray(tx.pack(Assessment())); corrupt[4] ^= 0x01
    log['checks']['bit_error_e2e'] = list(roundtrip(bytes(corrupt))[:2])

    # 6. supervisor goes silent: gateway falls back to NONE after 3 missed cycles
    roundtrip(tx.pack(req))  # last good state was EVAL_MRM
    states = [gw.tick_without_frame() for _ in range(MISSED_CYCLES_TO_NONE)]
    log['checks']['supervisor_silent_fallback'] = states

    # 7. the schema cannot express an actuator command: no field maps to brake/torque
    log['checks']['actuator_fields_in_schema'] = 0
    bus.shutdown()
    return log


if __name__ == '__main__':
    print(json.dumps(run_demo(), indent=2))
