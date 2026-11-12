
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from .config import settings
from .ingestion import load_documents, build_chunks
from .retriever import HybridRetriever
from .generator import GroqGenerator

log = logging.getLogger("rag.pipeline")


class RAGPipeline:

    def __init__(self):
        self.documents: list[dict] = []
        self.chunks: list[dict] = []
        self.retriever = None
        self.generator = GroqGenerator()
        self.last_ingest_error: str | None = None

        self.rebuild()

    # ---------------- INGESTION ----------------

    def rebuild(self) -> dict:

        try:
            log.info("INGESTION_STARTED")

            docs = load_documents()

            if not docs:
                raise RuntimeError("No documents found under data/")

            chunks = build_chunks(
                docs,
                settings.chunk_size,
                settings.chunk_overlap
            )

            # Build the new retriever before replacing the old one.
            new_retriever = HybridRetriever(
                chunks,
                settings.retrieval_mode,
                settings.embedding_model
            )

            # Publish the new index only after successful construction.
            self.documents = docs
            self.chunks = chunks
            self.retriever = new_retriever
            self.last_ingest_error = None

            log.info(
                "PIPELINE_READY documents=%d chunks=%d mode=%s",
                len(docs),
                len(chunks),
                new_retriever.mode
            )

            return {
                "documents": len(docs),
                "chunks": len(chunks),
                "retrieval_mode": new_retriever.mode
            }

        except Exception as exc:
            self.last_ingest_error = (
                f"{type(exc).__name__}: {exc}"
            )
            log.exception("PIPELINE_BUILD_FAILED")
            raise

    # ---------------- RETRIEVAL ----------------

    def retrieve(
        self,
        question: str,
        role: str | None = None,
        top_k: int | None = None
    ) -> tuple[list[dict], bool]:

        retriever = self.retriever

        if retriever is None:
            raise RuntimeError("RETRIEVER_NOT_INITIALIZED")

        hits = retriever.search(
            question,
            top_k if top_k is not None else settings.top_k,
            role
        )

        score = hits[0]["score"] if hits else 0.0

        relevant = (
            bool(hits)
            and score >= settings.min_relevance_score
        )

        log.info(
            "RETRIEVAL_COMPLETE hits=%d score=%.4f relevant=%s",
            len(hits),
            score,
            relevant
        )

        return hits, relevant

    async def retrieve_async(
        self,
        question: str,
        role: str | None = None,
        top_k: int | None = None
    ) -> tuple[list[dict], bool]:

        # Keep synchronous retrieval from blocking the event loop.
        return await asyncio.to_thread(
            self.retrieve,
            question,
            role,
            top_k
        )

    # ---------------- RESPONSE METADATA ----------------

    @staticmethod
    def get_page_context(hits: list[dict]) -> dict | None:

        for hit in hits:
            route = hit.get("route")

            if (
                hit.get("source_type") == "product_knowledge"
                and isinstance(route, str)
                and route.startswith("/")
                and not route.startswith("//")
                and "\\" not in route
            ):
                return {
                    "page_id": hit.get("page_id") or hit.get("id"),
                    "page_title": hit.get("title"),
                    "route": route
                }

        return None

    @staticmethod
    def get_sources(hits: list[dict]) -> list[dict]:

        return [
            {
                "chunk_id": hit["chunk_id"],
                "title": hit["title"],
                "source": hit["source"],
                "source_type": hit["source_type"],
                "score": hit["score"]
            }
            for hit in hits
        ]

    @staticmethod
    def get_navigation_context(hits: list[dict]) -> dict:

        for hit in hits:

            if hit.get("source_type") != "product_knowledge":
                continue

            topic_id = hit.get("id")

            if not topic_id:
                continue

            return {
                "id": topic_id,
                "steps": hit.get("navigation_steps") or []
            }

        return {
            "id": None,
            "steps": []
        }

    def get_retrieval_info(self, hits: list[dict]) -> dict:

        retriever = self.retriever

        return {
            "mode": retriever.mode if retriever else None,
            "count": len(hits),
            "top_score": hits[0]["score"] if hits else 0.0
        }

    def get_metadata(
        self,
        hits: list[dict],
        relevant: bool
    ) -> dict:

        page_context = self.get_page_context(hits) if relevant else None

        return {
            "page_context": page_context,
            "guide_available": page_context is not None,
            "sources": self.get_sources(hits) if relevant else [],
            "retrieval": self.get_retrieval_info(hits)
        }

    # ---------------- NORMAL CHAT ----------------

    async def ask(
        self,
        question: str,
        role: str | None = None,
        current_page: str | None = None,
        top_k: int | None = None
    ) -> dict[str, Any]:

        trace = []

        # Stage 1: Retrieval
        try:
            hits, relevant = await self.retrieve_async(
                question,
                role,
                top_k
            )

            trace.append({
                "stage": "retrieval",
                "status": "ok",
                "hit_count": len(hits)
            })

        except Exception as exc:
            log.exception("RETRIEVAL_FAILED")

            return {
                "answer": "I couldn't find the requested information. Please try again.",
                "steps": [],
                "id": None,
                "status": "retrieval_error"
            }

        metadata = self.get_metadata(hits, relevant)

        # Stage 2: Relevance check
        if not relevant:
            return {
                "answer": (
                    "I couldn't find sufficiently relevant "
                    "information in the knowledge base. "
                    "Try rephrasing your question."
                ),
                "status": "no_relevant_context",
                **metadata,
                "trace": trace + [{
                    "stage": "relevance_check",
                    "status": "failed"
                }]
            }

        trace.append({
            "stage": "relevance_check",
            "status": "passed"
        })

        # Stage 3: Async LLM generation
        try:
            answer = await self.generator.generate(
                question,
                hits,
                current_page
            )

            status = "ok"

            trace.append({
                "stage": "groq_generation",
                "status": "ok",
                "model": settings.groq_model
            })

        except Exception as exc:
            log.exception("GROQ_GENERATION_FAILED")

            answer = (
                "I found relevant documentation, but couldn't "
                "generate an answer. Please try again."
            )

            status = "generation_error"

            trace.append({
                "stage": "groq_generation",
                "status": "failed",
                "error": type(exc).__name__
            })

        navigation = self.get_navigation_context(hits)

        return {
            "answer": answer,
            "steps": navigation["steps"],
            "id": navigation["id"],
            "status": status,
            "trace": trace
        }

    # ---------------- STREAMING CHAT ----------------

    async def ask_stream(
        self,
        question: str,
        role: str | None = None,
        current_page: str | None = None,
        top_k: int | None = None
    ) -> AsyncIterator[dict]:

        # Stage 1: Retrieval
        try:
            hits, relevant = await self.retrieve_async(
                question,
                role,
                top_k
            )

        except Exception as exc:
            log.exception("STREAM_RETRIEVAL_FAILED")

            yield {
                "type": "error",
                "status": "retrieval_error",
                "message": "I couldn't search the knowledge base.",
                "page_context": None,
                "guide_available": False,
                "trace": [{
                    "stage": "retrieval",
                    "status": "failed",
                    "error": type(exc).__name__
                }]
            }
            return

        metadata = self.get_metadata(hits, relevant)

        yield {
            "type": "start",
            "status": "generating" if relevant else "no_relevant_context",
            **metadata
        }

        # Stage 2: Relevance check
        if not relevant:
            yield {
                "type": "token",
                "content": (
                    "I couldn't find sufficiently relevant "
                    "information in the knowledge base. "
                    "Try rephrasing your question."
                )
            }
            yield {
                "type": "done",
                "status": "no_relevant_context"
            }
            return

        # Stage 3: Async streaming generation
        try:
            async for token in self.generator.generate_stream(
                question,
                hits,
                current_page
            ):
                yield {
                    "type": "token",
                    "content": token
                }

            yield {
                "type": "done",
                "status": "ok",
                "trace": [
                    {"stage": "retrieval", "status": "ok"},
                    {"stage": "relevance_check", "status": "passed"},
                    {
                        "stage": "groq_generation",
                        "status": "ok",
                        "model": settings.groq_model
                    }
                ]
            }

        except Exception as exc:
            log.exception("STREAM_GENERATION_FAILED")

            yield {
                "type": "error",
                "status": "generation_error",
                "message": (
                    "Answer generation failed. Please try again."
                ),
                "trace": [{
                    "stage": "groq_generation",
                    "status": "failed",
                    "error": type(exc).__name__
                }]
            }
