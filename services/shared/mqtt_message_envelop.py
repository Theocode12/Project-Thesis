import time
from dataclasses import dataclass, asdict


@dataclass(slots=True)
class MQTTMessageEnvelope:

    source: str

    timestamp: float

    payload: dict

    @classmethod
    def create(
        cls,
        source: str,
        payload: dict
    ) -> "MQTTMessageEnvelope":

        return cls(
            source=source,
            timestamp=time.time(),
            payload=payload
        )

    def to_dict(self) -> dict:
        return asdict(self)