from dataclasses import dataclass
from typing import Any, Protocol

@dataclass(frozen=True)
class SourceHealth:
    source: str
    status: str
    checked_at: str
    detail: str | None = None

class Collector(Protocol):
    name: str
    def health(self) -> SourceHealth: ...
    def collect(self, **kwargs: Any) -> list[Any]: ...
