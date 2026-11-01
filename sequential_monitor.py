"""One-sided standardized-score CUSUM and same-input fixed-threshold monitor.

No camera extraction, medical diagnosis, vehicle authority or network I/O.
See docs/CUSUM_DESIGN.md for the explicit uncalibrated lifecycle and gap policy.
"""
from dataclasses import asdict,dataclass,replace
import hashlib
import json
import math


def finite_number(x):
    try:return type(x) in (int,float) and math.isfinite(x)
    except OverflowError:return False


def nonempty(x):
    return isinstance(x,str) and bool(x.strip())


@dataclass(frozen=True)
class MonitorConfig:
    mu0: float
    sigma0: float
    k: float
    h: float
    fixed_threshold: float
    gap_timeout_ms: int
    source_id: str
    score_version: str
    normalization_id: str
    score_units: str
    config_version: str
    parameter_provenance: str

    def __post_init__(self):
        if not all(finite_number(x) for x in (self.mu0,self.sigma0,self.k,self.h,self.fixed_threshold)):
            raise ValueError('nonfinite_or_nonnumeric_configuration')
        if self.sigma0<=0 or self.k<0 or self.h<=0:
            raise ValueError('sigma_positive_k_nonnegative_h_positive_required')
        if type(self.gap_timeout_ms) is not int or self.gap_timeout_ms<=0:
            raise ValueError('positive_integer_gap_timeout_required')
        if not all(nonempty(getattr(self,k)) for k in ('source_id','score_version','normalization_id','score_units','config_version','parameter_provenance')):
            raise ValueError('configuration_identifiers_required')

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self),sort_keys=True,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ScoreObservation:
    at_ms: int
    session_id: str
    source_id: str
    score: float | None
    valid: bool
    quality_reason: str
    score_version: str
    normalization_id: str
    score_units: str


@dataclass(frozen=True)
class ResetRequest:
    at_ms: int
    session_id: str
    reason: str


@dataclass(frozen=True)
class MonitorState:
    session_id: str
    statistic: float = 0.
    last_seen_ms: int | None = None
    last_valid_ms: int | None = None
    started_ms: int | None = None
    latched: bool = False
    needs_reset: bool = False


@dataclass(frozen=True)
class MonitorResult:
    method: str
    at_ms: int | None
    session_id: str
    source_id: str
    score: float | None
    input_valid: bool | None
    available: bool
    quality_reason: str
    score_version: str
    normalization_id: str
    score_units: str
    z: float | None
    statistic: float
    k: float
    threshold: float
    crossing: bool
    state: str
    latched: bool
    needs_reset: bool
    reason: str
    config_version: str
    config_sha256: str
    input_metadata: dict | None


class SequentialMonitor:
    def __init__(self,config:MonitorConfig,session_id:str,method='cusum'):
        if not isinstance(config,MonitorConfig) or not nonempty(session_id) or method not in ('cusum','fixed'):
            raise ValueError('invalid_monitor_setup')
        config.__post_init__()
        self._config=config
        self._config_digest=config.digest
        self._method=method
        self._state=MonitorState(session_id)

    @property
    def snapshot(self):return self._state

    def _healthy(self):
        s=self._state
        if not isinstance(s,MonitorState) or not nonempty(s.session_id):return False
        times=(s.last_seen_ms,s.last_valid_ms,s.started_ms)
        return (finite_number(s.statistic) and s.statistic>=0
                and type(s.latched) is bool and type(s.needs_reset) is bool
                and all(x is None or type(x) is int and x>=0 for x in times)
                and (s.last_seen_ms is not None or s.last_valid_ms is None and s.started_ms is None)
                and (s.last_seen_ms is None or s.started_ms is not None)
                and (s.statistic==0 or s.last_valid_ms is not None)
                and (s.last_valid_ms is None or s.last_seen_ms is not None and s.last_valid_ms<=s.last_seen_ms)
                and (s.last_valid_ms is None or s.started_ms is not None and s.last_valid_ms>=s.started_ms)
                and (s.started_ms is None or s.last_seen_ms is not None and s.started_ms<=s.last_seen_ms))

    def _result(self,obs=None,available=False,z=None,crossing=False,reason='unavailable'):
        s=self._state;c=self._config
        state=('SUSPECTED_BEHAVIORAL_CHANGE' if crossing else 'VERIFICATION_PENDING' if s.latched else 'MONITORING') if available else 'UNKNOWN'
        isobs=isinstance(obs,ScoreObservation)
        return MonitorResult(self._method,obs.at_ms if isobs and type(obs.at_ms) is int else s.last_seen_ms,
            s.session_id,c.source_id,obs.score if isobs and finite_number(obs.score) else None,
            obs.valid if isobs and type(obs.valid) is bool else None,available,
            obs.quality_reason if isobs and isinstance(obs.quality_reason,str) else reason,
            c.score_version,c.normalization_id,c.score_units,z,s.statistic,c.k,
            c.h if self._method=='cusum' else c.fixed_threshold,crossing,state,s.latched,
            s.needs_reset,reason,c.config_version,self._config_digest,
            {key:getattr(obs,key) if isinstance(getattr(obs,key),str) else None for key in
             ('session_id','source_id','score_version','normalization_id','score_units')} if isobs else None)

    def _check_state(self):
        if self._healthy():return True
        # A corrupt state cannot silently become healthy or emit an event.
        sid=getattr(self._state,'session_id','corrupted_session')
        self._state=MonitorState(sid if nonempty(sid) else 'corrupted_session',needs_reset=True)
        return False

    def _advance(self,at_ms):
        s=self._state
        self._state=replace(s,last_seen_ms=at_ms,started_ms=s.started_ms if s.started_ms is not None else at_ms)
        anchor=s.last_valid_ms if s.last_valid_ms is not None else self._state.started_ms
        if at_ms-anchor>self._config.gap_timeout_ms:
            self._state=replace(self._state,statistic=0.,needs_reset=True)

    def update(self,obs):
        if not self._check_state():return self._result(reason='corrupted_state')
        if not isinstance(obs,ScoreObservation):return self._result(reason='malformed_observation')
        s=self._state;c=self._config
        if type(obs.at_ms) is not int or obs.at_ms<0:return self._result(obs,reason='invalid_timestamp')
        if s.last_seen_ms is not None and obs.at_ms<=s.last_seen_ms:return self._result(obs,reason='non_monotonic_timestamp')
        if obs.session_id!=s.session_id:return self._result(obs,reason='session_mismatch')
        self._advance(obs.at_ms)
        if self._state.needs_reset:return self._result(obs,reason='recovery_reset_required')
        if (obs.source_id!=c.source_id or obs.score_version!=c.score_version or
            obs.normalization_id!=c.normalization_id or obs.score_units!=c.score_units):
            return self._result(obs,reason='score_metadata_mismatch')
        if type(obs.valid) is not bool or not nonempty(obs.quality_reason):return self._result(obs,reason='invalid_quality_metadata')
        if not obs.valid:return self._result(obs,reason='quality_unavailable')
        if not finite_number(obs.score):return self._result(obs,reason='invalid_score')
        try:
            z=(obs.score-c.mu0)/c.sigma0
            value=self._state.statistic+z-c.k if self._method=='cusum' else z
            if not math.isfinite(z) or not math.isfinite(value):raise ArithmeticError
        except (ArithmeticError,OverflowError):
            self._state=replace(self._state,statistic=0.,needs_reset=True)
            return self._result(obs,reason='numeric_overflow')
        statistic=max(0.,value) if self._method=='cusum' else 0.
        crossed=(statistic>=c.h if self._method=='cusum' else z>=c.fixed_threshold)
        crossing=bool(crossed and not self._state.latched)
        self._state=replace(self._state,statistic=statistic,last_valid_ms=obs.at_ms,latched=self._state.latched or crossing)
        return self._result(obs,True,float(z),crossing,'threshold_crossing' if crossing else 'latched_no_repeat' if self._state.latched else 'below_threshold')

    def tick(self,at_ms):
        """Caller-provided clock tick for a stream that has stopped emitting."""
        if not self._check_state():return self._result(reason='corrupted_state')
        if type(at_ms) is not int or at_ms<0 or self._state.last_seen_ms is not None and at_ms<=self._state.last_seen_ms:
            return self._result(reason='invalid_tick_timestamp')
        self._advance(at_ms)
        return self._result(reason='recovery_reset_required' if self._state.needs_reset else 'no_observation')

    def reset(self,request):
        """Trusted local orchestration only. No OEM ACK triggers this implicitly."""
        if not isinstance(request,ResetRequest) or type(request.at_ms) is not int or request.at_ms<0 or not nonempty(request.session_id):
            raise ValueError('invalid_reset_request')
        if request.reason not in ('operator_review','sensor_recovery','new_session'):raise ValueError('invalid_reset_reason')
        if not self._healthy():raise ValueError('process_corrupted_state_before_reset')
        s=self._state
        if request.reason=='new_session':
            if request.session_id==s.session_id:raise ValueError('new_session_id_required')
        else:
            if request.session_id!=s.session_id or s.last_seen_ms is not None and request.at_ms<s.last_seen_ms:raise ValueError('invalid_reset_session_or_time')
            if request.reason=='sensor_recovery' and not s.needs_reset:raise ValueError('no_degradation_to_recover')
        self._state=MonitorState(request.session_id,last_seen_ms=request.at_ms,started_ms=request.at_ms)
        return self._result(reason='explicit_'+request.reason+'_reset')
