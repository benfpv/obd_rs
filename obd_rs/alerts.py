import time

from .config import COOLANT_CAUTION_C, CRITICAL_DTC_PREFIXES, LTFT_ALERT_PCT, STFT_ALERT_PCT
from .models import AlertEvent, Severity, TelemetryState


class AlertEngine:
    """Separates confirmed issues and possible issues for distinct UI sections."""

    def __init__(self) -> None:
        self._issues: dict[str, AlertEvent] = {}
        self._possible: dict[str, AlertEvent] = {}

    def _upsert(self, store: dict[str, AlertEvent], prev: dict[str, AlertEvent], event: AlertEvent) -> None:
        """Insert or update an alert, preserving *first_seen* from the previous tick."""
        prev_event = prev.get(event.key)
        if prev_event is not None:
            event.first_seen = prev_event.first_seen
        store[event.key] = event

    def update_from_state(self, state: TelemetryState, active_dtcs: list[str], pending_dtcs: list[str]) -> None:
        now = time.monotonic()
        prev_issues = self._issues
        prev_possible = self._possible
        self._issues = {}
        self._possible = {}

        for code in active_dtcs:
            self._upsert(self._issues, prev_issues, AlertEvent(
                key=f"dtc:{code}",
                title=f"Active DTC {code}",
                detail="confirmed fault",
                severity=Severity.CRITICAL if any(code.startswith(p) for p in CRITICAL_DTC_PREFIXES) else Severity.CAUTION,
                source="dtc_active",
                first_seen=now,
                last_seen=now,
            ))

        for code in pending_dtcs:
            self._upsert(self._possible, prev_possible, AlertEvent(
                key=f"pending:{code}",
                title=f"Pending DTC {code}",
                detail="possible emerging issue",
                severity=Severity.CAUTION,
                source="dtc_pending",
                first_seen=now,
                last_seen=now,
            ))

        coolant = state.coolant_temp.value
        if coolant is not None and not state.coolant_temp.stale and coolant > COOLANT_CAUTION_C:
            self._upsert(self._possible, prev_possible, AlertEvent(
                key="thermal",
                title="Coolant trend high",
                detail=f"coolant at {coolant:.1f} C",
                severity=Severity.CAUTION,
                source="heuristic",
                first_seen=now,
                last_seen=now,
            ))

        stft = state.stft_b1.value
        ltft = state.ltft_b1.value
        if stft is not None and not state.stft_b1.stale and abs(stft) > STFT_ALERT_PCT:
            self._upsert(self._possible, prev_possible, AlertEvent(
                key="stft",
                title="Fuel trim oscillation",
                detail=f"stft bank1 {stft:.1f}%",
                severity=Severity.CAUTION,
                source="heuristic",
                first_seen=now,
                last_seen=now,
            ))
        if ltft is not None and not state.ltft_b1.stale and abs(ltft) > LTFT_ALERT_PCT:
            self._upsert(self._possible, prev_possible, AlertEvent(
                key="ltft",
                title="Long-term trim drift",
                detail=f"ltft bank1 {ltft:.1f}%",
                severity=Severity.CAUTION,
                source="heuristic",
                first_seen=now,
                last_seen=now,
            ))

    def issues(self) -> list[AlertEvent]:
        return list(self._issues.values())

    def possible_issues(self) -> list[AlertEvent]:
        return list(self._possible.values())
