
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
import torch

_text_model = None
_vision_model = None
_vision_processor = None
_client = None

TEXT_DIM = 384  # all-MiniLM-L6-v2
VISION_DIM = 128  # ColQwen2


def get_text_model():
    global _text_model
    if _text_model is None:
        from sentence_transformers import SentenceTransformer
        _text_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _text_model


def get_vision_model():
    global _vision_model, _vision_processor
    if _vision_model is None:
        from colpali_engine.models import ColQwen2, ColQwen2Processor
        _vision_model = ColQwen2.from_pretrained(
            "vidore/colqwen2-v1.0",
            torch_dtype=torch.float32
        )
        _vision_model.eval()
        _vision_processor = ColQwen2Processor.from_pretrained("vidore/colqwen2-v1.0")
    return _vision_model, _vision_processor


def get_client():
    global _client
    if _client is None:
        _client = QdrantClient(path="./qdrant_db")
    return _client


def create_collections():
    client = get_client()

    # Text collection
    client.recreate_collection(
        "papers_text",
        vectors_config=VectorParams(size=TEXT_DIM, distance=Distance.COSINE)
    )
    print("Created 'papers_text' collection")

    # Visual collection
    client.recreate_collection(
        "papers_visual",
        vectors_config=VectorParams(size=VISION_DIM, distance=Distance.COSINE)
    )
    print("Created 'papers_visual' collection")


def embed_text(text: str) -> list[float]:
    model = get_text_model()
    return model.encode(text).tolist()


def embed_image(image) -> list[float]:
    """Embed image using ColQwen2."""
    model, processor = get_vision_model()
    inputs = processor.process_images([image])
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        embeddings = model(**inputs)
        embedding = embeddings[0].mean(dim=0).cpu().numpy()

    return embedding.tolist()


def store_text_chunks(chunks: list[dict]):
    client = get_client()
    model = get_text_model()

    points = []
    for i, chunk in enumerate(chunks):
        embedding = model.encode(chunk["text"]).tolist()
        point_id = abs(hash(f"{chunk['pdf']}_text_{chunk['page']}_{i}")) % (2**63)

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "pdf": chunk["pdf"],
                "page": chunk["page"],
                "text": chunk["text"],
                "type": "text"
            }
        ))

    if points:
        client.upsert("papers_text", points)
    print(f"  Stored {len(points)} text chunks")


def store_figures(figures: list[dict]):
    client = get_client()

    points = []
    for i, fig in enumerate(figures):
        embedding = embed_image(fig["image"])
        point_id = abs(hash(f"{fig['pdf']}_fig_{fig['page']}_{i}")) % (2**63)

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "pdf": fig["pdf"],
                "page": fig["page"],
                "type": "figure",
                "size": fig.get("size", (0, 0))
            }
        ))

    if points:
        client.upsert("papers_visual", points)
    print(f"  Stored {len(points)} figures")


def search_text(query: str, top_k: int = 3) -> list:
    client = get_client()
    q_emb = embed_text(query)

    results = client.query_points(
        collection_name="papers_text",
        query=q_emb,
        limit=top_k
    )
    return results.points


def search_figures(query: str, top_k: int = 3) -> list:
    client = get_client()
    model, processor = get_vision_model()

    # Embed query as text for vision model
    inputs = processor.process_queries([query])
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        embeddings = model(**inputs)
        q_emb = embeddings[0].mean(dim=0).cpu().numpy().tolist()

    results = client.query_points(
        collection_name="papers_visual",
        query=q_emb,
        limit=top_k
    )
    return results.points


def search_all(query: str, top_k: int = 3) -> dict:
    text_results = search_text(query, top_k)
    figure_results = search_figures(query, top_k)

    return {
        "text": text_results,
        "figures": figure_results
    }
