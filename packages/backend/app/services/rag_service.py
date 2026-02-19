"""
FAISS-based RAG memory for the SWE-Agent pipeline.

Stores past pipeline results (issue → patch) as vector embeddings so that
the agents can retrieve similar past fixes as context, improving patch quality.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MEMORY_DIR = Path(__file__).parent / "memory_store"
_INDEX_PATH = _MEMORY_DIR / "faiss.index"
_META_PATH = _MEMORY_DIR / "metadata.pkl"

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False
    logger.warning("FAISS/sentence-transformers not installed — RAG memory disabled.")


class RAGMemory:
    """
    Vector store for past pipeline results.
    Uses sentence-transformers for embeddings and FAISS for similarity search.
    """

    EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

    def __init__(self) -> None:
        if not _FAISS_AVAILABLE:
            self._enabled = False
            return

        self._enabled = True
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)

        self._model = SentenceTransformer("all-MiniLM-L6-v2")

        # Load or create FAISS index
        if _INDEX_PATH.exists() and _META_PATH.exists():
            self._index = faiss.read_index(str(_INDEX_PATH))
            with open(_META_PATH, "rb") as f:
                self._metadata: list[dict] = pickle.load(f)
            logger.info("RAG memory loaded: %d entries", len(self._metadata))
        else:
            self._index = faiss.IndexFlatL2(self.EMBEDDING_DIM)
            self._metadata = []
            logger.info("RAG memory initialized (empty)")

    def _embed(self, text: str) -> "np.ndarray":
        import numpy as np
        vec = self._model.encode([text], normalize_embeddings=True)
        return vec.astype(np.float32)

    def store(self, issue_text: str, result: dict) -> None:
        """Store a pipeline result keyed by the issue text embedding."""
        if not self._enabled:
            return
        try:
            vec = self._embed(issue_text)
            self._index.add(vec)
            self._metadata.append({
                "type": "fix",
                "issue_text": issue_text[:500],
                "result": result
            })
            # Persist
            faiss.write_index(self._index, str(_INDEX_PATH))
            with open(_META_PATH, "wb") as f:
                pickle.dump(self._metadata, f)
            logger.info("RAG memory: stored entry (total=%d)", len(self._metadata))
        except Exception as e:
            logger.warning("RAG store failed: %s", e)

    def store_document(self, text: str, metadata: dict) -> None:
        """Store a generic knowledge document chunk."""
        if not self._enabled:
            return
        try:
            # Chunking might be needed for very large texts, but let's keep it simple for now
            vec = self._embed(text[:2000]) # Embed the first 2k chars
            self._index.add(vec)
            self._metadata.append({
                "type": "document",
                "text": text,
                "metadata": metadata
            })
            faiss.write_index(self._index, str(_INDEX_PATH))
            with open(_META_PATH, "wb") as f:
                pickle.dump(self._metadata, f)
            logger.info("RAG memory: stored document '%s'", metadata.get('filename', 'unknown'))
        except Exception as e:
            logger.warning("RAG document store failed: %s", e)

    def list_documents(self) -> list[dict]:
        """List all stored documents (not fixes)."""
        return [m for m in self._metadata if m.get("type") == "document"]

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve the top-k most similar past results or documents."""
        if not self._enabled or self._index.ntotal == 0:
            return []
        try:
            vec = self._embed(query)
            distances, indices = self._index.search(vec, min(top_k, self._index.ntotal))
            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if idx >= 0 and dist < 1.8:  # slightly higher threshold
                    results.append(self._metadata[idx])
            return results
        except Exception as e:
            logger.warning("RAG retrieve failed: %s", e)
            return []

    def build_context_prompt(self, query: str) -> str:
        """Build a context string for injection into agent prompts."""
        similar = self.retrieve(query)
        if not similar:
            return ""
        
        parts = ["=== RAG Knowledge Retrieval ==="]
        fixes = [s for s in similar if s.get("type") == "fix"]
        docs = [s for s in similar if s.get("type") == "document"]

        if fixes:
            parts.append("\n[Similar Past Fixes]")
            for i, entry in enumerate(fixes, 1):
                r = entry.get("result", {})
                parts.append(
                    f"{i}. Issue: {entry.get('issue_text', '')[:150]}\n"
                    f"   Solution: {r.get('root_cause', '')[:200]}"
                )

        if docs:
            parts.append("\n[Related Documentation]")
            for i, entry in enumerate(docs, 1):
                m = entry.get("metadata", {})
                parts.append(
                    f"{i}. File: {m.get('filename', 'unknown')}\n"
                    f"   Content: {entry.get('text', '')[:800]}..."
                )
        
        return "\n".join(parts)


# Singleton
_rag_memory: Optional[RAGMemory] = None


def get_rag_memory() -> RAGMemory:
    global _rag_memory
    if _rag_memory is None:
        _rag_memory = RAGMemory()
    return _rag_memory
