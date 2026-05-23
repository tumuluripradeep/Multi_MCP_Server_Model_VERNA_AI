"""
HTTP-based MCP Agent for handling HTTP MCP servers.
"""
import json
import httpx
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


class HTTPMCPAgent:
    """Agent for handling HTTP-based MCP servers like Microsoft Docs."""
    
    def __init__(self, server_name: str, url: str, llm):
        """
        Initialize HTTP MCP agent.
        
        Args:
            server_name: Name of the MCP server
            url: URL endpoint for the HTTP MCP server
            llm: Language model instance for processing
        """
        self.server_name = server_name
        self.url = url
        self.llm = llm
        self.conversation_history: List[Dict[str, Any]] = []
        
    async def run(self, user_input: str) -> str:
        """
        Process user input with the HTTP MCP server.
        
        Args:
            user_input: User's input/query
            
        Returns:
            Response from the MCP server
        """
        try:
            if "microsoft" in self.server_name.lower() or "docs" in self.server_name.lower():
                return await self._query_microsoft_docs(user_input)
            else:
                return f"HTTP MCP server {self.server_name} not yet implemented"
        except Exception as e:
            logger.error(f"Error querying {self.server_name}: {e}")
            return f"Error querying {self.server_name}: {str(e)}"
    
    async def _query_microsoft_docs(self, query: str) -> str:
        """
        Query the Microsoft Docs MCP server.
        
        Args:
            query: Search query for Microsoft documentation
            
        Returns:
            Formatted response from Microsoft Docs
        """
        try:
            payload = self._create_microsoft_docs_payload(query)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    headers=self._get_request_headers()
                )
                
                if response.status_code == 200:
                    return await self._parse_microsoft_docs_response(response)
                else:
                    return await self._fallback_microsoft_docs_search(query)
                    
        except Exception as e:
            logger.error(f"Error querying Microsoft Docs: {e}")
            return await self._fallback_microsoft_docs_search(query)
    
    def _create_microsoft_docs_payload(self, query: str) -> Dict[str, Any]:
        """Create the JSON-RPC payload for Microsoft Docs MCP."""
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "microsoft_docs_search",
                "arguments": {
                    "question": query
                }
            }
        }
    
    def _get_request_headers(self) -> Dict[str, str]:
        """Get HTTP headers for MCP requests."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
    
    async def _parse_microsoft_docs_response(self, response: httpx.Response) -> str:
        """
        Parse response from Microsoft Docs MCP server.
        
        Args:
            response: HTTP response from the server
            
        Returns:
            Formatted response text
        """
        response_text = response.text
        
        # Extract JSON data from SSE format
        if "data: " in response_text:
            for line in response_text.split('\n'):
                if line.startswith('data: '):
                    json_data = line[6:]  # Remove "data: " prefix
                    try:
                        result = json.loads(json_data)
                        if 'result' in result and 'content' in result['result']:
                            return self._format_microsoft_docs_content(result['result']['content'])
                        else:
                            return f"Microsoft Docs search completed: {result}"
                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing response: {e}")
                        return f"Error parsing response: {e}. Raw response: {json_data[:200]}..."
        
        return f"Microsoft Docs search completed but returned unexpected format: {response_text[:200]}..."
    
    def _format_microsoft_docs_content(self, content: Any) -> str:
        """
        Format Microsoft Docs content for display.
        
        Args:
            content: Content from Microsoft Docs response
            
        Returns:
            Formatted content string
        """
        if isinstance(content, list) and len(content) > 0:
            docs_content = content[0].get('text', 'No content available')
            
            # Parse the JSON string within the text if it exists
            if docs_content.startswith('[{'):
                try:
                    docs_data = json.loads(docs_content)
                    return self._format_docs_data(docs_data)
                except json.JSONDecodeError:
                    return docs_content
            else:
                return docs_content
        elif isinstance(content, str):
            return content
        else:
            return str(content)
    
    def _format_docs_data(self, docs_data: List[Dict[str, Any]]) -> str:
        """
        Format parsed documentation data.
        
        Args:
            docs_data: List of documentation entries
            
        Returns:
            Formatted documentation string
        """
        formatted_response = "📚 **Microsoft Documentation Results:**\n\n"
        
        for i, doc in enumerate(docs_data[:3], 1):  # Show top 3 results
            title = doc.get('title', 'Untitled')
            content_text = doc.get('content', '')
            
            # Truncate long content
            if len(content_text) > 500:
                content_text = content_text[:500] + "..."
            
            url = doc.get('contentUrl', '')
            
            formatted_response += f"**{i}. {title}**\n"
            formatted_response += f"{content_text}\n"
            
            if url:
                formatted_response += f"🔗 [Read more]({url})\n\n"
            else:
                formatted_response += "\n"
        
        return formatted_response
    
    async def _fallback_microsoft_docs_search(self, query: str) -> str:
        """
        Fallback search using basic web search for Microsoft documentation.
        
        Args:
            query: Search query
            
        Returns:
            Fallback response with search URL
        """
        try:
            search_url = f"https://learn.microsoft.com/en-us/search/?terms={query.replace(' ', '%20')}"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(search_url)
                if response.status_code == 200:
                    return (
                        f"✅ Microsoft Docs search completed. For detailed information about '{query}', "
                        f"please visit: {search_url}\n\n"
                        f"Note: The Microsoft Docs MCP server is available but may require additional "
                        f"configuration. You can find comprehensive documentation on Microsoft Learn."
                    )
                else:
                    return (
                        f"❌ Unable to search Microsoft documentation at this time. "
                        f"You can manually search for '{query}' at https://learn.microsoft.com/"
                    )
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return (
                f"❌ Microsoft Docs search temporarily unavailable. "
                f"Please search manually at https://learn.microsoft.com/ for '{query}'"
            )
    
    def clear_conversation_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear() 