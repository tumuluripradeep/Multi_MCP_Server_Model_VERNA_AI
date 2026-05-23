# =============================
# Imports & Setup
# =============================
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP
import os
from dotenv import load_dotenv
from mcp_use import MCPClient

# =============================
# Load Environment Variables
# =============================
load_dotenv()

# =============================
# MCP Server Initialization
# =============================
mcp = FastMCP("marketing_system")

# =============================
# Constants
# =============================
# (Add your marketing system constants here)

# =============================
# Utility Functions
# =============================
# (Add your marketing system utility functions here)

# =============================
# MCP Tool Functions
# =============================
@mcp.tool()
async def marketing_example_marketing_tool(param: str) -> str:
    """
    Example tool for the marketing system MCP server.
    Args:
        param (str): Example parameter.
    Returns:
        str: Example response.
    """
    return f"Marketing system tool received: {param}"

@mcp.prompt("marketing_system_prompt")
def marketing_system_prompt() -> str:
    """
    Example prompt template for the marketing system MCP server.
    """
    return "This is a placeholder prompt for the marketing system."

@mcp.tool()
async def marketing_marketing_with_vector_search(query: str, locale: str = "en-US") -> str:
    """
    Example of A2A: Marketing agent calls the vector search agent for relevant content.
    Args:
        query (str): The search query
        locale (str): The language locale
    Returns:
        str: Summary of relevant content from vector search
    """
    # Assume the vector search MCP server is named 'vector_search'
    client = MCPClient(config={"mcpServers": {"vector_search": {"url": "http://localhost:8000"}}})
    # Call the hybrid search tool
    results = await client.run("vector_search", "vector_get_relevant_content_hybrid", {"query": query, "locale": locale})
    if not results:
        return "No relevant content found."
    # Summarize the results for demonstration
    summary = "\n".join([f"Source: {item.get('source', 'unknown')} | Text: {item.get('text', '')[:100]}..." for item in results])
    return f"Relevant content from vector search:\n{summary}" 