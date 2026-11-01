"""Software-only PDU checks; these are not physical CAN or safety tests."""
from dataclasses import replace
from src.reference_canfd import ReferenceRequest, ReferenceReceiver, encode, TOTAL_BYTES
KEY=b'non-production-32-byte-sim-secret!!'
ID=0x123  # example local context for tests, NOT OEM-assigned CAN ID

def example():
    return ReferenceRequest(1,1001,1,20000,1500,2,1,0,0b111,1)

def test_exact_can_fd_length_and_legitimate_candidate():
    frame=encode(example(),KEY,ID)
    assert len(frame)==TOTAL_BYTES==48
    assert ReferenceReceiver({1:KEY},ID).check(frame,20050)[0]

def test_replay_rejection():
    rx=ReferenceReceiver({1:KEY},ID)
    frame=encode(example(),KEY,ID)
    assert rx.check(frame,20001)[0]
    assert rx.check(frame,20002)==(False,'replayed_or_out_of_order')

def test_payload_tampering_rejected():
    frame=bytearray(encode(example(),KEY,ID))
    frame[16]^=0x01
    assert ReferenceReceiver({1:KEY},ID).check(bytes(frame),20050)[1]=='invalid_mac_or_context'

def test_wrong_context_rejected():
    assert ReferenceReceiver({1:KEY},ID+1).check(encode(example(),KEY,ID),20050)[1]=='invalid_mac_or_context'

def test_stale_and_future_rejected():
    frame=encode(example(),KEY,ID)
    rx=ReferenceReceiver({1:KEY},ID)
    assert rx.check(frame,24000)[1]=='expired_or_future'
    assert rx.check(frame,19000)[1]=='expired_or_future'

def test_unauthorized_source_and_invalid_length_rejected():
    frame=encode(example(),KEY,ID)
    rx=ReferenceReceiver({},ID)
    assert rx.check(frame,20050)[1]=='unauthorized_sender'
    assert rx.check(frame[:-1],20050)[1]=='bad_length'
