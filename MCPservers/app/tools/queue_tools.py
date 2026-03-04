from app.contracts import QueuePopRequest, QueueAckResponse
from app.contracts import QueueAckRequest, QueueAckResponse
from app.adapters import queue_adapter

def queue_pop(req: QueuePopRequest):
    raw_payloads = queue_adapter.pop(
        req.queue,
        req.max_messages,
        req.visibility_timeout_s
    )

    messages = []
    for payload in raw_payloads:
        wrapped = queue_adapter.wrap_message(payload)
        messages.append(wrapped)

    return {"messages": messages}

def queue_ack(req: QueueAckRequest):
    from app.adapters import queue_adapter

    queue_adapter.ack(
        req.queue,
        req.receipt,
        req.status,
        req.result,
        req.error
    )
    return QueueAckResponse().model_dump()