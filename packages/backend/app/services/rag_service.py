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
            self._metadata.append({"issue_text": issue_text[:500], "result": result})
            # Persist
            faiss.write_index(self._index, str(_INDEX_PATH))
            with open(_META_PATH, "wb") as f:
                pickle.dump(self._metadata, f)
            logger.info("RAG memory: stored entry (total=%d)", len(self._metadata))
        except Exception as e:
            logger.warning("RAG store failed: %s", e)

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """Retrieve the top-k most similar past results."""
        if not self._enabled or self._index.ntotal == 0:
            return []
        try:
            vec = self._embed(query)
            distances, indices = self._index.search(vec, min(top_k, self._index.ntotal))
            results = []
            for idx, dist in zip(indices[0], distances[0]):
                if idx >= 0 and dist < 1.5:  # similarity threshold
                    results.append(self._metadata[idx])
            return results
        except Exception as e:
            logger.warning("RAG retrieve failed: %s", e)
            return []

    def build_context_prompt(self, query: str) -> str:
        """Build a context string from similar past fixes for injection into agent prompts."""
        similar = self.retrieve(query)
        if not similar:
            return ""
        parts = ["=== Similar Past Fixes (RAG Memory) ==="]
        for i, entry in enumerate(similar, 1):
            r = entry.get("result", {})
            parts.append(
                f"\n[Past Fix {i}]\n"
                f"Issue: {entry.get('issue_text', '')[:200]}\n"
                f"Classification: {r.get('classification', 'unknown')}\n"
                f"Root Cause: {r.get('root_cause', '')[:300]}\n"
                f"Patch (excerpt): {r.get('patch_diff', '')[:400]}\n"
            )
        return "\n".join(parts)


# Singleton
_rag_memory: Optional[RAGMemory] = None


def get_rag_memory() -> RAGMemory:
    global _rag_memory
    if _rag_memory is None:
        _rag_memory = RAGMemory()
    return _rag_memory
