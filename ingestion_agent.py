"""Ingestion agent orchestrator.

Calls teammate MCP tools in sequence:
  queue_pop -> pdf_extract_text -> chunk_document -> embed_texts -> vector_upsert -> queue_ack

Does NOT implement any MCP tool logic — only orchestration and error handling.
"""

from __future__ import annotations

import logging
import time

from agent_interfaces import MCPToolClient, OPTION_DEFAULTS, IngestionOutcome

logger = logging.getLogger(__name__)


def _fatal(code: str, message: str) -> IngestionOutcome:
    """Build a fatal outcome (no receipt available, cannot ack)."""
    return {
        "status": "fatal",
        "error": {"code": code, "message": message, "retryable": False},
    }


class IngestionAgent:
    """Orchestrates the ingestion pipeline via injected MCP tool client."""

    def __init__(self, client: MCPToolClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(
        self,
        queue: str = "ingestion",
        max_messages: int = 1,
        visibility_timeout_s: int = 120,
    ) -> IngestionOutcome:
        """Pop one job, ingest it, ack result. Returns structured outcome."""

        # 1. Pop from queue
        try:
            pop_resp = self._client.call("queue_pop", {
                "queue": queue,
                "max_messages": max_messages,
                "visibility_timeout_s": visibility_timeout_s,
            })
        except Exception as exc:
            logger.error("queue_pop call failed: %s", exc)
            return _fatal("QUEUE_POP_FAILED", str(exc))

        messages = pop_resp.get("messages", [])
        if not messages:
            return {"status": "idle"}

        msg = messages[0]

        # 2. Validate envelope (receipt is required to ack)
        receipt = msg.get("receipt")
        if not receipt:
            logger.error("Message missing receipt — cannot ack, fatal")
            return _fatal(
                "MISSING_RECEIPT",
                "Queue message has no receipt; cannot acknowledge",
            )

        # 3. Validate payload
        payload = msg.get("payload") or {}
        doc_id = payload.get("doc_id")
        storage_url = payload.get("storage_url")

        missing = []
        if not doc_id:
            missing.append("doc_id")
        if not storage_url:
            missing.append("storage_url")

        if missing:
            return self._fail(queue, receipt, doc_id, {
                "code": "VALIDATION_ERROR",
                "message": f"Missing required fields: {', '.join(missing)}",
                "retryable": False,
            })

        options = {**OPTION_DEFAULTS, **(payload.get("options") or {})}

        # 4. Extract text from PDF
        extract_result = self._call_tool(
            "pdf_extract_text",
            {"doc_id": doc_id, "storage_url": storage_url},
            required_key="pages",
        )
        if extract_result is None:
            return self._fail(queue, receipt, doc_id, self._last_error(
                "PDF_PARSE_FAILED", retryable=True,
            ))

        # 5. Chunk document
        chunk_result = self._call_tool(
            "chunk_document",
            {
                "doc_id": doc_id,
                "pages": extract_result["pages"],
                "chunk_config": {
                    "strategy": options["chunk_strategy"],
                    "max_chars": options["max_chars"],
                    "overlap_chars": options["overlap_chars"],
                },
            },
            required_key="chunks",
        )
        if chunk_result is None:
            return self._fail(queue, receipt, doc_id, self._last_error(
                "CHUNKING_FAILED", retryable=True,
            ))

        chunks = chunk_result["chunks"]

        # 6. Embed texts
        embed_result = self._call_tool(
            "embed_texts",
            {
                "model": options["embedding_model"],
                "inputs": [
                    {"id": c["chunk_id"], "text": c["text"]} for c in chunks
                ],
            },
            required_key="embeddings",
        )
        if embed_result is None:
            return self._fail(queue, receipt, doc_id, self._last_error(
                "EMBEDDING_FAILED", retryable=True,
            ))

        # 7. Validate chunk↔embedding ID alignment
        chunk_ids = {c["chunk_id"] for c in chunks}
        embed_ids = {e["id"] for e in embed_result["embeddings"]}
        if chunk_ids != embed_ids:
            extra = embed_ids - chunk_ids
            missing_ids = chunk_ids - embed_ids
            return self._fail(queue, receipt, doc_id, {
                "code": "EMBEDDING_ID_MISMATCH",
                "message": (
                    f"Chunk/embedding ID mismatch — "
                    f"missing from embeddings: {missing_ids}, "
                    f"extra in embeddings: {extra}"
                ),
                "retryable": False,
            })

        # 8. Build vectors and upsert
        embed_map = {e["id"]: e["vector"] for e in embed_result["embeddings"]}
        vectors = [
            {
                "id": c["chunk_id"],
                "vector": embed_map[c["chunk_id"]],
                "metadata": {
                    "doc_id": doc_id,
                    "chunk_id": c["chunk_id"],
                    "page_start": c["page_start"],
                    "page_end": c["page_end"],
                    "offset_start": c.get("offset_start", 0),
                    "offset_end": c.get("offset_end", 0),
                    "section_title": c.get("section_title"),
                },
            }
            for c in chunks
        ]

        upsert_result = self._call_tool(
            "vector_upsert",
            {"namespace": doc_id, "vectors": vectors},
        )
        if upsert_result is None:
            return self._fail(queue, receipt, doc_id, self._last_error(
                "VECTOR_UPSERT_FAILED", retryable=True,
            ))

        # 9. Optional summary (best-effort, failure does not fail ingestion)
        if options.get("make_summary"):
            try:
                from summarizer import summarize_paper
                summarize_paper(storage_url)
                logger.info("Summary generated for doc_id=%s", doc_id)
            except Exception as exc:
                logger.warning(
                    "Summary failed for doc_id=%s (non-fatal): %s", doc_id, exc,
                )

        # 10. Ack success
        chunk_count = len(chunks)
        self._ack(queue, receipt, "SUCCESS", result={
            "doc_id": doc_id,
            "chunk_count": chunk_count,
        })

        return {"status": "success", "doc_id": doc_id, "chunk_count": chunk_count}

    def run_loop(
        self,
        queue: str = "ingestion",
        poll_interval_s: int = 2,
        visibility_timeout_s: int = 120,
        max_iterations: int | None = None,
    ) -> None:
        """Poll the queue repeatedly until interrupted or max_iterations reached."""
        logger.info(
            "Ingestion worker started (queue=%s, poll=%ds)", queue, poll_interval_s,
        )
        iterations = 0

        try:
            while max_iterations is None or iterations < max_iterations:
                outcome = self.run_once(
                    queue=queue,
                    visibility_timeout_s=visibility_timeout_s,
                )
                iterations += 1
                status = outcome.get("status", "unknown")

                if status == "idle":
                    logger.debug("Queue empty, sleeping %ds", poll_interval_s)
                    time.sleep(poll_interval_s)
                elif status == "success":
                    logger.info(
                        "Ingested doc_id=%s chunks=%d",
                        outcome.get("doc_id"),
                        outcome.get("chunk_count"),
                    )
                elif status == "failed":
                    logger.warning(
                        "Ingestion failed doc_id=%s error=%s",
                        outcome.get("doc_id"),
                        outcome.get("error"),
                    )
                elif status == "fatal":
                    logger.error("Fatal: %s — sleeping before retry", outcome.get("error"))
                    time.sleep(poll_interval_s)
        except KeyboardInterrupt:
            logger.info("Ingestion worker stopped by user")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    _last_exc: Exception | None = None

    def _call_tool(
        self,
        tool_name: str,
        payload: dict,
        required_key: str | None = None,
    ) -> dict | None:
        """Call an MCP tool. Returns the response dict, or None on failure.

        Stores the exception in self._last_exc for the caller to wrap into
        an error payload via _last_error().
        """
        try:
            result = self._client.call(tool_name, payload)
            if required_key and required_key not in result:
                raise ValueError(
                    f"{tool_name} response missing required key '{required_key}'"
                )
            self._last_exc = None
            return result
        except Exception as exc:
            self._last_exc = exc
            logger.error("%s failed: %s", tool_name, exc)
            return None

    def _last_error(self, code: str, retryable: bool) -> dict:
        """Build a QueueAckError dict from the most recent _call_tool failure."""
        return {
            "code": code,
            "message": str(self._last_exc) if self._last_exc else "unknown error",
            "retryable": retryable,
        }

    def _fail(
        self, queue: str, receipt: str, doc_id: str | None, error: dict,
    ) -> IngestionOutcome:
        """Ack failure and return a failed outcome."""
        self._ack(queue, receipt, "FAILED", error=error)
        return {"status": "failed", "doc_id": doc_id, "error": error}

    def _ack(
        self,
        queue: str,
        receipt: str,
        status: str,
        result: dict | None = None,
        error: dict | None = None,
    ) -> None:
        """Send queue_ack. Failures are logged, never raised."""
        ack_payload: dict = {
            "queue": queue,
            "receipt": receipt,
            "status": status,
        }
        if result is not None:
            ack_payload["result"] = result
        if error is not None:
            ack_payload["error"] = error

        try:
            self._client.call("queue_ack", ack_payload)
        except Exception as exc:
            logger.error(
                "queue_ack failed (receipt=%s, status=%s): %s",
                receipt, status, exc,
            )
