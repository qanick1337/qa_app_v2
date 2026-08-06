import json
from datetime import datetime, timezone


def log(event: str, ticket_id: int, **fields) -> None:
    print(json.dumps({
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "process": "qa_evaluation",
        "event": event,
        "ticket_id": ticket_id,
        **fields,
    }, default=str, ensure_ascii=False))