from langchain_text_splitters import RecursiveCharacterTextSplitter
try:
    # When running from project root (package mode)
    from backend.services.ai_service import ai_service
    from backend.utils.vector_db import vector_db
    from backend.utils.database import postgres_db
except ModuleNotFoundError:
    # When running from inside backend/ (module mode)
    from services.ai_service import ai_service
    from utils.vector_db import vector_db
    from utils.database import postgres_db
import uuid
import time

class RAGService:
    def __init__(self):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=150,
            length_function=len,
            is_separator_regex=False,
        )

    async def ingest_text(self, text: str, metadata: dict):
        # 1. Chunking
        chunks = self.text_splitter.split_text(text)
        
        doc_id = str(uuid.uuid4())
        metadata["doc_id"] = doc_id
        
        # 2. Store in PostgreSQL
        row = {
            "doc_id": doc_id,
            "text": text,
            "metadata": metadata,
            "chunk_count": len(chunks)
        }
        await postgres_db.insert_document("documents", row)
        
        # 3. Embedding & Store in Vector DB
        vectors = []
        for i, chunk in enumerate(chunks):
            embedding = ai_service.get_embeddings(chunk)
            vectors.append({
                "id": f"{doc_id}_{i}",
                "values": embedding,
                "metadata": {
                    "text": chunk,
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "source": metadata.get("source", "unknown"),
                    "title": metadata.get("title", "Untitled")
                }
            })
            
        vector_db.upsert_vectors(vectors)
        return doc_id

    async def query(self, query_text: str):
        start_time = time.time()
        
        # 1. Embed Query
        query_embedding = ai_service.get_query_embedding(query_text)
        
        # 2. Retrieval (Top-K)
        retrieval_results = vector_db.query_vectors(query_embedding, top_k=10)
        
        initial_chunks = [
            {
                "text": match.metadata["text"],
                "metadata": match.metadata,
                "score": match.score
            }
            for match in retrieval_results.matches
        ]
        
        # 3. Reranking (optional; if Cohere missing or fails, use vector retrieval order)
        docs_to_rerank = [c["text"] for c in initial_chunks]
        reranked_results = ai_service.rerank(query_text, docs_to_rerank, top_n=5)

        top_chunks = []
        context_parts = []
        if reranked_results:
            for i, res in enumerate(reranked_results):
                chunk_data = initial_chunks[res.index]
                top_chunks.append(chunk_data)
                title = chunk_data["metadata"].get("title", "Document")
                context_parts.append(f"Source [{i+1}] (From: {title}):\n{chunk_data['text']}")
        else:
            for i, chunk_data in enumerate(initial_chunks[:5]):
                top_chunks.append(chunk_data)
                title = chunk_data["metadata"].get("title", "Document")
                context_parts.append(f"Source [{i+1}] (From: {title}):\n{chunk_data['text']}")
            
        context = "\n\n".join(context_parts)
        
        # 4. Generation
        gen_result = ai_service.generate_answer(query_text, context)
        
        end_time = time.time()
        
        return {
            "answer": gen_result["answer"],
            "sources": top_chunks,
            "metrics": {
                "time_seconds": round(end_time - start_time, 3),
                "tokens": gen_result["tokens"],
                "cost_estimate": round(gen_result["tokens"] * 0.000000125, 6) # Rough Gemini 1.5 Flash cost
            }
        }

rag_service = RAGService()
