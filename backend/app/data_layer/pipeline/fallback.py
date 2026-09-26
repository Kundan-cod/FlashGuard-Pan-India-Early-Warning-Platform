from dataclasses import dataclass

@dataclass(frozen=True)
class FallbackDecision:
    selected_source: str | None
    status: str
    reason: str

def choose_fallback(candidates: list[tuple[str, str]]) -> FallbackDecision:
    # candidates are ordered by source priority; only usable statuses are selected.
    for source, status in candidates:
        if status in {"LIVE", "NRT", "REPLAY", "SIMULATED"}:
            return FallbackDecision(source, status, "highest-priority usable source")
    return FallbackDecision(None, "ERROR", "no usable source")
