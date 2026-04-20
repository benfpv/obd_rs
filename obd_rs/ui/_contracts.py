"""UI contracts: typed theme keys, panel protocol, and validation helpers.

These contracts make panel/theme requirements explicit so that:

  * The dashboard theme is verifiable against every panel at test time.
  * New panels declare their required theme keys, preventing silent
    `KeyError` crashes at runtime.
  * Static analyzers / IDEs can enforce the panel surface area.

Adoption is incremental: panels only need to expose ``required_theme_keys``
to participate in the contract. Existing draw/update signatures are
unchanged so this module is purely additive.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Protocol, Tuple, runtime_checkable


# ---------------------------------------------------------------------------
# Canonical theme keys
# ---------------------------------------------------------------------------
# A BGR colour tuple as expected by OpenCV (uint8 channels: 0–255).
ThemeColor = Tuple[int, int, int]

# A pixel-space rectangle (x, y, width, height) in OpenCV's top-left origin.
# Width/height are non-negative; (x, y) is the top-left corner.
Rect = Tuple[int, int, int, int]


# All theme keys recognised by the dashboard.  The dashboard is required to
# provide every key in this set; panels declare a subset they actually use.
THEME_KEYS: frozenset[str] = frozenset(
    {
        "bg_top",
        "bg_bottom",
        "grid",
        "panel_border",
        "panel_header",
        "text_primary",
        "text_dim",
        "diag",
        "inputs",
        "power",
        "issue",
        "possible",
        "system",
        "reserved",
        "ok_banner",
        "caution_banner",
        "critical_banner",
    }
)


# ---------------------------------------------------------------------------
# Panel protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class PanelContract(Protocol):
    """Structural contract that all dashboard panels are expected to satisfy.

    Panels keep their existing ``update(...)`` signatures (which legitimately
    differ – e.g. the system panel takes connection state, not telemetry).
    The contract focuses on the parts that *must* be uniform: a ``draw``
    method and a declaration of which theme keys the panel reads.
    """

    @classmethod
    def required_theme_keys(cls) -> frozenset[str]:  # pragma: no cover - protocol
        ...

    def draw(self, frame, rect, theme):  # pragma: no cover - protocol
        ...


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def validate_theme(theme: Mapping[str, ThemeColor], required: Iterable[str]) -> None:
    """Validate that *theme* contains every key in *required* with a valid
    BGR colour tuple.

    Raises:
        KeyError: when one or more required keys are missing.
        ValueError: when a key exists but holds an invalid colour value.
    """
    required_set = set(required)
    missing = sorted(required_set - set(theme.keys()))
    if missing:
        raise KeyError(f"Theme is missing required key(s): {missing}")

    invalid: list[str] = []
    for key in sorted(required_set):
        value = theme[key]
        if not _is_valid_color(value):
            invalid.append(f"{key}={value!r}")
    if invalid:
        raise ValueError(
            "Theme entries are not valid BGR colour tuples: " + ", ".join(invalid)
        )


def assert_panel_theme_compatible(
    theme: Mapping[str, ThemeColor], panel: type
) -> None:
    """Assert that *theme* satisfies *panel*'s declared theme requirements.

    Provides a clearer error than ``validate_theme`` by naming the panel.
    """
    required = getattr(panel, "required_theme_keys", None)
    if required is None or not callable(required):
        raise TypeError(
            f"Panel {panel.__name__!r} does not declare required_theme_keys()"
        )
    keys = required()
    try:
        validate_theme(theme, keys)
    except (KeyError, ValueError) as exc:  # re-raise with panel context
        raise type(exc)(f"{panel.__name__}: {exc}") from exc


def _is_valid_color(value: object) -> bool:
    if not isinstance(value, tuple) or len(value) != 3:
        return False
    for channel in value:
        if not isinstance(channel, int) or not (0 <= channel <= 255):
            return False
    return True
