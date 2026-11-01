"""Input-validity adversarial cases, synthetic only."""
from dataclasses import replace
import pytest
from strict_safety_policy import strict_decide, strict_medical_hypothesis
from tests.test_strict_hard_negatives import base

@pytest.mark.parametrize('bad', [float('nan'),float('inf'),-1.0, 1.01])
def test_invalid_medical_score_does_not_create_diagnosis(bad):
    b=base()
    o=replace(b,camera_motor_score=replace(b.camera_motor_score,value=bad))
    assert strict_medical_hypothesis(o)=='unknown'
    assert strict_decide(o).oem_evaluation_request  # valid independent capacity still eligible

def test_conflicting_high_quality_medical_patterns_abstain():
    b=base()
    o=replace(b,camera_motor_score=replace(b.camera_motor_score,value=.94),
              ecg_rhythm_score=replace(b.ecg_rhythm_score,value=.91))
    assert strict_medical_hypothesis(o)=='unknown'

def test_bad_measurements_do_not_count_as_normal():
    b=base()
    o=replace(b,hmi=replace(b.hmi,state='responded'),
              ecg_rhythm_score=replace(b.ecg_rhythm_score,value=float('inf')))
    assert strict_medical_hypothesis(o)=='unknown'
    assert not strict_decide(o).oem_evaluation_request
