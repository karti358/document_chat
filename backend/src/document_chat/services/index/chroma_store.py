from __future__ import annotations

import threading
from pathlib import Path

import chromadb
import numpy as np
from PIL import Image
from typing import Literal
from chromadb.utils.embedding_functions import (
    DefaultEmbeddingFunction,
    OpenCLIPEmbeddingFunction,
)
from chromadb.utils.data_loaders import ImageLoader
from document_chat.services.parsers.kinds import (
    TEXT_KIND,
    IMAGE_KIND,
    Chunk,
)
from document_chat.config import config
from document_chat.logging import get_logger, preview

logger = get_logger("document_chat.chroma")


class ChromaStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(config.data_dir) / "chroma"
        self._path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._client = chromadb.PersistentClient(path=str(self._path))
        self._collection = self._client.get_or_create_collection(
            name="chunks",
            embedding_function=DefaultEmbeddingFunction(),
        )
        self._image_collection = None

    def _images(self):
        if self._image_collection is None:
            logger.info("chroma loading OpenCLIP image collection")
            self._image_collection = self._client.get_or_create_collection(
                name="images",
                embedding_function=OpenCLIPEmbeddingFunction(),
                data_loader=ImageLoader(),
            )
        return self._image_collection

    def upsert(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        images = [chunk for chunk in chunks if chunk.kind == IMAGE_KIND]
        texts = [chunk for chunk in chunks if chunk.kind != IMAGE_KIND]
        logger.info(
            "chroma upsert chunks=%s documents=%s kinds=%s",
            len(chunks),
            sorted({chunk.document_id for chunk in chunks}),
            sorted({chunk.kind for chunk in chunks}),
        )
        with self._lock:
            if images:
                loaded = []
                for image in images:
                    loaded.append(np.array(Image.open(image.data).convert("RGB")))
                self._images().upsert(
                    ids=[image.id for image in images],
                    images=loaded,
                    uris=[image.data for image in images],
                    metadatas=[_metadata(image) for image in images],
                )
            if texts:
                self._collection.upsert(
                    ids=[chunk.id for chunk in texts],
                    documents=[chunk.data for chunk in texts],
                    metadatas=[_metadata(chunk) for chunk in texts],
                )

    def delete_document(self, document_id: str) -> None:
        logger.info("chroma delete document_id=%s", document_id)
        with self._lock:
            try:
                self._collection.delete(where={"document_id": document_id})
                if self._image_collection is not None:
                    self._image_collection.delete(where={"document_id": document_id})
            except Exception:
                logger.exception("chroma delete failed document_id=%s", document_id)
                return

    def query(
        self,
        prompt: str,
        document_ids: list[str],
        limit: int = 2,
        kinds: set[Literal[TEXT_KIND, IMAGE_KIND]] | None = None,
    ) -> list:
        if not prompt.strip() or not document_ids:
            logger.info(
                "chroma query skipped prompt_empty=%s document_ids=%s",
                not prompt.strip(),
                document_ids,
            )
            return []
        document_filter = {"document_id": {"$in": document_ids}}
        filter = _text_filter(document_ids, kinds)
        with self._lock:
            try:
                want_text = kinds is None or bool(set(kinds) - {IMAGE_KIND})
                want_image = kinds is None or IMAGE_KIND in kinds
                result = {"ids": [[]], "documents": [[]], "metadatas": [[]]}
                if want_text:
                    result = self._collection.query(
                        query_texts=[prompt],
                        n_results=limit,
                        where=filter,
                    )
                image_result = None
                if want_image:
                    image_result = self._images().query(
                        query_texts=[prompt],
                        n_results=limit,
                        where=document_filter,
                        include=["metadatas", "uris"],
                    )
            except Exception:
                logger.exception("chroma query failed document_ids=%s", document_ids)
                return []
        hits = _hits(result)
        if image_result is not None:
            hits.extend(_image_hits(image_result))
        logger.info(
            "chroma query document_ids=%s hits=%s prompt=%s",
            document_ids,
            len(hits),
            preview(prompt, 200),
        )
        return hits

    def fetch(self, document_ids: list[str], kinds: set[str] | None = None) -> list[Chunk]:
        if not document_ids:
            return []
        with self._lock:
            try:
                result = self._collection.get(
                    where=_text_filter(document_ids, kinds),
                    include=["documents", "metadatas"],
                )
            except Exception:
                logger.exception("chroma fetch failed document_ids=%s", document_ids)
                return []
        return _chunks(result.get("ids") or [], result.get("documents") or [], result.get("metadatas") or [])


def _text_filter(document_ids: list[str], kinds: set[str] | None) -> dict:
    document_filter = {"document_id": {"$in": document_ids}}
    text_kinds = sorted(set(kinds) - {IMAGE_KIND}) if kinds else []
    if not text_kinds:
        return document_filter
    return {"$and": [document_filter, {"kind": {"$in": text_kinds}}]}


def _metadata(chunk: Chunk) -> dict:
    return {
        "document_id": chunk.document_id,
        "conversation_id": chunk.conversation_id or "",
        "filename": chunk.filename,
        "kind": chunk.kind,
        "location": chunk.location,
        "ocr_text": (chunk.ocr_text or "")[:800],
        "caption": (chunk.caption or "")[:500],
    }


def _hits(result: dict) -> list[Chunk]:
    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    return _chunks(ids, documents, metadatas)


def _image_hits(result: dict) -> list[Chunk]:
    ids = (result.get("ids") or [[]])[0]
    uris = (result.get("uris") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    return _chunks(ids, uris, metadatas)


def _chunks(ids: list, data: list, metadatas: list) -> list[Chunk]:
    return [
        Chunk(
            id=ids[index],
            document_id=metadatas[index]["document_id"],
            conversation_id=metadatas[index].get("conversation_id") or "",
            filename=metadatas[index]["filename"],
            kind=metadatas[index]["kind"],
            data=data[index],
            location=metadatas[index].get("location") or "",
            ocr_text=metadatas[index].get("ocr_text") or "",
            caption=metadatas[index].get("caption") or "",
        )
        for index in range(len(ids))
    ]


chroma_store = ChromaStore()
