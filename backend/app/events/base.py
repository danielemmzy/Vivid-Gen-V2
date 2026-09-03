from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime

    @classmethod
    def now(cls, **kwargs):
        return cls(occurred_at=datetime.now(timezone.utc), **kwargs)
