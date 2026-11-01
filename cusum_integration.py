"""Optional shadow monitoring of the existing SYNTHETIC camera motor score.

No CUSUM output is inserted into CR01Observation or used for vehicle authority.
The existing motor/etiology branch and TemporalAssurance remain unchanged.
"""
from dataclasses import dataclass
from sequential_monitor import MonitorConfig,MonitorResult,ScoreObservation,SequentialMonitor
from scenario_reasoning import observable_scenario
from strict_safety_policy import valid_signal
from src.triage_guard_cr01 import MIN_MEDICAL_QUALITY
from temporal_assurance import TemporalAssurance,EventResult


@dataclass(frozen=True)
class BehavioralReview:
    enabled: bool
    monitor: MonitorResult | None
    behavioral_evidence: str
    existing_observable_scenario: str
    safety: EventResult


class BehavioralReplay:
    def __init__(self,supervisor:TemporalAssurance,*,enabled=False,config:MonitorConfig|None=None,session_id='synthetic_session'):
        if type(enabled) is not bool:raise ValueError('explicit_boolean_flag_required')
        if enabled and config is None:raise ValueError('enabled_monitor_requires_configuration')
        self.supervisor=supervisor
        self.monitor=SequentialMonitor(config,session_id) if enabled else None
        self.config=config
        self.session_id=session_id

    def reset_monitor(self,request):
        """Reset only advisory evidence; never reset/rearm the safety supervisor."""
        if self.monitor is None:raise ValueError('monitor_disabled')
        result=self.monitor.reset(request)
        self.session_id=self.monitor.snapshot.session_id
        return result

    def step(self,observation):
        monitored=None
        if self.monitor is not None:
            s=observation.camera_motor_score;c=self.config
            # Preserve the original timestamp and source. Legacy freshness/quality
            # and boundedness are checked before the standardized score update.
            valid=valid_signal(s,observation.time_ms,MIN_MEDICAL_QUALITY)
            if s.at_ms!=observation.time_ms:
                monitored=self.monitor.tick(observation.time_ms)
            else:
                monitored=self.monitor.update(ScoreObservation(s.at_ms,self.session_id,s.source_id,s.value,
                    bool(valid),'legacy_synthetic_quality_valid' if valid else 'legacy_synthetic_quality_unavailable',
                    c.score_version,c.normalization_id,c.score_units))
        # CUSUM values never enter this call, including invalid/missing outputs.
        safety=self.supervisor.step(observation)
        behavior=('disabled' if monitored is None else 'unknown' if not monitored.available
            else 'suspected_behavioral_change_etiology_unresolved' if monitored.latched else 'below_threshold_not_health')
        return BehavioralReview(self.monitor is not None,monitored,behavior,observable_scenario(observation),safety)
