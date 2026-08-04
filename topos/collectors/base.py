from abc import ABC, abstractmethod
from typing import Any


class Collector(ABC):
    @abstractmethod
    def collect(self) -> list[dict[str, Any]]:
        """Fetch raw filings/records from a data source."""
