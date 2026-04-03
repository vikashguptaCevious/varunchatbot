import os
import re
import time
import random
import google.generativeai as genai
import cohere
from dotenv import load_dotenv
from pathlib import Path

# Load .env from backend/ or current dir
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class AIService:
    """
    AIService handles communication with Google Gemini and Cohere.
    This version uses stable model names and standard SDK methods
    to ensure compatibility across all account types (Free/Tiered).
    """
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment")
        
        # Configure the Google AI SDK
        genai.configure(api_key=self.api_key)
        
        # Generation: flash model. Embeddings: gemini-embedding-001 (v1beta); text-embedding-004 is not available there.
        self.generation_model_name = 'gemini-2.5-flash'
        self.embedding_model_name = 'models/gemini-embedding-001'
        self.embedding_dimensions = 768  # Must match Pinecone index + stored FAQ vectors

        self.llm = genai.GenerativeModel(model_name=self.generation_model_name)
        
        # Cohere Reranker Configuration
        self.co_key = os.getenv("COHERE_API_KEY")
        if self.co_key:
            self.co = cohere.Client(self.co_key)
        else:
            self.co = None

    def _embed(self, text: str, task_type: str):
        """Single path for document vs query embeddings; 768-dim to match vector index."""
        max_retries = 6
        for attempt in range(max_retries):
            try:
                result = genai.embed_content(
                    model=self.embedding_model_name,
                    content=text,
                    task_type=task_type,
                    output_dimensionality=self.embedding_dimensions,
                )
                return result["embedding"]
            except Exception as e:
                err_s = str(e).lower()
                is_ratelimit = (
                    "429" in str(e)
                    or "quota" in err_s
                    or ("rate" in err_s and "limit" in err_s)
                    or "resource_exhausted" in err_s
                )
                if not is_ratelimit or attempt == max_retries - 1:
                    raise
                wait = min(120.0, (2**attempt) * 2 + random.uniform(0, 1.5))
                m = re.search(
                    r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*s",
                    str(e),
                    re.I,
                )
                if m:
                    wait = float(m.group(1)) + 1.0
                print(
                    f"Embedding rate limited, waiting {wait:.1f}s "
                    f"(retry {attempt + 1}/{max_retries})..."
                )
                time.sleep(wait)
        raise RuntimeError("embedding retries exhausted")  # pragma: no cover

    def get_embeddings(self, text: str):
        """Embedding for chunks / FAQ documents (retrieval index)."""
        return self._embed(text, "retrieval_document")

    def get_query_embedding(self, query: str):
        """Embedding for user search queries."""
        return self._embed(query, "retrieval_query")

    def rerank(self, query: str, documents: list, top_n: int = 5):
        """Uses Cohere to rerank retrieved documents for higher precision."""
        if not self.co or not documents:
            return []
        try:
            results = self.co.rerank(
                model="rerank-english-v3.0",
                query=query,
                documents=documents,
                top_n=top_n,
                return_documents=True,
            )
            return results.results
        except Exception as e:
            print(f"Cohere rerank skipped: {e}")
            return []

    def generate_answer(self, query: str, context: str):
        """Generates a grounded answer based on the provided context."""
        
        # Production-grade system prompt - Updated to remove citations as requested
        prompt = f"""
        You are a helpful AI assistant. Answer the following question based ONLY on the provided context.
        If the context does not contain the answer, state: "I don’t have enough information from your data to answer that right now."
        
        Context:
        {context}
        
        Question:
        {query}
        
        Answer Grounded in Context:
        """
        try:
            response = self.llm.generate_content(prompt)
            
            # Extract text safely
            answer_text = response.text
            
            # Get token usage metrics
            tokens = 0
            if hasattr(response, 'usage_metadata'):
                tokens = response.usage_metadata.total_token_count
            
            return {
                "answer": answer_text,
                "tokens": tokens
            }
        except Exception as e:
            return {
                "answer": f"Error generating answer: {str(e)}",
                "tokens": 0
            }

ai_service = AIService()
