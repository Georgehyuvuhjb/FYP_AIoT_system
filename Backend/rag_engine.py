"""
rag_engine.py
Lightweight Vector-based Retrieval-Augmented Generation (RAG) engine.
Chunks the system manual, computes TF-IDF vectors, and retrieves the
most relevant sections for a given user query using cosine similarity.
"""

import os
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Path to the system manual
MANUAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system_manual.md")

# Global state (lazy initialized)
_chunks = None
_vectorizer = None
_chunk_vectors = None


def _load_and_chunk_manual(chunk_separator="---"):
    """
    Load the system manual and split it into semantic chunks.

    Each chunk is a section separated by '---' (horizontal rule) in Markdown.
    Sub-chunks are created by splitting on '###' headings for finer granularity.

    Returns:
        list[str]: List of text chunks.
    """
    if not os.path.exists(MANUAL_PATH):
        print(f"Warning: System manual not found at {MANUAL_PATH}")
        return ["System manual not available."]

    with open(MANUAL_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Primary split: by '---' horizontal rules (major sections)
    major_sections = re.split(r"\n---\n", content)

    chunks = []
    for section in major_sections:
        section = section.strip()
        if not section:
            continue

        # Secondary split: by '### ' sub-headings for finer granularity
        sub_parts = re.split(r"(?=^### )", section, flags=re.MULTILINE)

        for part in sub_parts:
            part = part.strip()
            if len(part) > 50:  # Skip very short fragments
                chunks.append(part)

    if not chunks:
        chunks = [content]  # Fallback: use entire document as one chunk

    print(f"RAG Engine: Loaded {len(chunks)} chunks from system manual.")
    return chunks


def _build_index():
    """
    Build the TF-IDF vector index from manual chunks.
    Called once on first query (lazy initialization).
    """
    global _chunks, _vectorizer, _chunk_vectors

    _chunks = _load_and_chunk_manual()

    # Build TF-IDF vectorizer with bigrams for better matching
    _vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=5000,
    )
    _chunk_vectors = _vectorizer.fit_transform(_chunks)

    print(f"RAG Engine: TF-IDF index built. Vocabulary size: {len(_vectorizer.vocabulary_)}")


def retrieve(query, top_k=3):
    """
    Retrieve the top-k most relevant chunks for a given query.

    Uses TF-IDF vectorization and cosine similarity to rank chunks.

    Args:
        query (str): The user's question.
        top_k (int): Number of chunks to return.

    Returns:
        list[dict]: List of {text, score} for the top-k chunks.
    """
    global _chunks, _vectorizer, _chunk_vectors

    # Lazy initialization
    if _chunks is None:
        _build_index()

    # Vectorize the query
    query_vector = _vectorizer.transform([query])

    # Compute cosine similarity between query and all chunks
    similarities = cosine_similarity(query_vector, _chunk_vectors).flatten()

    # Get top-k indices sorted by score (descending)
    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(similarities[idx])
        if score > 0.0:  # Only include chunks with some relevance
            results.append({
                "text": _chunks[idx],
                "score": round(score, 4),
            })

    if not results:
        # If no relevant chunk found, return a fallback message
        results.append({
            "text": "No specific information found in the manual for this query.",
            "score": 0.0,
        })

    print(f"RAG Engine: Query '{query[:50]}...' -> {len(results)} relevant chunks (top score: {results[0]['score']})")
    return results


def get_context_for_query(query, top_k=3):
    """
    Get a formatted context string from retrieved chunks for LLM injection.

    Args:
        query (str): The user's question.
        top_k (int): Number of chunks to use.

    Returns:
        str: Joined context text from the most relevant chunks.
    """
    results = retrieve(query, top_k=top_k)
    context_parts = [r["text"] for r in results]
    return "\n\n---\n\n".join(context_parts)
