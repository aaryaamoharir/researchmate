from typing import Literal
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class QueuePopRequest(BaseModel):
    queue: str
    max_messages: int = 1
    visibility_timeout_s: int = 120

class QueueJobPayload(BaseModel):
    job_type: str
    doc_id: str
    user_id: Optional[str] = None
    storage_url: str
    created_at: str
    options: Dict[str, Any] = Field(default_factory=dict)

class QueueMessage(BaseModel):
    job_id: str
    receipt: str
    payload: QueueJobPayload

class QueuePopResponse(BaseModel):
    messages: List[QueueMessage] = Field(default_factory=list)

class QueueAckRequest(BaseModel):
    queue: str
    receipt: str
    status: Literal["SUCCESS", "FAILED"]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class QueueAckResponse(BaseModel):
    ok: bool = True