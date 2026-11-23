"""Indexação e recuperação documental (Chroma) para o RAG agêntico."""

from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "data" / "docs"
SOURCE_DOCS_DIR = ROOT / "data" / "source_docs"
CHROMA_DIR = ROOT / "chroma"
COLLECTION = "fridgechef_docs"

PDF_SOURCES = (
    ("cartilha_anvisa.pdf", (11, 23, 31, 32, 33, 34),
     "https://www.gov.br/anvisa/pt-br/centraisdeconteudo/publicacoes/alimentos/manuais-guias-e-orientacoes/cartilha-boas-praticas-para-servicos-de-alimentacao.pdf/"),
    ("hortalicas_mapa.pdf", (17,),
     "https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/857646/1/Cartilha-Hortalicas-nao-convencionais.pdf"),
)


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
    if docs_dir == DOCS_DIR:
        for filename, page_indexes, url in PDF_SOURCES:
            path = SOURCE_DOCS_DIR / filename
            reader = PdfReader(path)
            for page_index in page_indexes:
                content = reader.pages[page_index].extract_text() or ""
                if content.strip():
                    documents.append(
                        Document(
                            page_content=content,
                            metadata={
                                "source": filename,
                                "filename": filename,
                                "page": page_index + 1,
                                "url": url,
                            },
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
            meta["chunk_id"] = _chunk_id(f"{meta['source']}:{meta.get('page', '')}", i, part)
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
    current = {chunk.metadata["chunk_id"] for chunk in chunks}
    stale = existing - current
    if stale:
        store.delete(ids=list(stale))
        existing -= stale
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
        page = doc.metadata.get("page")
        location = f" página_pdf={page}" if page else ""
        blocks.append(f"[fonte={source}{location} trecho={idx}]\n{doc.page_content}")
    return "\n\n".join(blocks)


def retrieve(query: str, k: int = 4) -> tuple[str, list[dict]]:
    store = get_store()
    docs = store.similarity_search(query, k=k)
    payload = [
        {
            "content": d.page_content,
            "source": d.metadata.get("source", ""),
            "chunk_index": d.metadata.get("chunk_index"),
            "page": d.metadata.get("page"),
            "url": d.metadata.get("url"),
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
