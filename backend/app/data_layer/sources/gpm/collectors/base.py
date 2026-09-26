from abc import ABC, abstractmethod
from typing import Any

class CollectorError(RuntimeError):
    pass

class BaseCollector(ABC):
    @abstractmethod
    def fetch(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def validate(self, payload: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, payload: Any) -> list[Any]:
        raise NotImplementedError
