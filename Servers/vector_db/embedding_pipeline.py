import os
from typing import List, Dict, Any
import openai
import httpx

# You may want to load your OpenAI API key from environment variables or a config file
openai.api_key = os.getenv("OPENAI_API_KEY")

# --- Vector DB Endpoint (update as needed) ---
VECTOR_DB_ENDPOINT = os.getenv("VECTOR_DB_ENDPOINT", "http://localhost:8080/api/v1/vectors/upsert")

# --- Chunking Function ---
def chunk_text(text: str, max_chunk_size: int = 500) -> List[str]:
    """
    Split text into chunks of approximately max_chunk_size characters, preserving sentence boundaries if possible.
    """
    import re
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# --- Embedding Function ---
def embed_texts(texts: List[str], model: str = "text-embedding-ada-002") -> List[List[float]]:
    """
    Generate embeddings for a list of texts using OpenAI's API.
    """
    response = openai.Embedding.create(input=texts, model=model)
    return [item["embedding"] for item in response["data"]]

# --- Store Embeddings (Production) ---
async def store_embeddings(chunks: List[str], embeddings: List[List[float]], metadata: List[Dict[str, Any]] = None):
    """
    Store the embeddings and their metadata in the vector DB via REST API.
    """
    payload = []
    for i, chunk in enumerate(chunks):
        payload.append({
            "text": chunk,
            "embedding": embeddings[i],
            "metadata": metadata[i] if metadata else {}
        })
    async with httpx.AsyncClient() as client:
        response = await client.post(VECTOR_DB_ENDPOINT, json={"vectors": payload})
        response.raise_for_status()
        return response.json()

# --- Main Pipeline Function ---
async def process_document(text: str, source: str = None, extra_metadata: Dict[str, Any] = None):
    """
    Chunk a document, generate embeddings, and store them with metadata.
    """
    chunks = chunk_text(text)
    embeddings = embed_texts(chunks)
    metadata = [{"source": source, **(extra_metadata or {})} for _ in chunks]
    await store_embeddings(chunks, embeddings, metadata)

# Example usage (remove or comment out in production):
# import asyncio
# if __name__ == "__main__":
#     sample_text = """Artificial intelligence (AI) is intelligence demonstrated by machines, in contrast to the natural intelligence displayed by humans and animals. Leading AI textbooks define the field as the study of \"intelligent agents\": any device that perceives its environment and takes actions that maximize its chance of successfully achieving its goals."""
#     asyncio.run(process_document(sample_text, source="Wikipedia:Artificial_intelligence")) 