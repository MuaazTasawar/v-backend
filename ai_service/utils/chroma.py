import logging
from functools import lru_cache

from ai_service.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache
def get_chroma_client():
    """Returns a singleton persistent ChromaDB client."""
    import chromadb

    return chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)


def get_embedding_function():
    """
    Embedding function used for all Venturify vector collections.
    Uses Anthropic-compatible sentence embeddings via a local model
    to avoid an extra paid embeddings API call per chunk.
    """
    from chromadb.utils import embedding_functions

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )


def get_or_create_collection(collection_name: str):
    client = get_chroma_client()
    embed_fn = get_embedding_function()
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Simple sliding-window chunker for startup context documents."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def index_startup_documents(
    startup_id: str,
    pitch_context: dict,
    generated_documents: list[dict],
) -> str:
    """
    Builds (or rebuilds) the ChromaDB collection for a startup from its
    pitch context and generated documents. Returns the collection name.
    """
    collection_name = f"startup_{startup_id.replace('-', '_')}"
    collection = get_or_create_collection(collection_name)

    # Clear existing entries for a clean re-index
    try:
        existing = collection.get()
        if existing and existing.get("ids"):
            collection.delete(ids=existing["ids"])
    except Exception as exc:
        logger.warning("Could not clear existing collection %s: %s", collection_name, exc)

    documents, metadatas, ids = [], [], []
    idx_counter = 0

    # Index pitch context fields
    for key, value in (pitch_context or {}).items():
        if not value or not isinstance(value, str):
            continue
        for chunk in chunk_text(value):
            documents.append(chunk)
            metadatas.append({"source": "pitch_context", "field": key})
            ids.append(f"{collection_name}_{idx_counter}")
            idx_counter += 1

    # Index generated document content
    for doc in generated_documents or []:
        content_json = doc.get("content_json", {})
        doc_type = doc.get("document_type", "unknown")
        text_blob = " ".join(
            str(v) for v in content_json.values() if isinstance(v, (str, int, float))
        )
        for chunk in chunk_text(text_blob):
            documents.append(chunk)
            metadatas.append({"source": "generated_document", "document_type": doc_type})
            ids.append(f"{collection_name}_{idx_counter}")
            idx_counter += 1

    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info("Indexed %d chunks for %s", len(documents), collection_name)

    return collection_name


def query_collection(collection_name: str, query: str, n_results: int = 5) -> dict:
    """
    Queries a startup's collection and returns results plus the best
    cosine similarity score for confidence routing (dual-layer RAG).
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(
            name=collection_name, embedding_function=get_embedding_function()
        )
    except Exception:
        return {"documents": [], "best_similarity": 0.0}

    results = collection.query(query_texts=[query], n_results=n_results)

    distances = results.get("distances", [[]])[0]
    # Cosine distance -> similarity: similarity = 1 - distance
    best_similarity = 1 - min(distances) if distances else 0.0

    return {
        "documents": results.get("documents", [[]])[0],
        "metadatas": results.get("metadatas", [[]])[0],
        "best_similarity": best_similarity,
    }