from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env from backend/ or current dir
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Support running from project root (import as package) or from inside backend/ (direct run)
try:
    from backend.utils.database import postgres_db
    from backend.utils.vector_db import vector_db
    from backend.services.rag_service import rag_service
    from backend.services.faq_service import faq_service
    from backend.services.auth_service import auth_service, get_admin_user, ADMIN_USERNAME, ADMIN_PASSWORD
except ModuleNotFoundError:
    from utils.database import postgres_db
    from utils.vector_db import vector_db
    from services.rag_service import rag_service
    from services.faq_service import faq_service
    from services.auth_service import auth_service, get_admin_user, ADMIN_USERNAME, ADMIN_PASSWORD



app = FastAPI(title="Mini RAG API")

# CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IngestRequest(BaseModel):
    text: str
    source: Optional[str] = "paste"
    title: Optional[str] = None

class QueryRequest(BaseModel):
    query: str

class LoginRequest(BaseModel):
    username: str
    password: str

@app.on_event("startup")
async def startup_db_client():
    # Required — must succeed or API cannot persist data
    await postgres_db.connect()
    try:
        vector_db.connect()
    except Exception as e:
        print(f"Startup warning (Pinecone): {e}")
    try:
        await faq_service.initialize()
    except Exception as e:
        print(f"Startup warning (FAQ init): {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    await postgres_db.disconnect()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/login")
async def login(request: LoginRequest):
    # Fixed admin credentials from .env for this assignment
    if request.username == ADMIN_USERNAME and request.password == ADMIN_PASSWORD:
        token = auth_service.create_access_token({"sub": request.username, "role": "admin"})
        return {"access_token": token, "token_type": "bearer"}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/ingest")
async def ingest_text(request: IngestRequest, admin: dict = Depends(get_admin_user)):
    try:
        # Generate title if not provided
        doc_title = request.title
        if not doc_title:
            doc_title = request.text[:50] + "..." if len(request.text) > 50 else request.text

        doc_id = await rag_service.ingest_text(request.text, {
            "source": request.source,
            "title": doc_title
        })
        return {"status": "success", "doc_id": doc_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/query") 
async def query_rag(request: QueryRequest):
    try:
        # 1. FAST FAQ LAYER
        faq_result = await faq_service.get_answer(request.query)
        if faq_result:
             return {
                 "answer": faq_result["answer"],
                 "sources": [{"text": "FAQ Database", "metadata": {"source": "faq", "type": faq_result["source"]}}],
                 "metrics": {
                     "time_seconds": 0.05,
                     "tokens": 0,
                     "cost_estimate": 0.0
                 }
             }

        # 2. SLOW RAG LAYER
        result = await rag_service.query(request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    # Reload subprocess must import the same module path the parent used. From backend/ use main:app;
    # from repo root with PYTHONPATH set, backend.main:app works.
    _backend_dir = Path(__file__).resolve().parent
    _app = "main:app" if Path.cwd().resolve() == _backend_dir else "backend.main:app"
    _host = os.getenv("HOST", "0.0.0.0")
    _port = int(os.getenv("PORT", "8000"))
    uvicorn.run(_app, host=_host, port=_port, reload=True)
