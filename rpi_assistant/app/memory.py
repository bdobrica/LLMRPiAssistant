"""Episodic memory system for the RPI Assistant.

Implements:
- Working memory (short-term, in RAM) - rolling buffer of conversation turns
- Episodic memory (long-term, on disk) - vector-based storage with summaries
- Memory retrieval using cosine similarity search

Optimized for Raspberry Pi with:
- float16 storage for vectors
- np.memmap for efficient disk access
- Normalized vectors for fast cosine similarity
"""
import json
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np


def load_meta(meta_path: str) -> dict:
    """Load metadata from JSON file.
    
    Args:
        meta_path: Path to metadata JSON file.
    
    Returns:
        Dictionary containing metadata.
    """
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_meta(meta_path: str, meta: dict) -> None:
    """Save metadata to JSON file atomically.
    
    Args:
        meta_path: Path to metadata JSON file.
        meta: Dictionary containing metadata.
    """
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, meta_path)


def l2_normalize(x: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """L2 normalize a vector to unit length.
    
    Args:
        x: Input vector.
        eps: Small epsilon to avoid division by zero.
    
    Returns:
        Unit-normalized vector.
    """
    x = x.astype(np.float32, copy=False)
    n = np.linalg.norm(x)
    return x / (n + eps)


class MemmapVectorStore:
    """Memory-mapped vector store for efficient storage and retrieval.
    
    Stores unit-normalized float16 vectors in a memory-mapped file.
    Supports append and cosine similarity search.
    """
    
    def __init__(self, root: str, dim: int, initial_capacity: int = 1024):
        """Initialize vector store.
        
        Args:
            root: Root directory for storage.
            dim: Embedding dimension (must be consistent).
            initial_capacity: Initial capacity (will grow as needed).
        """
        self.root = root
        self.dim = dim
        os.makedirs(root, exist_ok=True)

        self.vec_path = os.path.join(root, "vectors.f16")
        self.meta_path = os.path.join(root, "meta.json")

        meta = load_meta(self.meta_path)
        if meta:
            assert meta["dim"] == dim, f"Dim mismatch: {meta['dim']} vs {dim}"
            self.capacity = int(meta["capacity"])
            self.count = int(meta["count"])
        else:
            self.capacity = int(initial_capacity)
            self.count = 0
            save_meta(self.meta_path, {"dim": dim, "capacity": self.capacity, "count": self.count})

        self._open_memmap()

    def _open_memmap(self):
        """Open or create the memory-mapped vector file."""
        # Ensure file exists with correct size
        expected_bytes = self.capacity * self.dim * np.dtype(np.float16).itemsize
        if not os.path.exists(self.vec_path):
            with open(self.vec_path, "wb") as f:
                f.truncate(expected_bytes)
        else:
            # Check file size
            actual = os.path.getsize(self.vec_path)
            if actual != expected_bytes:
                raise RuntimeError(f"Vector file size mismatch: {actual} vs {expected_bytes}")

        self.V = np.memmap(
            self.vec_path, dtype=np.float16, mode="r+",
            shape=(self.capacity, self.dim)
        )

    def _persist_meta(self):
        """Save metadata to disk."""
        save_meta(self.meta_path, {"dim": self.dim, "capacity": self.capacity, "count": self.count})

    def _grow(self, new_capacity: int):
        """Grow the vector store capacity.
        
        Args:
            new_capacity: New capacity (must be > current capacity).
        """
        new_capacity = int(new_capacity)
        new_path = self.vec_path + ".new"

        new_bytes = new_capacity * self.dim * np.dtype(np.float16).itemsize
        with open(new_path, "wb") as f:
            f.truncate(new_bytes)

        V_new = np.memmap(new_path, dtype=np.float16, mode="r+", shape=(new_capacity, self.dim))

        # Copy existing data
        if self.count > 0:
            V_new[:self.count, :] = self.V[:self.count, :]
        V_new.flush()

        # Swap in new file
        del self.V
        os.replace(new_path, self.vec_path)

        self.capacity = new_capacity
        self._persist_meta()
        self._open_memmap()

    def add(self, emb_unit: np.ndarray) -> int:
        """Add a unit-normalized embedding to the store.
        
        Args:
            emb_unit: Unit-normalized embedding, shape (D,).
        
        Returns:
            Row index of the added vector.
        """
        if self.count >= self.capacity:
            self._grow(self.capacity * 2)

        i = self.count
        self.V[i, :] = emb_unit.astype(np.float16)
        self.V.flush()

        self.count += 1
        self._persist_meta()
        return i

    def search(self, query_unit: np.ndarray, k: int = 5) -> tuple[np.ndarray, np.ndarray]:
        """Search for top-k most similar vectors.
        
        Args:
            query_unit: Unit-normalized query vector.
            k: Number of results to return.
        
        Returns:
            Tuple of (indices, scores) where scores are cosine similarities.
        """
        n = self.count
        if n == 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

        q = query_unit.astype(np.float32, copy=False)

        # Read only active rows; cast to float32 for dot product
        V = self.V[:n, :].astype(np.float32, copy=False)
        scores = V @ q  # cosine similarity (vectors are normalized)

        k = min(k, n)
        top = np.argpartition(scores, -k)[-k:]
        top = top[np.argsort(scores[top])[::-1]]

        return top.astype(np.int64), scores[top].astype(np.float32)


class SummaryStore:
    """Store for episode summaries with metadata.
    
    Each summary is stored as a separate JSON file, indexed by episode number.
    Also maintains a manifest JSONL for quick metadata access.
    """
    
    def __init__(self, root: str):
        """Initialize summary store.
        
        Args:
            root: Root directory for storage.
        """
        self.root = root
        self.summ_dir = os.path.join(root, "summaries")
        self.manifest_path = os.path.join(root, "manifest.jsonl")
        os.makedirs(self.summ_dir, exist_ok=True)

    def write_summary(self, i: int, summary_text: str, extra: Optional[dict] = None) -> str:
        """Write an episode summary.
        
        Args:
            i: Episode index.
            summary_text: Summary text.
            extra: Additional metadata to store.
        
        Returns:
            Path to the created summary file.
        """
        extra = extra or {}
        rec = {
            "i": int(i),
            "ts": int(time.time()),
            "summary": summary_text,
            **extra
        }
        fname = f"{i:08d}.json"
        fpath = os.path.join(self.summ_dir, fname)

        tmp = fpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        os.replace(tmp, fpath)

        # Append small manifest line
        with open(self.manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"i": i, "file": f"summaries/{fname}", "ts": rec["ts"]}, ensure_ascii=False) + "\n")

        return fpath

    def load_summary(self, i: int) -> dict:
        """Load an episode summary.
        
        Args:
            i: Episode index.
        
        Returns:
            Summary record dictionary.
        """
        fpath = os.path.join(self.summ_dir, f"{i:08d}.json")
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)


class EpisodicMemory:
    """Episodic memory manager.
    
    Combines vector storage and summary storage for efficient
    memory management and retrieval.
    """
    
    def __init__(self, root: str, dim: int):
        """Initialize episodic memory.
        
        Args:
            root: Root directory for memory storage.
            dim: Embedding dimension.
        """
        self.vectors = MemmapVectorStore(root=root, dim=dim, initial_capacity=1024)
        self.summaries = SummaryStore(root=root)

    def commit_episode(self, summary_text: str, embedding: np.ndarray, meta: Optional[dict] = None) -> int:
        """Commit an episode to long-term memory.
        
        Args:
            summary_text: Episode summary text.
            embedding: Episode embedding vector (will be normalized).
            meta: Additional metadata to store.
        
        Returns:
            Episode index.
        """
        emb_unit = l2_normalize(embedding)
        i = self.vectors.add(emb_unit)
        self.summaries.write_summary(i=i, summary_text=summary_text, extra=meta)
        return i

    def retrieve(self, query_embedding: np.ndarray, k: int = 5) -> list[dict]:
        """Retrieve top-k relevant episodes.
        
        Args:
            query_embedding: Query embedding vector (will be normalized).
            k: Number of episodes to retrieve.
        
        Returns:
            List of episode records with scores.
        """
        q_unit = l2_normalize(query_embedding)
        idxs, scores = self.vectors.search(q_unit, k=k)

        out = []
        for i, s in zip(idxs.tolist(), scores.tolist()):
            rec = self.summaries.load_summary(int(i))
            out.append({"i": int(i), "score": float(s), "record": rec})
        return out


class SessionManager:
    """Manages conversation sessions and idle timeout.
    
    Tracks conversation turns within a session and determines
    when to finalize a session based on idle timeout.
    """
    
    def __init__(self, idle_timeout_s: float = 20.0):
        """Initialize session manager.
        
        Args:
            idle_timeout_s: Idle timeout in seconds.
        """
        self.idle_timeout_s = idle_timeout_s
        self.turns: list[dict] = []
        self.last_activity = None  # monotonic time

    def add_turn(self, role: str, text: str):
        """Add a conversation turn to the current session.
        
        Args:
            role: Role (e.g., "user", "assistant").
            text: Turn text.
        """
        self.turns.append({"role": role, "text": text})
        self.last_activity = time.monotonic()

    def is_idle_expired(self) -> bool:
        """Check if the session idle timeout has expired.
        
        Returns:
            True if idle timeout has expired, False otherwise.
        """
        if self.last_activity is None:
            return False
        return (time.monotonic() - self.last_activity) >= self.idle_timeout_s

    def finalize(self) -> list[dict]:
        """Finalize the current session and return turns.
        
        Returns:
            List of conversation turns from the session.
        """
        turns = self.turns
        self.turns = []
        self.last_activity = None
        return turns

    def has_turns(self) -> bool:
        """Check if the session has any turns.
        
        Returns:
            True if session has turns, False otherwise.
        """
        return len(self.turns) > 0

    def get_turns(self) -> list[dict]:
        """Get current session turns without finalizing.
        
        Returns:
            List of conversation turns.
        """
        return self.turns.copy()


def format_memories(memories: list[dict]) -> str:
    """Format retrieved memories for injection into LLM context.
    
    Args:
        memories: List of memory records from retrieval.
    
    Returns:
        Formatted string for LLM context.
    """
    if not memories:
        return ""
    
    lines = ["Relevant past memories (may be imperfect):"]
    for m in memories:
        s = m["score"]
        summ = m["record"]["summary"]
        ts = m["record"].get("ts", None)
        if ts:
            time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            lines.append(f"- (score={s:.3f}, time={time_str}) {summ}")
        else:
            lines.append(f"- (score={s:.3f}) {summ}")
    return "\n".join(lines)
