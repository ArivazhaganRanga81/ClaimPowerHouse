from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import (
    PolicyChunk,
    PolicyDocument,
    PolicyVersion,
    PublicationState,
    RagIndexVersion,
)
from ..schemas import PolicyEvidence

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9.]+")
COLLECTION_NAME = "policy_chunks_lexical_1"
INDEX_VERSION = "rag-lexical-1"
CHUNKING_VERSION = "heading-220-v1"


def _tokens(text: str) -> Counter[str]:
    return Counter(token.lower() for token in TOKEN_PATTERN.findall(text))


def _bm25_score(
    query: str,
    text: str,
    *,
    document_frequency: dict[str, int],
    document_count: int,
    average_length: float,
) -> float:
    """Small dependency-free BM25 implementation for offline policy retrieval."""
    query_tokens = _tokens(query)
    text_tokens = _tokens(text)
    if not query_tokens or not text_tokens:
        return 0.0
    k1 = 1.2
    b = 0.75
    length = sum(text_tokens.values())
    score = 0.0
    for token, query_frequency in query_tokens.items():
        frequency = text_tokens.get(token, 0)
        if not frequency:
            continue
        df = document_frequency.get(token, 0)
        idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
        saturation = (frequency * (k1 + 1)) / (
            frequency + k1 * (1 - b + b * length / max(average_length, 1.0))
        )
        score += idf * saturation * min(query_frequency, 2)
    return score


def chunk_policy(
    content: str, *, target_tokens: int = 200, overlap: int = 35
) -> list[tuple[str, str]]:
    """Create heading-aware chunks without crossing markdown section boundaries."""
    sections: list[tuple[str, list[str]]] = []
    heading = "Policy"
    body: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if body:
                sections.append((heading, body))
            heading = stripped.lstrip("#").strip() or "Policy"
            body = []
        elif stripped:
            body.append(stripped)
    if body:
        sections.append((heading, body))
    if not sections and content.strip():
        sections = [("Policy", [content.strip()])]

    chunks: list[tuple[str, str]] = []
    for heading_path, lines in sections:
        words = " ".join(lines).split()
        start = 0
        while start < len(words):
            end = min(start + target_tokens, len(words))
            chunks.append((heading_path, " ".join(words[start:end])))
            if end == len(words):
                break
            start = max(start + 1, end - overlap)
    return chunks


def search_policies(
    session: Session,
    *,
    query: str,
    payer_code: str,
    plan_code: str,
    service_date: date,
    limit: int = 5,
) -> list[PolicyEvidence]:
    statement = (
        select(PolicyChunk, PolicyVersion, PolicyDocument)
        .join(PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.id)
        .join(PolicyDocument, PolicyVersion.policy_id == PolicyDocument.id)
        .where(
            PolicyDocument.payer_code == payer_code,
            PolicyDocument.plan_code == plan_code,
            PolicyVersion.state.in_([PublicationState.ACTIVE, PublicationState.APPROVED]),
            PolicyVersion.effective_from <= service_date,
            (PolicyVersion.effective_to.is_(None) | (PolicyVersion.effective_to >= service_date)),
        )
    )
    rows = session.execute(statement).all()
    document_frequency: Counter[str] = Counter()
    lengths: list[int] = []
    for chunk, _, _ in rows:
        tokens = _tokens(chunk.text)
        document_frequency.update(tokens.keys())
        lengths.append(sum(tokens.values()))
    average_length = sum(lengths) / len(lengths) if lengths else 0.0
    ranked = sorted(
        [
            (
                _bm25_score(
                    query,
                    chunk.text,
                    document_frequency=document_frequency,
                    document_count=len(rows),
                    average_length=average_length,
                ),
                chunk,
                version,
                document
            )
            for chunk, version, document in rows
        ],
        key=lambda row: row[0],
        reverse=True,
    )
    ranked = [row for row in ranked if row[0] > 0]
    return [
        PolicyEvidence(
            chunk_id=chunk.id,
            policy_code=document.policy_code,
            policy_version=version.version,
            title=document.title,
            heading_path=chunk.heading_path,
            excerpt=chunk.text,
            effective_from=version.effective_from,
            effective_to=version.effective_to,
            score=round(score, 6),
            source_uri=document.source_uri,
        )
        for score, chunk, version, document in ranked[:limit]
    ]


def replace_policy_chunks(session: Session, version: PolicyVersion) -> list[PolicyChunk]:
    for existing in list(version.chunks):
        session.delete(existing)
    session.flush()
    chunks: list[PolicyChunk] = []
    for ordinal, (heading, text) in enumerate(chunk_policy(version.content), 1):
        digest = hashlib.sha256(text.encode()).hexdigest()
        chunk = PolicyChunk(
            policy_version_id=version.id,
            ordinal=ordinal,
            heading_path=heading,
            text=text,
            content_hash=digest,
        )
        session.add(chunk)
        chunks.append(chunk)
    session.flush()
    for chunk in chunks:
        chunk.chroma_id = chunk.id
    return chunks


def rebuild_lexical_index(session: Session) -> dict[str, Any]:
    """Refresh the dependency-free BM25 index metadata.

    Retrieval is calculated directly from approved SQLite chunks, so rebuilding
    never downloads a model or requires network access.
    """
    rows = session.execute(
        select(PolicyChunk, PolicyVersion, PolicyDocument)
        .join(PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.id)
        .join(PolicyDocument, PolicyVersion.policy_id == PolicyDocument.id)
        .where(PolicyVersion.state.in_([PublicationState.ACTIVE, PublicationState.APPROVED]))
    ).all()
    source_hash = hashlib.sha256(
        "|".join(sorted(chunk.content_hash for chunk, _, _ in rows)).encode()
    ).hexdigest()
    index = session.scalar(select(RagIndexVersion).where(RagIndexVersion.version == INDEX_VERSION))
    if index is None:
        index = RagIndexVersion(
            version=INDEX_VERSION,
            collection_name=COLLECTION_NAME,
            embedding_model="none (bm25)",
            chunking_version=CHUNKING_VERSION,
            source_set_hash=source_hash,
        )
        session.add(index)
    index.status = "BUILDING"
    index.error_message = None
    index.source_set_hash = source_hash
    session.commit()
    try:
        session.execute(update(RagIndexVersion).values(active=False))
        index.active = True
        index.status = "READY"
        index.chunk_count = len(rows)
        session.commit()
        return {
            "status": "ready",
            "index_version": INDEX_VERSION,
            "collection": COLLECTION_NAME,
            "chunks": len(rows),
            "embedding_model": "none (bm25)",
            "source_set_hash": source_hash,
        }
    except Exception as exc:
        index.status = "FAILED"
        index.error_message = str(exc)[:2000]
        session.commit()
        raise


# Backward-compatible name for existing CLI/API callers.
rebuild_chroma = rebuild_lexical_index
