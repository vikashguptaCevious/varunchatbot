import json
import re
import math
import hashlib
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

try:
    from backend.services.ai_service import ai_service
    from backend.utils.database import postgres_db
except ModuleNotFoundError:
    from services.ai_service import ai_service
    from utils.database import postgres_db

class FAQService:
    def __init__(self):
        self.faqs = []
        self.faq_embeddings = [] # List of (embedding, faq_entry) tuples
        self.exact_match_map = {}
        self.similarity_threshold = 0.75 
        self.collection_name = "faq_vector_store"
        
        # Load JSON config immediately
        self._load_json_config()
        
    async def initialize(self):
        print("Initializing FAQ Service...")
        
        # 1. Load FAQs from disk
        self._load_json_config()
        
        if not self.faqs:
            print("WARNING: No FAQs loaded from JSON.") 
            
        # 2. Generate Greeting FAQs (Dynamic)
        greeting_faqs = self._generate_greeting_faqs()
        print(f"Generated {len(greeting_faqs)} greeting variations.")
        
        # 3. Merge Lists
        all_items = self.faqs + greeting_faqs
        
        # 4. Compute/Load Embeddings
        print(f"Processing embeddings for {len(all_items)} total items (Persistent Mode)...")
        await self._sync_embeddings(all_items)
        
        print(f"FAQ Service Ready: {len(self.faq_embeddings)} vectors loaded in memory.")

    def _load_json_config(self):
        try:
            path = Path(__file__).parent.parent / "data" / "faqs.json"
            if not path.exists():
                # Fallback check
                path = Path(__file__).parent.parent / "data" / "faqs_generated.json"
                
            if not path.exists():
                print(f"ERROR: No FAQ JSON found.")
                return

            with open(path, "r", encoding="utf-8") as f:
                self.faqs = json.load(f)
            
            # Build exact match map for JSON items
            self.exact_match_map = {}
            for entry in self.faqs:
                questions = [entry["question"]] + entry.get("variations", [])
                for q in questions:
                    normalized = self._normalize(q)
                    self.exact_match_map[normalized] = entry
                    
        except Exception as e:
            print(f"Error loading FAQs: {e}")
            self.faqs = []

    def _generate_greeting_faqs(self) -> List[Dict]:
        """Generates 200+ greeting variations."""
        base_greetings = [
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening", 
            "namaste", "yo", "hiya", "howdy", "greetings", "what's up", "sup", "heya",
            "hola", "bonjour", "hallo", "gday", "what is up", "hey there", "hello there"
        ]
        
        modifiers = ["", "!", ".", " there", " bot", " ai", " assistant", " friend", " buddy", " mate", " sir", " maam"]
        typos = ["hy", "hlo", "heyy", "heyyy", "hii", "hiii", "hlw", "hie"]
        
        greetings = []
        
        # 1. Combine base + modifiers
        for g in base_greetings:
            for m in modifiers:
                txt = f"{g}{m}".strip()
                greetings.append(txt)
                
        # 2. Add Typos
        greetings.extend(typos)
        
        # 3. Construct FAQ Entries
        faq_entries = []
        for i, g_text in enumerate(greetings, 1):
            entry = {
                "id": f"greeting_gen_{i}",
                "question": g_text,
                "variations": [],
                "answer": "{{TIME_AWARE_GREETING}}",
                "type": "greeting"
            }
            faq_entries.append(entry)
            
            # Add to exact match map
            normalized = self._normalize(g_text)
            self.exact_match_map[normalized] = entry
            
        return faq_entries

    async def _sync_embeddings(self, items: List[Dict]):
        """
        Iterates through items. 
        Checks PostgreSQL for existing embedding (ID + Hash match).
        If missing, generates and saves.
        Populates self.faq_embeddings.
        """
        self.faq_embeddings = []
        new_embeddings_count = 0
        
        for entry in items:
            # Greetings are covered by exact_match_map only (~260 variants). Embedding each
            # burns the Gemini free tier (1000 embeds/day) for no benefit.
            if entry.get("type") == "greeting":
                continue

            # Create a deterministic content hash
            content_str = entry["question"]
            content_hash = hashlib.sha256(content_str.encode()).hexdigest()
            
            # 1. Check DB
            existing = await postgres_db.get_document(
                self.collection_name, 
                {"faq_id": entry["id"], "content_hash": content_hash}
            )
            
            emb_vector = None
            
            if existing:
                # HIT: Load from DB
                emb_vector = existing["embedding"]
            else:
                # MISS: Generate
                try:
                    # Small delay to avoid burst RPM limits on free tier
                    if new_embeddings_count > 0:
                        await asyncio.sleep(0.25)
                    emb_vector = ai_service.get_embeddings(entry["question"])
                    new_embeddings_count += 1
                    
                    # Save to DB
                    await postgres_db.insert_document(self.collection_name, {
                        "faq_id": entry["id"],
                        "content_hash": content_hash,
                        "embedding": emb_vector,
                        "text": entry["question"],
                        "updated_at": datetime.utcnow()
                    })
                except Exception as e:
                    print(f"Failed to embed {entry['id']}: {e}")
                    continue
            
            # Add to in-memory index
            if emb_vector:
                self.faq_embeddings.append((emb_vector, entry))
                
        if new_embeddings_count > 0:
            print(f"Generated {new_embeddings_count} NEW embeddings. Loaded rest from DB.")
        else:
            print("All embeddings loaded from DB (Zero cost).")

    def _normalize(self, text: str) -> str:
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        return text.strip()

    def _cosine_similarity(self, vec1, vec2):
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def _get_time_aware_greeting(self) -> str:
        """Returns Good Morning/Afternoon/Evening based on server time."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "Good morning! How can I help you today?"
        elif 12 <= hour < 17:
            return "Good afternoon! How can I help you today?"
        else:
            return "Good evening! How can I help you today?"

    async def get_answer(self, query: str) -> Optional[Dict]:
        normalized_q = self._normalize(query)
        
        # 1. Exact Match
        if normalized_q in self.exact_match_map:
            match = self.exact_match_map[normalized_q]
            answer = match["answer"]
            
            if answer == "{{TIME_AWARE_GREETING}}":
                answer = self._get_time_aware_greeting()
                
            print(f"FAQ HIT (Exact): {query}")
            return {"answer": answer, "source": "faq_exact"}

        # 2. Semantic Match
        try:
            query_emb = ai_service.get_query_embedding(normalized_q)
            best_score = -1
            best_entry = None
            
            for doc_emb, entry in self.faq_embeddings:
                score = self._cosine_similarity(query_emb, doc_emb)
                if score > best_score:
                    best_score = score
                    best_entry = entry
            
            print(f"FAQ Best Score: {best_score} for '{query}'")
            
            if best_score >= self.similarity_threshold:
                answer = best_entry["answer"]
                if answer == "{{TIME_AWARE_GREETING}}":
                    answer = self._get_time_aware_greeting()
                    
                print(f"FAQ HIT (Semantic): {query} -> {best_entry['question']}")
                return {
                    "answer": answer,
                    "source": "faq_semantic",
                    "confidence": round(best_score, 4)
                }
                
        except Exception as e:
            print(f"FAQ Semantic Check Failed: {e}")
            
        return None

faq_service = FAQService()
