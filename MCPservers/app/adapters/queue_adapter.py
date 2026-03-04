import uuid
import time
from typing import Dict, List, Any

_QUEUE: Dict[str, Dict[str, Any]] = {}


def _get_queue(queue: str):
    if queue not in _QUEUE:
        _QUEUE[queue] = {
            "available": [],
            "in_flight": {}
        }
    return _QUEUE[queue]


def seed(queue: str, payload: Dict[str, Any]) -> None:
    """Add a job to queue (for testing)."""
    q = _get_queue(queue)
    q["available"].append(payload)


def pop(queue: str, max_messages: int, visibility_timeout_s: int) -> List[Dict[str, Any]]:
    """
    Lease messages from queue.
    """
    q = _get_queue(queue)
    messages = []

    # First, re-queue expired in-flight jobs
    now = time.time()
    expired = []
    for receipt, data in q["in_flight"].items():
        if data["expires_at"] <= now:
            expired.append(receipt)

    for receipt in expired:
        q["available"].append(q["in_flight"][receipt]["payload"])
        del q["in_flight"][receipt]

    # Lease new messages
    for _ in range(min(max_messages, len(q["available"]))):
        payload = q["available"].pop(0)

        receipt = f"r_{uuid.uuid4().hex}"
        expires_at = time.time() + visibility_timeout_s

        q["in_flight"][receipt] = {
            "payload": payload,
            "expires_at": expires_at
        }

        messages.append({
            "job_id": f"job_{uuid.uuid4().hex[:8]}",
            "receipt": receipt,
            "payload": payload
        })

    return messages


def ack(queue: str, receipt: str, status: str, result=None, error=None) -> None:
    """
    Acknowledge a message permanently.
    Removes it from in-flight messages.
    """
    q = _get_queue(queue)

    if receipt not in q["in_flight"]:
        raise ValueError(f"Invalid or expired receipt: {receipt}")

    # In real queue:
    # - If FAILED → maybe requeue or send to DLQ
    # - If SUCCESS → delete permanently

    if status == "FAILED":
        # Optional behavior: requeue failed jobs
        q["available"].append(q["in_flight"][receipt]["payload"])

    # Remove from in-flight (final delete)
    del q["in_flight"][receipt]