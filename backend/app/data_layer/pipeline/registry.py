from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class RegisteredSource:
    name: str
    enabled: bool
    priority: int
    collector_factory: Callable[..., Any] | None = None
    notes: str = ""

class SourceRegistry:
    def __init__(self):
        self._sources: dict[str, RegisteredSource] = {}

    def register(self, source: RegisteredSource) -> None:
        if source.name in self._sources:
            raise ValueError(f"duplicate source: {source.name}")
        self._sources[source.name] = source

    def get(self, name: str) -> RegisteredSource:
        return self._sources[name]

    def enabled(self) -> list[RegisteredSource]:
        return sorted(
            (s for s in self._sources.values() if s.enabled),
            key=lambda s: s.priority
        )

    def all(self) -> list[RegisteredSource]:
        return list(self._sources.values())
