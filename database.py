import io
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from dotenv import load_dotenv
from pypdf import PdfReader
from qdrant_client import QdrantClient, models
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PointStruct,
    VectorParams,
)
from supabase import Client, create_client

load_dotenv()

COLQWEN_VECTOR_NAME = "colqwen"


@dataclass
class PDFVectorPoint:
    point_id: str
    colqwen_multivector: list[list[float]]
    payload: dict[str, Any]


class ResearchVectorDB:
    def __init__(
        self,
        *,
        qdrant_collection: Optional[str] = None,
        colqwen_dim: Optional[int] = None,
    ) -> None:
        self.supabase: Client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )

        self.qdrant = QdrantClient(
            url=os.environ["QDRANT_URL"],
            api_key=os.getenv("QDRANT_API_KEY"),
        )

        self.collection_name = qdrant_collection or os.getenv(
            "QDRANT_COLLECTION", "research_paper_pages"
        )
        self.colqwen_dim = colqwen_dim or self._resolve_colqwen_dim()
        self.pdf_bucket = os.getenv("SUPABASE_PDF_BUCKET", "pdfs")

    @staticmethod
    def _resolve_colqwen_dim() -> Optional[int]:
        env_dim = os.getenv("COLQWEN_EMBEDDING_DIM") or os.getenv("EMBEDDING_DIM")
        if not env_dim:
            return None
        return int(env_dim)

    def _ensure_collection(self, inferred_dim: Optional[int] = None) -> None:
        if self.qdrant.collection_exists(self.collection_name):
            return

        vector_size = self.colqwen_dim or inferred_dim
        if not vector_size:
            raise ValueError(
                "ColQwen vector size is unknown. Set COLQWEN_EMBEDDING_DIM in .env "
                "or ingest with non-empty embeddings so the size can be inferred."
            )

        self.qdrant.create_collection(
            collection_name=self.collection_name,
            vectors_config={
                COLQWEN_VECTOR_NAME: VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM
                    ),
                )
            },
        )

        # Enables efficient keyword/full-text filtering over summaries.
        self.qdrant.create_payload_index(
            collection_name=self.collection_name,
            field_name="text_summary",
            field_schema=models.TextIndexParams(type="text"),
        )

    def get_pdf_row(self, pdf_id: int) -> dict[str, Any]:
        result = (
            self.supabase.table("pdfs")
            .select("id,user_id,file_name,storage_path,created_at")
            .eq("id", pdf_id)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError(f"pdfs.id={pdf_id} was not found in Supabase.")
        return result.data

    def download_pdf_bytes(self, storage_path: str) -> bytes:
        pdf_bytes = self.supabase.storage.from_(self.pdf_bucket).download(storage_path)
        if not pdf_bytes:
            raise ValueError(
                f"Could not download PDF from {self.pdf_bucket}/{storage_path}."
            )
        return pdf_bytes

    @staticmethod
    def extract_pages(pdf_bytes: bytes) -> list[str]:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                text = f"[No extractable text found on page {index}]"
            pages.append(text)
        return pages

    @staticmethod
    def _make_point_id(pdf_id: int, page_number: int) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"pdf:{pdf_id}:page:{page_number}"))

    @staticmethod
    def _default_page_summary(page_text: str, max_chars: int = 700) -> str:
        compact = " ".join(page_text.split())
        return compact[:max_chars]

    @staticmethod
    def _validate_multivector(multivector: list[list[float]], expected_dim: Optional[int]) -> int:
        if not multivector:
            raise ValueError("Each page must contain at least one ColQwen vector.")
        first_dim = len(multivector[0])
        if first_dim == 0:
            raise ValueError("ColQwen vectors cannot be empty.")
        for token_vec in multivector:
            if len(token_vec) != first_dim:
                raise ValueError("All vectors in one page multivector must share the same dim.")
        if expected_dim is not None and first_dim != expected_dim:
            raise ValueError(
                f"ColQwen dimension mismatch: got {first_dim}, expected {expected_dim}."
            )
        return first_dim

    def build_colqwen_points(
        self,
        *,
        pdf_row: dict[str, Any],
        page_multivectors: list[list[list[float]]],
        page_texts: list[str],
        page_summaries: Optional[list[str]] = None,
    ) -> list[PDFVectorPoint]:
        if len(page_multivectors) != len(page_texts):
            raise ValueError("page_multivectors and page_texts must have equal length.")
        if page_summaries is not None and len(page_summaries) != len(page_multivectors):
            raise ValueError("page_summaries must match number of pages.")

        points: list[PDFVectorPoint] = []
        for i, (page_mv, page_text) in enumerate(zip(page_multivectors, page_texts), start=1):
            self._validate_multivector(page_mv, self.colqwen_dim)
            summary = (
                page_summaries[i - 1]
                if page_summaries is not None
                else self._default_page_summary(page_text)
            )

            payload = {
                "pdf_id": pdf_row["id"],
                "user_id": str(pdf_row["user_id"]),
                "file_name": pdf_row["file_name"],
                "storage_path": pdf_row["storage_path"],
                "page_number": i,
                "text": page_text,
                "text_summary": summary,
                "pdf_created_at": pdf_row.get("created_at"),
            }
            points.append(
                PDFVectorPoint(
                    point_id=self._make_point_id(pdf_row["id"], i),
                    colqwen_multivector=page_mv,
                    payload=payload,
                )
            )
        return points

    def upsert_colqwen_points(self, points: list[PDFVectorPoint]) -> None:
        qdrant_points = [
            PointStruct(
                id=p.point_id,
                vector={COLQWEN_VECTOR_NAME: p.colqwen_multivector},
                payload=p.payload,
            )
            for p in points
        ]
        self.qdrant.upsert(collection_name=self.collection_name, points=qdrant_points)

    def ingest_pdf_colqwen_by_id(
        self,
        pdf_id: int,
        *,
        page_multivectors: list[list[list[float]]],
        page_summaries: Optional[list[str]] = None,
        user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        pdf_row = self.get_pdf_row(pdf_id)
        if user_id and str(pdf_row["user_id"]) != str(user_id):
            raise PermissionError("This PDF does not belong to the provided user_id.")

        if not page_multivectors:
            raise ValueError("page_multivectors cannot be empty.")

        inferred_dim = self._validate_multivector(page_multivectors[0], self.colqwen_dim)
        self._ensure_collection(inferred_dim=inferred_dim)

        pdf_bytes = self.download_pdf_bytes(pdf_row["storage_path"])
        page_texts = self.extract_pages(pdf_bytes)

        points = self.build_colqwen_points(
            pdf_row=pdf_row,
            page_multivectors=page_multivectors,
            page_texts=page_texts,
            page_summaries=page_summaries,
        )
        self.upsert_colqwen_points(points)

        return {
            "pdf_id": pdf_id,
            "user_id": str(pdf_row["user_id"]),
            "file_name": pdf_row["file_name"],
            "page_count": len(points),
            "collection": self.collection_name,
            "vector_name": COLQWEN_VECTOR_NAME,
        }

    @staticmethod
    def _build_filter(
        *,
        pdf_id: Optional[int],
        user_id: Optional[str],
        summary_keywords: Optional[str] = None,
    ) -> Optional[Filter]:
        conditions = []
        if pdf_id is not None:
            conditions.append(FieldCondition(key="pdf_id", match=MatchValue(value=pdf_id)))
        if user_id is not None:
            conditions.append(
                FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))
            )
        if summary_keywords:
            conditions.append(
                FieldCondition(
                    key="text_summary",
                    match=MatchText(text=summary_keywords),
                )
            )

        if not conditions:
            return None
        return Filter(must=conditions)

    def search_colqwen_pages(
        self,
        *,
        query_multivector: list[list[float]],
        top_k: int = 5,
        pdf_id: Optional[int] = None,
        user_id: Optional[str] = None,
        summary_keywords: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        self._validate_multivector(query_multivector, self.colqwen_dim)

        query_filter = self._build_filter(
            pdf_id=pdf_id,
            user_id=user_id,
            summary_keywords=summary_keywords,
        )
        response = self.qdrant.query_points(
            collection_name=self.collection_name,
            query=query_multivector,
            using=COLQWEN_VECTOR_NAME,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )

        output: list[dict[str, Any]] = []
        for match in response.points:
            payload = match.payload or {}
            output.append(
                {
                    "score": match.score,
                    "pdf_id": payload.get("pdf_id"),
                    "page_number": payload.get("page_number"),
                    "file_name": payload.get("file_name"),
                    "text_summary": payload.get("text_summary"),
                    "text": payload.get("text"),
                }
            )
        return output

    def save_summary(self, *, pdf_id: int, summary: str) -> dict[str, Any]:
        result = (
            self.supabase.table("summaries")
            .insert(
                {
                    "pdf_id": pdf_id,
                    "summary": summary,
                }
            )
            .execute()
        )
        if not result.data:
            raise RuntimeError("Could not insert summary row.")
        return result.data[0]


if __name__ == "__main__":
    # This module now expects ColQwen embeddings to be computed by your model code,
    # then passed into ingest_pdf_colqwen_by_id(...).
    print("ResearchVectorDB ready for ColQwen multivector ingestion.")
