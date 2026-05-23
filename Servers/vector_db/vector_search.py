from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import os

# Initialize the MCP server
mcp = FastMCP("vector_search")

# Constants
VECTOR_SEARCH_URL = "https://aria-llm-stage.adobe.io/api/v1/agent/search"
PROBLEM_STATEMENT_URL = "https://aria-llm-dev.adobe.io/api/v1/llm/generate"
KEYWORD_SEARCH_ENDPOINT = os.getenv("KEYWORD_SEARCH_ENDPOINT", "http://localhost:8080/api/v1/keyword_search")

async def get_problem_statement(text: str, locale: str = "en-US") -> str | None:
    """
    Get the problem statement from the case description.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model_params": {
            "key": "AZURE_TURBO_GPT4_0_MINI",
            "items": [
                {"name": "temperature", "value": 0},
                {"name": "max_tokens", "value": 4000}
            ]
        },
        "locale": locale,
        "prompt_params": {
            "key": "PROBLEM_STATEMENT",
            "items": [
                {
                    "name": "text",
                    "value": text
                }
            ]
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(PROBLEM_STATEMENT_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("response")
        except httpx.HTTPStatusError:
            return None

async def search_vector_db(query: str, locale: str = "en-US", top_k: int = 5) -> list[dict[str, Any]] | None:
    """
    Search the vector database for relevant content.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "query_text": query,
        "top_k": top_k,
        "query_type": 2,
        "metadata": {
            "locale": locale
        }
    }
    
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(VECTOR_SEARCH_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError:
            return None

async def keyword_search(query: str, locale: str = "en-US", top_k: int = 5) -> list[dict[str, Any]]:
    """
    Keyword-based search using a REST API endpoint (template).
    """
    payload = {
        "query_text": query,
        "top_k": top_k,
        "metadata": {"locale": locale}
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(KEYWORD_SEARCH_ENDPOINT, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except httpx.HTTPStatusError:
            return []

async def hybrid_search(query: str, locale: str = "en-US", top_k: int = 5) -> list[dict[str, Any]]:
    """
    Perform both vector and keyword search, merge results, and remove duplicates.
    """
    vector_results = await search_vector_db(query, locale, top_k)
    keyword_results = await keyword_search(query, locale, top_k)
    # Merge results, prioritizing vector results
    seen = set()
    merged = []
    for item in (vector_results or []) + (keyword_results or []):
        key = item.get('id') or item.get('text')
        if key and key not in seen:
            merged.append(item)
            seen.add(key)
    return merged[:top_k]

@mcp.tool()
async def vector_get_relevant_content(query: str, case_data: dict[str, Any] | None = None, locale: str = "en-US") -> str:
    """
    Get relevant content based on the query. If case_data is provided, it will first
    extract a problem statement from it.
    
    Args:
        query (str): The search query or case description
        case_data (dict[str, Any] | None): Optional case data for problem statement extraction
        locale (str): The language locale (default: en-US)
        
    Returns:
        str: Formatted relevant content or error message
    """
    if case_data:
        # For case-related queries, first get the problem statement
        problem_statement = await get_problem_statement(str(case_data), locale)
        if not problem_statement:
            return None
        search_query = problem_statement
    else:
        # For general queries, use the query directly
        search_query = query
    
    # Search the vector database
    results = await search_vector_db(search_query, locale)
    # Add source attribution if available
    if results:
        for item in results:
            # Ensure 'source' is present in each result (customize as per your vector DB schema)
            if 'source' not in item:
                item['source'] = item.get('metadata', {}).get('source', 'unknown')
        
        # Format results as string
        formatted_results = []
        for item in results:
            text = item.get('text', 'N/A')
            source = item.get('source', 'unknown')
            score = item.get('score', 0.0)
            formatted_results.append(f"Source: {source}\nScore: {score:.2f}\nContent: {text[:200]}...\n")
        
        return f"Found {len(results)} relevant content items:\n\n" + "\n".join(formatted_results)
    else:
        return f"No relevant content found for query: {query}"

@mcp.tool()
async def vector_get_relevant_content_hybrid(query: str, locale: str = "en-US", top_k: int = 5) -> str:
    """
    Get relevant content using hybrid (vector + keyword) search.
    This tool is intended for A2A (Agent-to-Agent) calls and can be invoked by other agents for richer workflows.
    Args:
        query (str): The search query
        locale (str): The language locale (default: en-US)
        top_k (int): Number of top results to return
    Returns:
        str: Formatted relevant content or error message
    """
    results = await hybrid_search(query, locale, top_k)
    # Add source attribution if available
    if results:
        for item in results:
            if 'source' not in item:
                item['source'] = item.get('metadata', {}).get('source', 'unknown')
        
        # Format results as string
        formatted_results = []
        for item in results:
            text = item.get('text', 'N/A')
            source = item.get('source', 'unknown')
            score = item.get('score', 0.0)
            formatted_results.append(f"Source: {source}\nScore: {score:.2f}\nContent: {text[:200]}...\n")
        
        return f"Found {len(results)} relevant content items (hybrid search):\n\n" + "\n".join(formatted_results)
    else:
        return f"No relevant content found for query: {query}"
