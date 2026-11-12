
from __future__ import annotations

import logging
import math
import re
import threading
from collections import Counter

import numpy as np

log = logging.getLogger("rag.retrieval")


def tokenize(text: str) -> list[str]:

    raw = re.findall(
        r"[a-z0-9_]+(?:-[a-z0-9_]+)*",
        text.lower()
    )

    expanded = []

    for token in raw:
        expanded.append(token)

        if "-" in token:
            expanded.extend(
                part for part in token.split("-") if part
            )

    return expanded


class BM25Index:
    """Small self-contained Okapi BM25 index."""

    def __init__(
        self,
        corpus: list[list[str]],
        k1: float = 1.5,
        b: float = 0.75
    ):

        self.corpus = corpus
        self.k1 = k1
        self.b = b

        self.doc_len = [len(doc) for doc in corpus]
        self.avgdl = (
            sum(self.doc_len) / max(1, len(self.doc_len))
        )

        self.tf = [Counter(doc) for doc in corpus]

        self.df = Counter(
            token
            for doc in corpus
            for token in set(doc)
        )

        self.n = len(corpus)

    def get_scores(self, query_tokens: list[str]) -> np.ndarray:

        scores = np.zeros(self.n, dtype=float)

        for term in query_tokens:

            df = self.df.get(term, 0)

            if not df:
                continue

            idf = math.log(
                1 + (self.n - df + 0.5) / (df + 0.5)
            )

            for i, counts in enumerate(self.tf):

                freq = counts.get(term, 0)

                if not freq:
                    continue

                denominator = freq + self.k1 * (
                    1 - self.b
                    + self.b * self.doc_len[i] / max(1, self.avgdl)
                )

                scores[i] += (
                    idf
                    * (freq * (self.k1 + 1))
                    / denominator
                )

        return scores


class HybridRetriever:

    def __init__(
        self,
        chunks: list[dict],
        mode: str = "hybrid",
        embedding_model: str = (
            "sentence-transformers/all-MiniLM-L6-v2"
        )
    ):

        if not chunks:
            raise ValueError("No chunks available to index")

        # Snapshot the chunk collection for this index.
        self.chunks = tuple(dict(chunk) for chunk in chunks)
        self.mode = mode

        self.bm25 = BM25Index([
            tokenize(chunk["text"] + " " + chunk["title"])
            for chunk in self.chunks
        ])

        self.embedder = None
        self.vectors = None

        # Protect shared embedding-model inference across threads.
        self.embedding_lock = threading.Lock()

        if mode == "hybrid":

            try:
                from sentence_transformers import SentenceTransformer

                self.embedder = SentenceTransformer(embedding_model)

                vectors = self.embedder.encode(
                    [chunk["text"] for chunk in self.chunks],
                    normalize_embeddings=True,
                    show_progress_bar=False
                )

                self.vectors = np.asarray(vectors)
                self.vectors.setflags(write=False)

                log.info(
                    "EMBEDDING_INDEX_READY model=%s chunks=%d",
                    embedding_model,
                    len(self.chunks)
                )

            except Exception as exc:

                log.exception(
                    "EMBEDDING_INIT_FAILED falling_back_to_bm25 error=%s",
                    type(exc).__name__
                )

                self.embedder = None
                self.vectors = None
                self.mode = "bm25"

    def search(
        self,
        query: str,
        top_k: int = 5,
        role: str | None = None
    ) -> list[dict]:

        if top_k <= 0:
            return []

        tokens = tokenize(query)

        if not tokens:
            return []

        # BM25 uses local arrays and read-only index data.
        bm_scores = np.asarray(
            self.bm25.get_scores(tokens),
            dtype=float
        )

        bm_norm = bm_scores / (bm_scores + 3.0)

        sem_scores = np.zeros(
            len(self.chunks),
            dtype=float
        )

        if self.mode == "hybrid" and self.embedder is not None:

            # Serialize access to the shared embedding model.
            with self.embedding_lock:
                query_vector = self.embedder.encode(
                    [query],
                    normalize_embeddings=True,
                    show_progress_bar=False
                )[0]

            sem_scores = np.maximum(
                0,
                self.vectors @ query_vector
            )

            scores = (
                0.55 * bm_norm
                + 0.45 * sem_scores
            )

        else:
            scores = bm_norm

        results = []
        normalized_role = (
            str(role).strip().casefold()
            if role is not None
            else None
        )

        for i, chunk in enumerate(self.chunks):

            roles = chunk.get("roles") or []

            if normalized_role and roles:
                allowed_roles = {
                    str(allowed_role).strip().casefold()
                    for allowed_role in roles
                }
                if normalized_role not in allowed_roles:
                    continue

            score = float(scores[i])

            if score <= 0:
                continue

            results.append({
                **chunk,
                "score": round(score, 4),
                "bm25_score": round(float(bm_norm[i]), 4),
                "semantic_score": (
                    round(float(sem_scores[i]), 4)
                    if self.embedder is not None
                    else None
                )
            })

        results.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        log.info(
            "RETRIEVAL_COMPLETE query_chars=%d candidates=%d returned=%d mode=%s",
            len(query),
            len(results),
            min(top_k, len(results)),
            self.mode
        )

        return results[:top_k]
