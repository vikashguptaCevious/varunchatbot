import os
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv
from pathlib import Path

# Load .env from backend/ or current dir
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

class VectorDB:
    def __init__(self):
        api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "mini-rag-index")
        self.pc = Pinecone(api_key=api_key)
        self.index = None

    def connect(self):
        if self.index_name not in self.pc.list_indexes().names():
            # 768 dimensions for models/gemini-embedding-001 (output_dimensionality=768)
            self.pc.create_index(
                name=self.index_name,
                dimension=768,
                metric='cosine',
                spec=ServerlessSpec(
                    cloud='aws',
                    region='us-east-1' # Default for free tier
                )
            )
        self.index = self.pc.Index(self.index_name)
        print(f"Connected to Pinecone index: {self.index_name}")

    def upsert_vectors(self, vectors):
        return self.index.upsert(vectors=vectors)

    def query_vectors(self, query_vector, top_k=10, include_metadata=True):
        return self.index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=include_metadata
        )

vector_db = VectorDB()
