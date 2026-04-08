from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
import os
from dotenv import load_dotenv
from colpali_engine.models import ColQwen2
from PIL import Image
import torch
from supabase import Client, create_client

load_dotenv()  

# Replace with your actual URL and API key (consider environment variables)
QDRANT_URL = os.getenv('QDRANT_URL')
QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')

class QdrantHandler:

    def __init__(self) -> None:
        self.client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )


    def create_collection(self, user_id, vector_size=128, distance_metric=Distance.COSINE):

        collection_name = f"user_{user_id}"

        if self.client.collection_exists(collection_name=collection_name):
            return collection_name

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=distance_metric,
            )
        )
        return collection_name

    def create_point(self, user_id, vector, pdf_id, page_num, supabase_client):

        collection_name = self.create_collection(user_id) # will make a new collection or return the existing one for the given user

        point_id = f'{pdf_id}_{page_num}'

        self.client.upsert(
            collection_name=collection_name,
            points=[
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "pdf_id": pdf_id,
                        "summary": supabase_client.table("pdf_pages").select("summary").eq("pdf_id", pdf_id).eq("page_number", page_num).execute().data[0]['summary'],
                        "tags": {},  # Add tags here
                    }
                }
            ]
        )

