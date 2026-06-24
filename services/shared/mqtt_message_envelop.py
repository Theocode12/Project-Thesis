from dataclasses import dataclass, asdict
from datetime import datetime, UTC


@dataclass(slots=True)
class MQTTMessageEnvelope:

    source: str

    timestamp: str

    payload: dict

    @classmethod
    def create(
        cls,
        source: str,
        payload: dict
    ) -> "MQTTMessageEnvelope":

        return cls(
            source=source,
            timestamp=datetime.now(
                UTC
            ).isoformat(),
            payload=payload
        )

    def to_dict(self) -> dict:
        return asdict(self)