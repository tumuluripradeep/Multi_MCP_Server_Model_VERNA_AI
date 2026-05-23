import json
import os
from typing import Optional, Dict, Any
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, SystemMessage
from mcp.server.fastmcp import FastMCP
import logging
import asyncio

# Import other providers
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    from langchain_mistralai import ChatMistralAI
    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False

logger = logging.getLogger(__name__)



def get_llm_from_config(
    config_path: str = "Servers/config/llm_config.json",
    streaming: Optional[bool] = None,
) -> Optional[BaseChatModel]:
    """
    Create an LLM instance from configuration file.
    
    Args:
        config_path: Path to the LLM configuration file
        
    Returns:
        BaseChatModel instance or None if error
    """
    try:
        if not os.path.exists(config_path):
            logger.error(f"LLM config file not found: {config_path}")
            return None
            
        with open(config_path) as f:
            config = json.load(f)

        if streaming is None:
            disable = os.getenv("DISABLE_STREAMING", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            se = os.getenv("STREAM_LLM", "").strip().lower()
            if disable or se in ("0", "false", "no"):
                streaming = False
            else:
                streaming = bool(
                    config.get("streaming", True) or se in ("1", "true", "yes")
                )
        else:
            streaming = bool(streaming)
            
        provider = config.get("provider", "").lower()
        model = config.get("model", "")
        
        if provider == "azureopenai":
            azure_config = config.get("azure", {})
            
            # Get credentials from environment variables, with config file fallbacks
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            
            # Try environment variable first, then fall back to config file
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
            if not deployment:
                deployment = azure_config.get("deployment", "")
            
            # Validate required credentials
            if not api_key or not endpoint or not deployment:
                logger.error("Azure OpenAI configuration incomplete. Missing credentials.")
                if not deployment:
                    logger.error("Please set AZURE_OPENAI_DEPLOYMENT environment variable or specify 'deployment' in azure config")
                else:
                    logger.error("Please set AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_DEPLOYMENT environment variables")
                return None
            
            req_timeout = config.get("request_timeout", 120)
            env_timeout = os.getenv("LLM_REQUEST_TIMEOUT", "").strip()
            if env_timeout:
                try:
                    req_timeout = float(env_timeout)
                except ValueError:
                    pass

            return AzureChatOpenAI(
                azure_deployment=deployment,
                api_version=azure_config.get("api_version", "2024-02-15-preview"),
                azure_endpoint=endpoint,
                api_key=api_key,
                temperature=config.get("temperature", 0.1),  # Lower temperature for faster, more focused responses
                max_tokens=config.get("max_tokens", 4000),  # Increased for complex responses
                max_retries=config.get("max_retries", 2),  # Reduced retries for faster failures
                request_timeout=req_timeout,
                streaming=streaming,
            )
        elif provider == "openai":
            openai_config = config.get("openai", {})
            
            # Get credentials from environment variables only
            api_key = os.getenv("OPENAI_API_KEY", "")
            
            if not api_key:
                logger.error("OpenAI API key not found. Please set OPENAI_API_KEY environment variable")
                return None
            
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000),
                max_retries=config.get("max_retries", 3)
            )
        elif provider == "gemini" and GOOGLE_AVAILABLE:
            gemini_config = config.get("gemini", {})
            
            # Get credentials from environment variables only
            api_key = os.getenv("GOOGLE_API_KEY", "")
            
            if not api_key:
                logger.error("Google API key not found. Please set GOOGLE_API_KEY environment variable")
                return None
            
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000)
            )
        elif provider == "claude" and ANTHROPIC_AVAILABLE:
            claude_config = config.get("claude", {})
            
            # Get credentials from environment variables only
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            
            if not api_key:
                logger.error("Anthropic API key not found. Please set ANTHROPIC_API_KEY environment variable")
                return None
            
            return ChatAnthropic(
                model=model,
                anthropic_api_key=api_key,
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000)
            )
        elif provider == "mistral" and MISTRAL_AVAILABLE:
            mistral_config = config.get("mistral", {})
            
            # Get credentials from environment variables only
            api_key = os.getenv("MISTRAL_API_KEY", "")
            
            if not api_key:
                logger.error("Mistral API key not found. Please set MISTRAL_API_KEY environment variable")
                return None
            
            return ChatMistralAI(
                model=model,
                mistral_api_key=api_key,
                temperature=config.get("temperature", 0.2),
                max_tokens=config.get("max_tokens", 1000)
            )
        else:
            logger.error(f"Unknown or unavailable provider: {provider}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating LLM from config: {e}")
        return None


class LLMEnhancedMCP:
    """
    Base class for LLM-enhanced MCP servers.
    Provides common LLM functionality that can be inherited by specific MCP servers.
    """
    
    def __init__(self, server_name: str, config_path: str = "Servers/config/llm_config.json"):
        """
        Initialize LLM-enhanced MCP server.
        
        Args:
            server_name: Name of the MCP server
            config_path: Path to LLM configuration file
        """
        self.server_name = server_name
        self.mcp = FastMCP(server_name)
        self.llm = get_llm_from_config(config_path)
        self.connection_error_logged = False
        
        if not self.llm:
            logger.warning(f"LLM not available for {server_name}")
    
    def is_llm_available(self) -> bool:
        """Check if LLM is available for use."""
        return self.llm is not None
    
    async def generate_response(self, prompt: str, system_message: str = None, timeout: int = 10) -> str:
        """
        Generate a response using the LLM with timeout protection.
        
        Args:
            prompt: User prompt/query
            system_message: Optional system message to guide the LLM
            timeout: Timeout in seconds for the LLM call (default: 10)
            
        Returns:
            Generated response or error message
        """
        if not self.llm:
            return "LLM not available. Please configure your API credentials in environment variables or llm_config.json file."
        
        try:
            messages = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # Add timeout protection to LLM call
            response = await asyncio.wait_for(
                self.llm.ainvoke(messages), 
                timeout=timeout
            )
            return response.content
            
        except asyncio.TimeoutError:
            logger.error(f"LLM request timed out after {timeout} seconds for {self.server_name}")
            return f"⏱️ LLM request timed out after {timeout} seconds. Please try again with a simpler request or check your network connection."
            
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "unauthorized" in error_msg or "api key" in error_msg:
                if not self.connection_error_logged:
                    logger.error(f"Authentication error for {self.server_name}: {e}")
                    self.connection_error_logged = True
                return "Authentication error. Please check your API credentials and try again."
            elif "connection" in error_msg or "network" in error_msg or "timeout" in error_msg:
                if not self.connection_error_logged:
                    logger.error(f"Connection error for {self.server_name}: {e}")
                    self.connection_error_logged = True
                return "Connection error. Please check your internet connection and try again."
            else:
                logger.error(f"Error generating LLM response: {e}")
                return f"Error generating response: {str(e)}"
    
    async def analyze_with_llm(self, data: str, analysis_type: str = "general") -> str:
        """
        Analyze data using LLM with specific analysis prompts.
        
        Args:
            data: Data to analyze
            analysis_type: Type of analysis (general, technical, business, etc.)
            
        Returns:
            Analysis results
        """
        if not self.llm:
            return "LLM not available for analysis. Please configure your API credentials."
        
        system_prompts = {
            "general": "You are an expert analyst. Provide clear, actionable insights.",
            "technical": "You are a technical expert. Focus on technical details and implications.",
            "business": "You are a business analyst. Focus on business impact and opportunities.",
            "weather": "You are a weather expert. Provide detailed weather analysis and recommendations.",
            "content": "You are a content analyst. Analyze structure, quality, and key insights.",
            "hr": "You are an HR expert. Focus on employee relations and organizational insights.",
            "financial": "You are a financial analyst. Focus on financial implications and recommendations."
        }
        
        system_message = system_prompts.get(analysis_type, system_prompts["general"])
        prompt = f"Analyze the following data and provide insights:\n\n{data}"
        
        # Use longer timeout for complex analysis
        timeout = 45 if analysis_type == "content" else 30
        return await self.generate_response(prompt, system_message, timeout=timeout)
    
    async def summarize_with_llm(self, content: str, max_length: int = 200) -> str:
        """
        Summarize content using LLM.
        
        Args:
            content: Content to summarize
            max_length: Maximum length of summary
            
        Returns:
            Summary of the content
        """
        if not self.llm:
            return "LLM not available for summarization. Please configure your API credentials."
        
        system_message = f"You are an expert summarizer. Create a concise summary of the content in approximately {max_length} words or less. Focus on the main points and key insights."
        prompt = f"Summarize the following content:\n\n{content}"
        
        # Use longer timeout for content summarization
        timeout = 40 if len(content) > 5000 else 30
        return await self.generate_response(prompt, system_message, timeout=timeout)
    
    async def explain_with_llm(self, data: str, context: str = "") -> str:
        """
        Explain data or concepts using LLM.
        
        Args:
            data: Data or concept to explain
            context: Additional context for explanation
            
        Returns:
            Detailed explanation
        """
        if not self.llm:
            return "LLM not available for explanations. Please configure your API credentials."
        
        system_message = "You are an expert explainer. Provide clear, detailed explanations that are easy to understand."
        prompt = f"Explain the following data or concept:\n\n{data}"
        if context:
            prompt += f"\n\nContext: {context}"
        
        return await self.generate_response(prompt, system_message, timeout=30)
    
    def get_mcp_server(self) -> FastMCP:
        """Get the underlying MCP server instance."""
        return self.mcp

def create_llm_enhanced_server(server_name: str, config_path: str = "Servers/config/llm_config.json") -> LLMEnhancedMCP:
    """
    Create an LLM-enhanced MCP server instance.
    
    Args:
        server_name: Name of the MCP server
        config_path: Path to LLM configuration file
        
    Returns:
        LLMEnhancedMCP instance
    """
    return LLMEnhancedMCP(server_name, config_path)