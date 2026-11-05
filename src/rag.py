"""Indexação e recuperação documental (Chroma) para o RAG agêntico."""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "docs"
CHROMA_DIR = ROOT / "chroma"
COLLECTION = "fridgechef_docs"


def _chunk_id(source: str, index: int, content: str) -> str:
    digest = hashlib.sha1(f"{source}:{index}:{content[:80]}".encode()).hexdigest()[:16]
    return f"{Path(source).stem}-{index}-{digest}"


def load_documents(docs_dir: Path | None = None) -> list[Document]:
    docs_dir = docs_dir or DOCS_DIR
    documents: list[Document] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        documents.append(
            Document(
                page_content=text,
                metadata={"source": path.name, "filename": path.name},
            )
        )
    return documents


def make_chunks(
    documents: list[Document] | None = None,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[Document]:
    documents = documents if documents is not None else load_documents()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks: list[Document] = []
    for doc in documents:
        parts = splitter.split_text(doc.page_content)
        for i, part in enumerate(parts):
            meta = dict(doc.metadata)
            meta["chunk_id"] = _chunk_id(meta["source"], i, part)
            meta["chunk_index"] = i
            chunks.append(Document(page_content=part, metadata=meta))
    return chunks


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model="text-embedding-3-small")


def build_store(
    persist_directory: Path | None = None,
    collection_name: str = COLLECTION,
) -> Chroma:
    persist_directory = persist_directory or CHROMA_DIR
    persist_directory.mkdir(parents=True, exist_ok=True)
    embeddings = get_embeddings()
    store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=str(persist_directory),
        collection_metadata={"hnsw:space": "cosine"},
    )
    chunks = make_chunks()
    existing = set(store.get()["ids"] or [])
    to_add_docs: list[Document] = []
    to_add_ids: list[str] = []
    for chunk in chunks:
        cid = chunk.metadata["chunk_id"]
        if cid not in existing:
            to_add_docs.append(chunk)
            to_add_ids.append(cid)
    if to_add_docs:
        store.add_documents(documents=to_add_docs, ids=to_add_ids)
    return store


def get_store(
    persist_directory: Path | None = None,
    collection_name: str = COLLECTION,
) -> Chroma:
    persist_directory = persist_directory or CHROMA_DIR
    if not persist_directory.exists() or not any(persist_directory.iterdir()):
        return build_store(persist_directory, collection_name)
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(persist_directory),
        collection_metadata={"hnsw:space": "cosine"},
    )


def format_docs(documents: list[Document]) -> str:
    if not documents:
        return "(nenhum trecho recuperado)"
    blocks = []
    for doc in documents:
        source = doc.metadata.get("source", "desconhecido")
        idx = doc.metadata.get("chunk_index", "?")
        blocks.append(f"[fonte={source} trecho={idx}]\n{doc.page_content}")
    return "\n\n".join(blocks)


def retrieve(query: str, k: int = 4) -> tuple[str, list[dict]]:
    store = get_store()
    docs = store.similarity_search(query, k=k)
    payload = [
        {
            "content": d.page_content,
            "source": d.metadata.get("source", ""),
            "chunk_index": d.metadata.get("chunk_index"),
        }
        for d in docs
    ]
    return format_docs(docs), payload


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    store = build_store()
    count = len(store.get()["ids"] or [])
    print(f"Índice pronto em {CHROMA_DIR} — {count} chunks.")
