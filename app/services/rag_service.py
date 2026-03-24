from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from io import BytesIO
from typing import Iterable
import os
from uuid import uuid4
import logging

from fastapi import UploadFile
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from docx import Document as DocxDocument

def _disable_chroma_telemetry() -> None:
    # Force-disable Chroma/PostHog telemetry.
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    os.environ["CHROMA_TELEMETRY"] = "False"
    os.environ["CHROMADB_ANONYMIZED_TELEMETRY"] = "False"
    os.environ["POSTHOG_DISABLED"] = "true"

    # CHROMA_PRODUCT_TELEMETRY_IMPL expects a fully-qualified class path.
    # Remove misconfigured values (e.g. "none") that can crash client init.
    if os.environ.get("CHROMA_PRODUCT_TELEMETRY_IMPL", "").strip().lower() == "none":
        os.environ.pop("CHROMA_PRODUCT_TELEMETRY_IMPL", None)

    # Chroma 0.5.23 + posthog>=6 can hit API signature mismatch:
    # capture() takes 1 positional argument but 3 were given.
    # Patch capture to a no-op to avoid log spam / side effects.
    try:
        import posthog  # type: ignore

        posthog.disabled = True

        def _noop_capture(*_args, **_kwargs):
            return None

        posthog.capture = _noop_capture  # type: ignore[attr-defined]
    except Exception:
        # Best-effort only; never block app startup.
        pass


_disable_chroma_telemetry()

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)
logger.info(
    "[chroma-telemetry] anonymized=%s chroma=%s chromadb=%s posthog_disabled=%s telemetry_impl=%s",
    os.environ.get("ANONYMIZED_TELEMETRY"),
    os.environ.get("CHROMA_TELEMETRY"),
    os.environ.get("CHROMADB_ANONYMIZED_TELEMETRY"),
    os.environ.get("POSTHOG_DISABLED"),
    os.environ.get("CHROMA_PRODUCT_TELEMETRY_IMPL", "<unset>"),
)

from app.core.config import settings
from app.services.embeddings import get_embeddings


@dataclass
class IngestResult:
    doc_id: str
    version: int
    chunk_count: int


class RAGService:
    def __init__(self) -> None:
        self._persist_path = Path(settings.chroma_persist_path).resolve()
        self._collection_name = "agent_knowledge"

    def _client(self) -> chromadb.ClientAPI:
        chroma_settings = ChromaSettings(anonymized_telemetry=False)
        if settings.chroma_url:
            return chromadb.HttpClient(host=settings.chroma_url, settings=chroma_settings)
        self._persist_path.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(self._persist_path), settings=chroma_settings)

    def _embedding_function(self) -> Embeddings:
        return get_embeddings()

    def _vector_store(self) -> Chroma:
        client = self._client()
        # Let LangChain manage collection creation with our remote embedding function.
        # Pre-creating collection here can trigger Chroma default embedding initialization
        # in some versions, which may probe/download HuggingFace models locally.
        return Chroma(
            client=client,
            collection_name=self._collection_name,
            embedding_function=self._embedding_function(),
        )

    def _split_text(self, text: str) -> list[str]:
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
        return splitter.split_text(text)

    def _extract_text_from_pdf(self, data: bytes) -> str:
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def _extract_text_from_docx(self, data: bytes) -> str:
        doc = DocxDocument(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)

    def _extract_text(self, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            return self._extract_text_from_pdf(data)
        if suffix in {".doc", ".docx"}:
            return self._extract_text_from_docx(data)
        return data.decode("utf-8", errors="ignore")

    def _build_documents(self, chunks: Iterable[str], doc_id: str, source_name: str) -> list[Document]:
        timestamp = datetime.utcnow().isoformat()
        return [
            Document(
                page_content=chunk,
                metadata={
                    "doc_id": doc_id,
                    "source": source_name,
                    "created_at": timestamp,
                },
            )
            for chunk in chunks
        ]

    async def ingest_upload(self, file: UploadFile, agent_id: str | None = None) -> IngestResult:
        data = await file.read()
        doc_id = f"doc-{uuid4().hex}"
        version = 1
        content = self._extract_text(file.filename or "uploaded", data)
        chunks = [chunk.strip() for chunk in self._split_text(content) if chunk.strip()]
        documents = self._build_documents(chunks, doc_id, file.filename or "uploaded")
        if agent_id:
            for doc in documents:
                doc.metadata["agent_id"] = agent_id
        for doc in documents:
            doc.metadata["version"] = version
            doc.metadata["status"] = "indexed"

        if not documents:
            return IngestResult(doc_id=doc_id, version=version, chunk_count=0)

        store = self._vector_store()
        store.add_documents(documents)
        return IngestResult(doc_id=doc_id, version=version, chunk_count=len(documents))

    def as_retriever(self, agent_id: str | None = None):
        store = self._vector_store()
        if agent_id:
            return store.as_retriever(search_kwargs={"k": 4, "filter": {"agent_id": agent_id}})
        return store.as_retriever(search_kwargs={"k": 4})

    def format_docs(self, docs: list[Document]) -> str:
        snippets = []
        for doc in docs:
            source = doc.metadata.get("source", "")
            doc_id = doc.metadata.get("doc_id", "")
            version = doc.metadata.get("version", "")
            snippets.append(f"[{doc_id}][v{version}][{source}] {doc.page_content}")
        return "\n\n".join(snippets)


def get_rag_service() -> RAGService:
    return RAGService()
