import numpy as np
import uuid
from backend.app.config import settings

# Load embedding model lazily
_encoder = None
def get_encoder():
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device='cpu')
        except Exception:
            # Lightweight mock encoder fallback if model not downloaded/installed
            class MockEncoder:
                def encode(self, text):
                    # Deterministic hash vector
                    np.random.seed(abs(hash(text)) % (2**32))
                    v = np.random.uniform(-1, 1, settings.EMBEDDING_VECTOR_SIZE)
                    return v / np.linalg.norm(v)
            _encoder = MockEncoder()
    return _encoder

def get_embedding(text: str) -> list[float]:
    model = get_encoder()
    embedding = model.encode(text)
    return embedding.tolist()

# Mock/In-Memory Vector database fallback
class InMemoryVectorDB:
    def __init__(self):
        # schema: list of dicts {"id": str, "vector": list[float], "payload": dict}
        self.records = []

    def create_collection(self, collection_name: str, size: int):
        pass  # No-op in-memory

    def upsert(self, collection_name: str, points: list):
        for pt in points:
            # point representation: {"id": str/int, "vector": list, "payload": dict}
            self.records.append(pt)

    def search(self, collection_name: str, query_vector: list, query_filter: dict = None, limit: int = 5):
        tenant_id = None
        if query_filter and "must" in query_filter:
            for condition in query_filter["must"]:
                if condition.get("key") == "tenant_id" and condition.get("match"):
                    tenant_id = condition["match"].get("value")

        # Filter records
        matched = []
        for r in self.records:
            if tenant_id and r["payload"].get("tenant_id") != tenant_id:
                continue
            matched.append(r)

        if not matched:
            return []

        # Compute cosine similarities
        qv = np.array(query_vector)
        results = []
        for r in matched:
            rv = np.array(r["vector"])
            dot = np.dot(qv, rv)
            norm_q = np.linalg.norm(qv)
            norm_r = np.linalg.norm(rv)
            similarity = float(dot / (norm_q * norm_r)) if norm_q > 0 and norm_r > 0 else 0.0
            results.append({
                "id": r["id"],
                "score": similarity,
                "payload": r["payload"]
            })

        # Sort by similarity score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

# Global vector DB wrapper
import importlib

class VectorDBClient:
    def __init__(self):
        self.db_type = settings.VECTOR_DB_TYPE.lower()
        self.qdrant_client = None
        self.fallback_db = InMemoryVectorDB()
        
        if self.db_type == "qdrant":
            try:
                qc_mod = importlib.import_module("qdrant_client")
                QdrantClient = getattr(qc_mod, "QdrantClient")
                self.qdrant_client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
                # Create collection if not exists
                self.qdrant_client.recreate_collection(
                    collection_name=settings.VECTOR_COLLECTION_NAME,
                    vectors_config={"size": settings.EMBEDDING_VECTOR_SIZE, "distance": "Cosine"}
                )
            except Exception as e:
                print(f"Failed to initialize Qdrant, falling back to In-Memory Vector DB: {e}")
                self.db_type = "chroma"  # fall back

    def upsert_knowledge(self, tenant_id: str, doc_type: str, content: str, metadata: dict = None):
        doc_id = str(uuid.uuid4())
        vector = get_embedding(content)
        payload = {
            "tenant_id": tenant_id,
            "type": doc_type,
            "content": content,
            "metadata": metadata or {}
        }

        if self.db_type == "qdrant" and self.qdrant_client:
            try:
                models = importlib.import_module("qdrant_client.models")
                PointStruct = getattr(models, "PointStruct")
                self.qdrant_client.upsert(
                    collection_name=settings.VECTOR_COLLECTION_NAME,
                    points=[PointStruct(id=doc_id, vector=vector, payload=payload)]
                )
                return doc_id
            except Exception:
                pass

        # Fallback (ChromaDB or In-Memory)
        self.fallback_db.upsert(
            collection_name=settings.VECTOR_COLLECTION_NAME,
            points=[{"id": doc_id, "vector": vector, "payload": payload}]
        )
        return doc_id

    def search_knowledge(self, tenant_id: str, query_text: str, doc_type: str = None, limit: int = 5):
        query_vector = get_embedding(query_text)
        
        # Build standard filter structure for tenant isolation
        if self.db_type == "qdrant" and self.qdrant_client:
            try:
                models = importlib.import_module("qdrant_client.models")
                Filter = getattr(models, "Filter")
                FieldCondition = getattr(models, "FieldCondition")
                MatchValue = getattr(models, "MatchValue")

                must_conditions = [
                    FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
                ]
                if doc_type:
                    must_conditions.append(
                        FieldCondition(key="type", match=MatchValue(value=doc_type))
                    )
                hits = self.qdrant_client.search(
                    collection_name=settings.VECTOR_COLLECTION_NAME,
                    query_vector=query_vector,
                    query_filter=Filter(must=must_conditions),
                    limit=limit
                )
                return [{"id": hit.id, "score": hit.score, "payload": hit.payload} for hit in hits]
            except Exception:
                pass

        # Fallback filter
        fallback_filter = {
            "must": [
                {"key": "tenant_id", "match": {"value": tenant_id}}
            ]
        }
        if doc_type:
            fallback_filter["must"].append({"key": "type", "match": {"value": doc_type}})

        return self.fallback_db.search(
            collection_name=settings.VECTOR_COLLECTION_NAME,
            query_vector=query_vector,
            query_filter=fallback_filter,
            limit=limit
        )

vector_db = VectorDBClient()

