"""Observable scenario labels for the synthetic demo, never actuation authority.

The legacy cardiac_rhythm code remains supporting physiological evidence. These
labels are neither diagnoses nor a trained or validated three-class detector.
"""
from strict_safety_policy import strict_capacity,valid_signal
from src.triage_guard_cr01 import MIN_MEDICAL_QUALITY,MEDICAL_SCORE_CUTOFF

def observable_scenario(observation,previously_responsive=False):
    motor=observation.camera_motor_score
    motor_valid=valid_signal(motor,observation.time_ms,MIN_MEDICAL_QUALITY)
    capacity=strict_capacity(observation)
    if motor_valid and motor.value >= MEDICAL_SCORE_CUTOFF:
        return 'seizure_like_motor_activity'
    if (previously_responsive is True and capacity=='corroborated_unresponsive'
            and motor_valid):
        return 'suspected_transient_loss_of_responsiveness'
    cardiac=observation.ecg_rhythm_score
    if (capacity=='responsive' and motor_valid
            and valid_signal(cardiac,observation.time_ms,MIN_MEDICAL_QUALITY)
            and cardiac.value < MEDICAL_SCORE_CUTOFF):
        return 'normal_driving'
    return 'uncertain_event'
