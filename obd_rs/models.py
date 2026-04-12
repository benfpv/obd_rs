from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    CRITICAL = "critical"


@dataclass
class Signal:
    value: Optional[float] = None
    unit: str = ""
    timestamp: float = 0.0
    supported: bool = True
    stale: bool = True
    confidence: float = 0.0


@dataclass
class TelemetryState:
    rpm: Signal = field(default_factory=lambda: Signal(unit="rpm"))
    speed: Signal = field(default_factory=lambda: Signal(unit="km/h"))
    throttle: Signal = field(default_factory=lambda: Signal(unit="%"))
    engine_load: Signal = field(default_factory=lambda: Signal(unit="%"))
    coolant_temp: Signal = field(default_factory=lambda: Signal(unit="C"))
    intake_temp: Signal = field(default_factory=lambda: Signal(unit="C"))
    stft_b1: Signal = field(default_factory=lambda: Signal(unit="%"))
    ltft_b1: Signal = field(default_factory=lambda: Signal(unit="%"))
    spark_advance: Signal = field(default_factory=lambda: Signal(unit="deg"))
    module_voltage: Signal = field(default_factory=lambda: Signal(unit="V"))
    maf_gps: Signal = field(default_factory=lambda: Signal(unit="g/s", supported=False))
    map_kpa: Signal = field(default_factory=lambda: Signal(unit="kPa", supported=False))
    oil_temp: Signal = field(default_factory=lambda: Signal(unit="C", supported=False))


@dataclass
class AlertEvent:
    key: str
    title: str
    detail: str
    severity: Severity
    source: str
    active: bool = True
    first_seen: float = 0.0
    last_seen: float = 0.0
