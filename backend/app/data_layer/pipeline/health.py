from datetime import datetime, timezone
from .source import SourceHealth

def healthy(source: SourceHealth) -> bool:
    return source.status in {"LIVE", "NRT", "REPLAY", "SIMULATED"}

def make_health(source: str, status: str, detail: str | None = None) -> SourceHealth:
    return SourceHealth(
        source=source,
        status=status,
        checked_at=datetime.now(timezone.utc).isoformat(),
        detail=detail,
    )
