"""
Main server manager for handling MCP server interactions using MultiServerMCPClient.
"""
import asyncio
import sys
import time
from typing import Dict, Any, Optional, Union, List
import logging
import json
import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fix Windows asyncio subprocess issue
if sys.platform == "win32":
    # Set Windows-specific event loop policy
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from pydantic import BaseModel, Field

from .config_manager import ConfigManager
from .conversation_manager import ConversationManager
from .http_mcp_agent import HTTPMCPAgent
from Servers.llm_factory import get_llm_from_config
from .auth_manager import auth_manager
from .oauth_manager import oauth_manager

# Enhanced logging setup
logger = logging.getLogger(__name__)

# Add detailed logging for sample prompts testing
SAMPLE_PROMPTS_LOG = logging.getLogger(f"{__name__}.sample_prompts")
PERFORMANCE_LOG = logging.getLogger(f"{__name__}.performance")
TOOL_ROUTING_LOG = logging.getLogger(f"{__name__}.tool_routing")
AUTH_LOG = logging.getLogger(f"{__name__}.auth")


class ServerManager:
    """
    Simplified server manager using the working MultiServerMCPClient pattern.
    Based on the successful client.py and simple_demo.py implementations.
    """

    # Streamlit/UI action keys -> MCP tool names (FastMCP registers function names)
    _UI_ACTION_TO_TOOL: Dict[str, Dict[str, str]] = {
        "youtube": {
            "search": "youtube_search_youtube",
            "get_transcript": "youtube_get_video_transcript",
            "transcript": "youtube_get_video_transcript",
            "get_comments": "youtube_get_video_comments",
            "comments": "youtube_get_video_comments",
            "analyze_video": "youtube_analyze_video_content",
            "parse_search_intent": "youtube_parse_search_intent",
            "present_search_results": "youtube_present_search_results",
        },
        "weather": {
            "get_forecast": "weather_get_forecast",
            "get_alerts": "weather_get_alerts",
        },
    }
    
    def __init__(self, config_dir: str = "Servers/config"):
        """
        Initialize the server manager.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_manager = ConfigManager(config_dir)
        self.conversation_manager = ConversationManager()
        self.auth_manager = auth_manager
        self.oauth_manager = oauth_manager
        
        # MultiServerMCPClient for handling MCP connections
        self.mcp_client: Optional[MultiServerMCPClient] = None
        self.llm = None
        self.agent = None
        self.available_tools: List = []
        
        # HTTP-based agents (like Microsoft Docs)
        self.http_agents: Dict[str, HTTPMCPAgent] = {}
        
        # Authentication support
        self.authenticated_servers: Dict[str, bool] = {}
        
        # Performance optimization: Cache tools and pre-initialize agent
        self._tools_cached = False
        self._agent_initialized = False
        self._cached_tools: List = []
        
        # Performance metrics tracking
        self._request_count = 0
        self._total_response_time = 0.0
        self._cache_hits = 0
        self._cache_timestamp = None  # Track when cache was created
        
        # Cache expiration (cache expires after 1 hour by default)
        self._cache_expiry_seconds = 3600

        # Agent invoke timeout (multi-tool Adobe-style prompts need >45s)
        try:
            self._agent_invoke_timeout = float(os.getenv("AGENT_INVOKE_TIMEOUT", "180"))
        except ValueError:
            self._agent_invoke_timeout = 180.0
        try:
            self._parallel_task_timeout = float(
                os.getenv("PARALLEL_TASK_TIMEOUT", str(self._agent_invoke_timeout))
            )
        except ValueError:
            self._parallel_task_timeout = self._agent_invoke_timeout

    @staticmethod
    def streaming_enabled() -> bool:
        """True unless explicitly disabled via env."""
        if os.getenv("DISABLE_STREAMING", "").strip().lower() in ("1", "true", "yes"):
            return False
        if os.getenv("STREAM_LLM", "").strip().lower() in ("0", "false", "no"):
            return False
        return True

    async def _ensure_streaming_llm_and_agent(self) -> bool:
        """Use a streaming-capable LLM and ensure the react agent is ready."""
        if self.streaming_enabled():
            if not self.llm or not getattr(self.llm, "streaming", False):
                logger.info("🌊 Enabling streaming LLM for agent")
                self.llm = get_llm_from_config(streaming=True)
                # Only reset agent if LLM mode changed; avoid tearing down mid-request.
                if self.agent:
                    self._agent_initialized = False
                    self.agent = None
        if not (self._tools_cached and self._cached_tools):
            await self.get_available_tools(force_refresh=True)
        if self.agent and self._agent_initialized:
            return True
        return await self._setup_agent(force_refresh=False)

    async def collect_stream_response(
        self,
        user_input: str,
        channel_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ) -> str:
        """Consume process_request_stream and return the full assistant text."""
        parts: List[str] = []
        async for event in self.process_request_stream(
            user_input, channel_id=channel_id, thread_ts=thread_ts
        ):
            event_type = event.get("type")
            if event_type == "token":
                chunk = event.get("content", "")
                if chunk:
                    parts.append(chunk)
            elif event_type == "error":
                return event.get("content", "Error processing request.")
            elif event_type == "done":
                return event.get("content") or "".join(parts)
        return "".join(parts)

    def initialize(self, llm=None) -> None:
        """
        Initialize the server manager with LLM from factory and set up MCP connections.
        
        Args:
            llm: Optional LLM instance, if not provided will use llm_factory
        """
        init_start_time = time.time()
        logger.info("🚀 Starting ServerManager initialization...")
        
        # Use llm_factory to create LLM
        if llm is None:
            logger.info("🧠 Creating LLM from factory configuration...")
            self.llm = get_llm_from_config(
                streaming=True if self.streaming_enabled() else False
            )
            if not self.llm:
                logger.error("❌ Failed to create LLM from factory")
                return
            logger.info(f"✅ LLM created successfully: {type(self.llm).__name__}")
        else:
            self.llm = llm
            logger.info(f"✅ LLM provided externally: {type(self.llm).__name__}")
        
        # Load server configurations
        logger.info("📋 Loading server configurations...")
        servers = self.config_manager.load_server_configs()
        if not servers:
            logger.warning("⚠️ No server configurations found")
            return
        
        logger.info(f"📊 Loaded {len(servers)} server configurations:")
        for server_name, config in servers.items():
            transport = config.get('transport', 'stdio')
            logger.info(f"  🔧 {server_name}: {transport} transport")
        
        # Check authentication for servers
        logger.info("🔐 Checking server authentication...")
        self._check_server_authentication(servers)
        
        # Setup MCP client with server configurations
        logger.info("📡 Setting up MCP client connections...")
        self._setup_mcp_client(servers)
        
        # Clear any existing cache to ensure fresh start
        self._clear_cache_internal()
        logger.info("🧹 Cleared any existing cache for fresh initialization")
        
        init_time = time.time() - init_start_time
        logger.info(f"🎉 ServerManager initialization completed in {init_time:.2f}s with {len(servers)} server configurations")
        logger.info("💡 Agent will be created with fresh tools on first request")

    def _check_server_authentication(self, servers: Dict[str, Any]) -> None:
        """Check authentication status for all servers with detailed logging"""
        AUTH_LOG.info("🔐 Starting authentication validation for all servers...")
        
        auth_summary = {
            "authenticated": 0,
            "missing_env_vars": 0,
            "auth_required": 0,
            "failed": 0
        }
        
        for server_name in servers.keys():
            try:
                AUTH_LOG.debug(f"🔍 Validating authentication for: {server_name}")
                auth_status = self.auth_manager.validate_server_auth(server_name)
                self.authenticated_servers[server_name] = auth_status["authenticated"]
                
                if not auth_status["authenticated"] and auth_status.get("missing_env_vars"):
                    missing_vars = ', '.join(auth_status['missing_env_vars'])
                    AUTH_LOG.warning(f"🔐 {server_name}: Missing environment variables: {missing_vars}")
                    auth_summary["missing_env_vars"] += 1
                elif auth_status["authenticated"]:
                    AUTH_LOG.info(f"🔐 {server_name}: Authentication OK ✅")
                    auth_summary["authenticated"] += 1
                else:
                    AUTH_LOG.warning(f"🔐 {server_name}: Authentication required ⚠️")
                    auth_summary["auth_required"] += 1
                    
            except Exception as e:
                AUTH_LOG.error(f"🔐 {server_name}: Authentication check failed: {e}")
                self.authenticated_servers[server_name] = False
                auth_summary["failed"] += 1
        
        # Log authentication summary
        total_servers = len(servers)
        AUTH_LOG.info(f"🔐 Authentication Summary: {auth_summary['authenticated']}/{total_servers} authenticated, "
                     f"{auth_summary['missing_env_vars']} missing env vars, "
                     f"{auth_summary['auth_required']} need auth, "
                     f"{auth_summary['failed']} failed")

    def get_authentication_status(self, session_id: str = None) -> Dict[str, Any]:
        """Get authentication status for all servers"""
        return self.auth_manager.get_auth_status(session_id)
    
    def is_server_authenticated(self, server_name: str, session_id: str = None) -> bool:
        """Check if a specific server is authenticated"""
        return self.auth_manager.is_authenticated(server_name, session_id)
    
    def get_server_auth_config(self, server_name: str) -> Dict[str, Any]:
        """Get authentication configuration for a specific server"""
        return self.auth_manager.get_server_config(server_name)
    
    def validate_server_authentication(self, server_name: str, session_id: str = None) -> Dict[str, Any]:
        """Validate authentication for a server and return detailed status"""
        return self.auth_manager.validate_server_auth(server_name, session_id)
    
    def authenticate_server_session(self, server_name: str, session_id: str, credentials: Dict[str, Any]) -> bool:
        """Authenticate a session for a specific server"""
        return self.auth_manager.authenticate_session(server_name, session_id, credentials)
    
    def logout_server_session(self, server_name: str, session_id: str) -> bool:
        """Logout a session from a specific server"""
        return self.auth_manager.logout_session(server_name, session_id)
    
    def get_oauth_token_status(self, server_name: str) -> Dict[str, Any]:
        """Get OAuth token status for a server"""
        return self.oauth_manager.get_token_status(server_name)
    
    def refresh_oauth_token(self, server_name: str) -> bool:
        """
        Refresh OAuth token for a server.
        
        Args:
            server_name: Name of the server to refresh token for
        
        Returns:
            True if refresh successful, False otherwise
        """
        # Get server config to get token URL and credentials
        servers_config = self.config_manager.get_servers()
        if server_name not in servers_config:
            logger.error(f"❌ Server {server_name} not found in configuration")
            return False
        
        server_config = servers_config[server_name]
        auth_config = server_config.get('auth', {})
        
        if auth_config.get('type') != 'oauth2':
            logger.error(f"❌ Server {server_name} does not use OAuth authentication")
            return False
        
        token_url = auth_config.get('token_url')
        client_id = os.path.expandvars(auth_config.get('client_id', ''))
        client_secret = os.path.expandvars(auth_config.get('client_secret', ''))
        
        if not all([token_url, client_id, client_secret]):
            logger.error(f"❌ Missing OAuth configuration for {server_name}")
            return False
        
        result = self.oauth_manager.refresh_token(
            server_name, token_url, client_id, client_secret
        )
        
        return result is not None
    
    def check_and_refresh_oauth_tokens(self) -> None:
        """Check all OAuth-enabled servers and refresh tokens if needed"""
        servers_config = self.config_manager.get_servers()
        
        for server_name, server_config in servers_config.items():
            auth_config = server_config.get('auth', {})
            
            if auth_config.get('type') == 'oauth2':
                token_status = self.oauth_manager.get_token_status(server_name)
                
                if token_status['status'] == 'expired' and token_status.get('has_refresh_token'):
                    logger.info(f"🔄 Auto-refreshing expired token for {server_name}")
                    self.refresh_oauth_token(server_name)

    def _setup_mcp_client(self, servers: Dict[str, Any]) -> None:
        """Set up the MultiServerMCPClient using the working pattern from demo files."""
        connections = {}
        
        logger.info(f"Setting up MCP client connections...")
        
        for server_name, server_config in servers.items():
            logger.info(f"🔧 Processing server: {server_name}")
            
            # Handle HTTP servers separately
            if server_config.get('transport') == 'streamable_http':
                # Handle OAuth authentication if configured
                if 'auth' in server_config and server_config['auth'].get('type') == 'oauth2':
                    auth_config = server_config['auth'].copy()
                    env_config = server_config.get('env', {})
                    logger.info(f"🔐 OAuth authentication required for {server_name}")
                    
                    # Resolve environment variables from config's env section first, then from system env
                    def resolve_env_var(value):
                        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                            var_name = value[2:-1]
                            # First check server's env config
                            if var_name in env_config:
                                resolved = env_config[var_name]
                                # If the env config value is also a variable reference, resolve from system env
                                if isinstance(resolved, str) and resolved.startswith('${') and resolved.endswith('}'):
                                    return os.getenv(resolved[2:-1], '')
                                return resolved
                            # Fall back to system environment
                            return os.getenv(var_name, '')
                        return value
                    
                    # Resolve all auth config values
                    for key in ['client_id', 'client_secret', 'code']:
                        if key in auth_config:
                            auth_config[key] = resolve_env_var(auth_config[key])
                    
                    # Check if we already have a valid token
                    token_status = self.oauth_manager.get_token_status(server_name)
                    
                    if token_status['status'] != 'valid':
                        # Need to obtain/refresh token
                        logger.info(f"🔄 Obtaining OAuth token for {server_name}...")
                        logger.debug(f"   Using client_id: {auth_config.get('client_id', 'NOT SET')[:20]}...")
                        token_result = self.oauth_manager.exchange_authorization_code(
                            server_name, auth_config
                        )
                        
                        if not token_result:
                            logger.error(f"❌ Failed to obtain OAuth token for {server_name}")
                            logger.error(f"   Server {server_name} will not be available")
                            continue
                    else:
                        logger.info(f"✅ Valid OAuth token already available for {server_name}")
                
                if 'microsoft' in server_name.lower():
                    # Keep Microsoft Docs as HTTP agent
                    try:
                        self.http_agents[server_name] = HTTPMCPAgent(
                            server_name=server_name,
                            url=server_config['url'],
                            llm=self.llm
                        )
                        logger.info(f"✅ Added HTTP agent: {server_name}")
                    except Exception as e:
                        logger.error(f"❌ Failed to add HTTP agent {server_name}: {e}")
                    continue
                else:
                    # Other HTTP servers through MCP client
                    # Resolve environment variables in headers
                    def resolve_header_env_var(value):
                        """Resolve environment variable references in header values"""
                        if not isinstance(value, str):
                            return value
                        
                        # Check if value contains ${VAR_NAME} pattern
                        import re
                        pattern = r'\$\{([^}]+)\}'
                        matches = re.findall(pattern, value)
                        
                        if matches:
                            # Replace all ${VAR_NAME} with actual values
                            resolved = value
                            for var_name in matches:
                                env_value = os.getenv(var_name, '')
                                if not env_value:
                                    logger.warning(f"⚠️  Environment variable {var_name} not set for {server_name}")
                                resolved = resolved.replace(f'${{{var_name}}}', env_value)
                            return resolved
                        
                        return value
                    
                    # Add headers with environment variable resolution
                    headers = server_config.get('headers', {}).copy()
                    resolved_headers = {}
                    missing_token = False
                    
                    for key, value in headers.items():
                        resolved_value = resolve_header_env_var(value)
                        
                        # Check for Bearer token specifically
                        if key == 'Authorization':
                            if 'Bearer' in str(value):
                                # Check if token was properly resolved
                                # If resolved_value still contains ${, the variable wasn't set
                                if '${' in resolved_value:
                                    # Extract variable name for better error message
                                    var_match = re.search(r'\$\{([^}]+)\}', resolved_value)
                                    var_name = var_match.group(1) if var_match else 'TOKEN'
                                    logger.error(f"❌ Missing Bearer token for {server_name}")
                                    logger.error(f"   Environment variable {var_name} is not set")
                                    logger.error(f"   Server {server_name} will be skipped to prevent 401 errors")
                                    missing_token = True
                                    break
                                
                                # Check if token part is empty (e.g., "Bearer " with no token)
                                token_part = resolved_value.replace('Bearer', '').strip()
                                if not token_part:
                                    logger.error(f"❌ Empty Bearer token for {server_name}")
                                    logger.error(f"   Token resolved but is empty")
                                    logger.error(f"   Server {server_name} will be skipped to prevent 401 errors")
                                    missing_token = True
                                    break
                                
                                # Token is valid, use resolved value
                                resolved_headers[key] = resolved_value
                            else:
                                # Not a Bearer token, use as-is
                                resolved_headers[key] = resolved_value
                        else:
                            # Not Authorization header, use as-is
                            resolved_headers[key] = resolved_value
                    
                    if missing_token:
                        continue
                    
                    connections[server_name] = {
                        'url': server_config['url'],
                        'transport': 'streamable_http'
                    }
                    
                    # Add OAuth header if available
                    if 'auth' in server_config and server_config['auth'].get('type') == 'oauth2':
                        auth_header = self.oauth_manager.get_auth_header(server_name)
                        if auth_header:
                            resolved_headers.update(auth_header)
                            logger.info(f"🔐 Added OAuth authorization header for {server_name}")
                    
                    if resolved_headers:
                        connections[server_name]['headers'] = resolved_headers
                    
                    logger.info(f"✅ Added HTTP server: {server_name}")
            
            # Handle stdio servers
            elif 'command' in server_config:
                connections[server_name] = {
                    'command': server_config['command'],
                    'args': server_config.get('args', []),
                    'transport': 'stdio'
                }
                
                # Add environment variables if present
                if 'env' in server_config:
                    env_vars = {}
                    for key, value in server_config['env'].items():
                        # Handle environment variable substitution
                        if value.startswith('${') and value.endswith('}'):
                            env_var = value[2:-1]
                            env_value = os.getenv(env_var, '')
                            if not env_value:
                                logger.warning(f"⚠️  Environment variable {env_var} not set for server {server_name}")
                            else:
                                logger.debug(f"✓ {server_name}: {key} = {env_value[:10]}..." if len(env_value) > 10 else f"✓ {server_name}: {key} = {env_value}")
                            env_vars[key] = env_value
                        else:
                            env_vars[key] = value
                    connections[server_name]['env'] = env_vars
                    logger.debug(f"📝 {server_name} env vars: {list(env_vars.keys())}")
                
                logger.info(f"✅ Added stdio server: {server_name}")
            else:
                logger.warning(f"⚠️  Skipping server {server_name}: missing command or unsupported transport type {server_config.get('transport', 'none')}")
        
        # Initialize MultiServerMCPClient
        if connections:
            logger.info(f"📡 Found {len(connections)} usable servers: {list(connections.keys())}")
            try:
                self.mcp_client = MultiServerMCPClient(connections)
                logger.info("✅ MCP Client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize MCP Client: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                # Try to identify problematic servers
                logger.info("🔍 Attempting to identify problematic servers...")
                self._debug_server_connections(connections)
        else:
            logger.warning("❌ No usable server connections found")

    async def get_available_tools(self, force_refresh: bool = False) -> List:
        """Get all available tools with caching for improved performance."""
        # Force refresh if requested
        if force_refresh:
            logger.info("🔄 Forcing tool refresh (bypassing cache)...")
            self._clear_cache_internal()
        
        # Check if cache is still valid
        if self._tools_cached and self._cached_tools and self._is_cache_valid():
            logger.debug(f"🎯 Using cached tools ({len(self._cached_tools)} available)")
            self._cache_hits += 1
            return self._cached_tools
        
        # Cache expired or not available, clear it
        if self._tools_cached and not self._is_cache_valid():
            logger.info("🔄 Tool cache expired, refreshing...")
            self._clear_cache_internal()
        
        if not self.mcp_client:
            logger.warning("MCP client not initialized")
            http_tools = await self._get_http_agent_tools()
            # Cache HTTP-only tools
            self._cached_tools = http_tools
            self._tools_cached = True
            self._cache_timestamp = time.time()
            return http_tools
        
        try:
            logger.info("🔧 Getting available tools from MCP servers...")
            logger.info("⏳ This may take 15-20 seconds as servers start up...")
            logger.info(f"   MCP Client status: {'Initialized' if self.mcp_client else 'NOT initialized'}")
            
            # Increased timeout from 15s to 20s to give servers more time
            tools = await asyncio.wait_for(self.mcp_client.get_tools(), timeout=20.0)
            self.available_tools = tools
            logger.info(f"✅ Successfully retrieved {len(tools)} MCP stdio tools")
            
            if not tools:
                logger.warning("⚠️  NO MCP stdio tools loaded!")

            # Add HTTP agent tools
            http_tools = await self._get_http_agent_tools()
            all_tools = list(tools) + http_tools

            # Cache the results for future use
            self._cached_tools = all_tools
            self._tools_cached = True
            self._cache_timestamp = time.time()

            logger.info(
                f"🎯 Total tools available: {len(all_tools)} "
                f"({len(tools)} MCP stdio + {len(http_tools)} HTTP)"
            )
            self._log_tools_grouped_by_server(all_tools)
            
            # Warn if we only have HTTP tools
            if len(all_tools) <= 2:
                logger.warning("⚠️⚠️⚠️  WARNING: Very few tools loaded!")
                logger.warning("   This indicates MCP stdio servers failed to start")
            
            return all_tools
            
        except asyncio.TimeoutError:
            logger.error("⏰ Tool retrieval timed out after 20s")
            logger.error("❌ This means MCP stdio servers failed to start properly")
            logger.error("")
            logger.error("💡 Common causes:")
            logger.error("   1. 'uv' not installed or not in PATH")
            logger.error("   2. 'npx' not installed or not in PATH")
            logger.error("   3. 'docker' not running")
            logger.error("   4. Server Python code has syntax errors")
            logger.error("   5. Missing Python dependencies in servers")
            logger.error("")
            logger.error("🔍 To diagnose, run this in terminal:")
            logger.error("   uv --version")
            logger.error("   npx --version")
            logger.error("   docker ps")
            logger.error("")
            logger.info("🔄 Falling back to HTTP agent tools only (Microsoft Docs)...")
            http_tools = await self._get_http_agent_tools()
            # Cache fallback tools
            self._cached_tools = http_tools
            self._tools_cached = True
            self._cache_timestamp = time.time()
            return http_tools
        except Exception as e:
            logger.error(f"❌ Failed to get tools: {e}")
            logger.error("")
            
            # Check for specific error types
            error_str = str(e)
            
            if "Connection closed" in error_str:
                logger.error("🔴 CONNECTION CLOSED ERROR DETECTED")
                logger.error("   This means servers started but crashed immediately")
                logger.error("")
                logger.error("💡 Most likely causes:")
                logger.error("   1. Missing Python dependencies (run: uv pip list)")
                logger.error("   2. Syntax errors in server code")
                logger.error("   3. Import errors in server files")
                logger.error("   4. Environment variables not set correctly")
                logger.error("")
                logger.error("🔧 To debug, manually test a server:")
                logger.error("   cd Servers/weather")
                logger.error("   uv run --with mcp[cli] mcp run weather_analysis_mcp.py")
                logger.error("   (Check for error messages)")
                logger.error("")
                
            elif "TaskGroup" in error_str or "unhandled errors" in error_str:
                logger.error("🔴 TASKGROUP ERROR DETECTED")
                logger.error("   One or more servers failed during initialization")
                logger.error("")
                
                # Check for specific error types in the traceback
                if "401 Unauthorized" in error_str or "HTTPStatusError" in error_str:
                    logger.error("💡 AUTHENTICATION ERROR DETECTED")
                    logger.error("   One of the HTTP servers returned 401 Unauthorized")
                    logger.error("")
                    
                    # Try to identify which server failed from the error
                    failed_server = "unknown"
                    if "aria-mcp-server" in error_str:
                        failed_server = "aria"
                        token_var = "ARIA_BEARER_TOKEN"
                    elif "n8n-oasis" in error_str or "oasis" in error_str.lower():
                        failed_server = "oasis"
                        token_var = "OASIS_BEARER_TOKEN"
                    else:
                        token_var = "BEARER_TOKEN"
                    
                    logger.error(f"   Failed server: {failed_server}")
                    logger.error("")
                    logger.error("   Most likely causes:")
                    logger.error(f"   - Missing or invalid Bearer token (check {token_var})")
                    logger.error("   - Expired authentication token")
                    logger.error("   - Incorrect API credentials")
                    logger.error("")
                    logger.error("   🔧 To fix:")
                    logger.error(f"   1. Check your .env file for {token_var}")
                    logger.error("   2. Verify the token is valid and not expired")
                    logger.error("   3. If token is missing, the server will be skipped automatically")
                    logger.error(f"   4. If token is invalid/expired, update {token_var} in your .env file")
                    logger.error("")
                    logger.error("   ⚠️  Note: Other servers will continue to work even if this one fails")
                    logger.error("")
                else:
                    logger.error("💡 This could be caused by:")
                    logger.error("   - Missing system dependencies (uv, npx, docker)")
                    logger.error("   - Missing environment variables (API keys)")
                    logger.error("   - Server code bugs or crashes")
                    logger.error("   - Port conflicts")
                    logger.error("   - Network connectivity issues")
                    logger.error("")
            
            # More detailed error logging
            import traceback
            error_traceback = traceback.format_exc()
            error_lines = error_traceback.split('\n')
            
            # Check traceback for specific error patterns
            has_401_error = "401" in error_traceback or "Unauthorized" in error_traceback
            has_http_error = "HTTPStatusError" in error_traceback or "httpx" in error_traceback.lower()
            
            if has_401_error or has_http_error:
                logger.error("📋 Error traceback (showing HTTP error details):")
                # Show more context for HTTP errors
                for i, line in enumerate(error_lines):
                    if "401" in line or "Unauthorized" in line or "HTTPStatusError" in line or "httpx" in line.lower():
                        # Show surrounding context
                        start = max(0, i - 3)
                        end = min(len(error_lines), i + 8)
                        for j in range(start, end):
                            if error_lines[j].strip():
                                logger.error(f"   {error_lines[j]}")
                        break
            else:
                logger.error("📋 Error traceback (last 15 lines):")
                for line in error_lines[-15:]:
                    if line.strip():
                        logger.error(f"   {line}")
            logger.error("")
            
            logger.info("🔄 Falling back to HTTP agent tools only (Microsoft Docs)...")
            logger.info("   ⚠️  Most MCP servers are NOT working - only HTTP servers available")
            logger.info("")
            
            http_tools = await self._get_http_agent_tools()
            # Cache fallback tools
            self._cached_tools = http_tools
            self._tools_cached = True
            self._cache_timestamp = time.time()
            return http_tools

    async def _get_http_agent_tools(self) -> List:
        """Get tools from HTTP agents only (these are reliable)"""
        http_tools = []
        
        for agent_name, agent in self.http_agents.items():
            try:
                # Create actual executable LangChain tool
                http_tool = self._create_http_agent_tool(agent_name, agent)
                http_tools.append(http_tool)
                logger.debug(f"Added HTTP agent tool: {agent_name}")
            except Exception as agent_error:
                logger.warning(f"Error adding HTTP agent {agent_name}: {agent_error}")
        
        return http_tools
    
    def _create_http_agent_tool(self, agent_name: str, agent: HTTPMCPAgent):
        """Create an executable LangChain tool for HTTP agent"""
        
        # Create input schema
        class HTTPAgentInput(BaseModel):
            query: str = Field(description="The search query or question")
        
        # Create the tool function
        @tool(description=f"Search and query {agent_name} documentation and knowledge base. Use this tool for questions about {agent_name} topics, especially Microsoft Azure, Office 365, and other Microsoft services.",
              args_schema=HTTPAgentInput)
        async def http_agent_search(query: str) -> str:
            """Execute HTTP agent search"""
            try:
                logger.info(f"🔍 Executing {agent_name} search for: {query}")
                result = await agent.run(query)
                logger.info(f"✅ {agent_name} search completed successfully")
                return result
            except Exception as e:
                logger.error(f"❌ Error in {agent_name} search: {e}")
                return f"Error searching {agent_name}: {str(e)}"
        
        # Set the tool name after creation
        http_agent_search.name = f"{agent_name}_search"
        
        return http_agent_search

    async def _setup_agent(self, force_refresh: bool = False) -> bool:
        """Setup the React agent with available tools using caching for performance."""
        # Force refresh if requested
        if force_refresh and self._agent_initialized:
            logger.info("🔄 Forcing agent refresh (bypassing cache)...")
            self._agent_initialized = False
            self.agent = None
        
        # Use pre-initialized agent if available
        if self._agent_initialized and self.agent:
            logger.debug("🎯 Using cached agent")
            return True
            
        if not self.llm:
            logger.error("LLM not available for agent creation")
            return False

        if self.streaming_enabled() and not getattr(self.llm, "streaming", False):
            logger.info("🌊 Switching agent LLM to streaming mode")
            self.llm = get_llm_from_config(streaming=True)
            self.agent = None
            self._agent_initialized = False
            
        try:
            agent_start_time = time.time()
            
            # Get available tools (force refresh if agent is being refreshed)
            tools = await self.get_available_tools(force_refresh=force_refresh)
            if not tools:
                logger.warning("No tools available for agent")
                return False
            
            # Log which tools will be used for agent creation
            tool_names = [t.name for t in tools]
            logger.info(f"🤖 Creating React agent with {len(tools)} tools...")
            logger.info(f"📋 Tool names: {', '.join(tool_names[:10])}{'...' if len(tool_names) > 10 else ''}")
            
            # Check if we only have HTTP tools (indicates MCP servers failed)
            if len(tools) == 1 and 'microsoft' in tool_names[0].lower():
                logger.warning("⚠️  Agent being created with ONLY Microsoft Docs tool!")
                logger.warning("⚠️  MCP servers are NOT working - agent will have limited capabilities")
            
            # Create agent using the working pattern with optimized configuration
            self.agent = create_react_agent(self.llm, tools=tools)
            self._agent_initialized = True  # Mark as initialized for future use
            
            agent_time = time.time() - agent_start_time
            logger.info(f"✅ Agent created successfully and cached in {agent_time:.2f}s")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create agent: {e}")
            return False

    def _log_tools_grouped_by_server(self, tools: List, *, preview_per_group: int = 5) -> None:
        """Log tools grouped by MCP/system prefix (same layout as main.py startup)."""
        if not tools:
            logger.warning("⚠️  No tools to display")
            return

        tool_groups: Dict[str, List[str]] = {}
        for tool in tools:
            name = getattr(tool, "name", str(tool))
            prefix = name.split("_")[0] if "_" in name else "unknown"
            tool_groups.setdefault(prefix, []).append(name)

        logger.info("📊 Tools grouped by server:")
        logger.info("=" * 76)
        for server, names in sorted(tool_groups.items()):
            logger.info(f"📦 {server.upper()} ({len(names)} tools)")
            logger.info("-" * 76)
            for tool_name in names[:preview_per_group]:
                logger.info(f"   • {tool_name}")
            if len(names) > preview_per_group:
                logger.info(f"   ... and {len(names) - preview_per_group} more")
            logger.info("")
        logger.info("=" * 76)

    async def warm_up_agent(self) -> bool:
        """Pre-load tools and create the agent so the first user query is not penalized."""
        if not self.llm:
            logger.warning("Cannot warm up agent: LLM not configured")
            return False
        if self.agent and self._agent_initialized:
            logger.info("Agent already warm")
            return True
        try:
            start = time.time()
            logger.info("🔥 Warming up agent (tools + react agent)...")
            if not (self._tools_cached and self._cached_tools):
                await self.get_available_tools(force_refresh=True)
            if self.streaming_enabled():
                ok = await self._ensure_streaming_llm_and_agent()
            else:
                ok = await self._setup_agent(force_refresh=False)
            elapsed = time.time() - start
            if ok:
                diag = self.get_streaming_diagnostics()
                logger.info(
                    f"✅ Agent warm-up completed in {elapsed:.2f}s "
                    f"({len(self._cached_tools)} tools) "
                    f"streaming={diag['streaming_enabled']} llm_streaming={diag['llm_streaming']}"
                )
            else:
                logger.error(f"❌ Agent warm-up failed after {elapsed:.2f}s")
            return ok
        except Exception as e:
            logger.error(f"❌ Agent warm-up error: {e}")
            return False

    def _detect_parallel_tasks(self, user_input: str) -> List[str]:
        """
        Detect if the user input contains multiple independent tasks that can be executed in parallel.
        
        Args:
            user_input: User's input query
            
        Returns:
            List of independent task strings, or empty list if tasks are sequential
        """
        # Check for common separators indicating parallel tasks
        parallel_indicators = [
            ' and ', ' also ', ' additionally ', ' furthermore ',
            ', also', '. Also', '. Additionally'
        ]
        
        # Convert to lowercase for checking
        user_input_lower = user_input.lower()
        
        # Check if query has parallel structure
        has_parallel_structure = any(indicator in user_input_lower for indicator in parallel_indicators)
        
        if not has_parallel_structure:
            return []
        
        # Split by common separators while preserving the text
        import re
        # Split on "Also," or ". Also" or " and " when followed by action verbs
        pattern = r'(?:,?\s+also,?\s+|;\s*|\.\s+Also,?\s+|\.\s+Additionally,?\s+)'
        tasks = re.split(pattern, user_input, flags=re.IGNORECASE)
        
        # Only return if we have 2-4 clear independent tasks (more than 4 might be too complex)
        if 2 <= len(tasks) <= 4:
            # Verify each task is substantial enough (more than 10 characters)
            substantial_tasks = [task.strip() for task in tasks if len(task.strip()) > 10]
            if len(substantial_tasks) >= 2:
                PERFORMANCE_LOG.info(f"🔀 Detected {len(substantial_tasks)} parallel tasks for optimization")
                return substantial_tasks
        
        return []
    
    async def _execute_parallel_tasks(self, tasks: List[str], channel_id: Optional[str] = None,
                                     thread_ts: Optional[str] = None) -> str:
        """
        Execute multiple independent tasks in parallel for better performance.
        
        Args:
            tasks: List of independent task strings
            channel_id: Channel identifier
            thread_ts: Thread timestamp
            
        Returns:
            Combined response from all tasks
        """
        PERFORMANCE_LOG.info(f"⚡ Executing {len(tasks)} tasks in parallel...")
        parallel_start = time.time()
        
        # Create coroutines for each task
        async def execute_single_task(task: str, task_num: int) -> Dict[str, Any]:
            try:
                task_start = time.time()
                PERFORMANCE_LOG.info(f"🚀 Task {task_num}: Starting - {task[:80]}...")
                
                # Get conversation history
                history_messages = self.conversation_manager.get_history_messages(channel_id, thread_ts)
                agent_messages = [(msg['role'], msg['content']) for msg in history_messages]
                agent_messages.append(("user", task))
                
                # Execute task with shorter timeout per task
                response = await asyncio.wait_for(
                    self.agent.ainvoke({"messages": agent_messages}),
                    timeout=self._parallel_task_timeout,
                )
                
                task_time = time.time() - task_start
                result = self._extract_ai_message_content(response)
                
                PERFORMANCE_LOG.info(f"✅ Task {task_num}: Completed in {task_time:.2f}s")
                
                return {
                    "task_num": task_num,
                    "task": task,
                    "result": result,
                    "time": task_time,
                    "success": True
                }
            except asyncio.TimeoutError:
                PERFORMANCE_LOG.error(f"⏰ Task {task_num}: Timeout after 30s")
                return {
                    "task_num": task_num,
                    "task": task,
                    "result": f"⏰ Task timed out: {task[:100]}...",
                    "time": 30.0,
                    "success": False
                }
            except Exception as e:
                PERFORMANCE_LOG.error(f"❌ Task {task_num}: Error - {e}")
                return {
                    "task_num": task_num,
                    "task": task,
                    "result": f"❌ Error in task: {str(e)}",
                    "time": 0,
                    "success": False
                }
        
        # Execute all tasks in parallel
        task_coroutines = [execute_single_task(task, i+1) for i, task in enumerate(tasks)]
        results = await asyncio.gather(*task_coroutines, return_exceptions=True)
        
        parallel_time = time.time() - parallel_start
        PERFORMANCE_LOG.info(f"⚡ Parallel execution completed in {parallel_time:.2f}s")
        
        # Combine results
        combined_response = "# Multi-Task Response\n\n"
        successful_tasks = 0
        
        for result in results:
            if isinstance(result, Exception):
                combined_response += f"❌ Task failed with exception: {str(result)}\n\n"
            else:
                task_num = result['task_num']
                task_desc = result['task'][:100]
                
                if result['success']:
                    successful_tasks += 1
                    combined_response += f"## Task {task_num}: {task_desc}\n"
                    combined_response += f"⏱️ Completed in {result['time']:.1f}s\n\n"
                    combined_response += f"{result['result']}\n\n"
                    combined_response += "---\n\n"
                else:
                    combined_response += f"## Task {task_num}: {task_desc}\n"
                    combined_response += f"{result['result']}\n\n"
                    combined_response += "---\n\n"
        
        # Add summary
        combined_response += f"\n**Performance Summary:** Executed {len(tasks)} tasks in parallel. "
        combined_response += f"{successful_tasks}/{len(tasks)} successful. Total time: {parallel_time:.1f}s"
        
        if successful_tasks == len(tasks):
            max_sequential_time = sum(r['time'] for r in results if not isinstance(r, Exception))
            time_saved = max_sequential_time - parallel_time
            if time_saved > 5:
                combined_response += f" (Saved ~{time_saved:.1f}s vs sequential execution)"
        
        return combined_response

    async def process_request(self, user_input: str, channel_id: Optional[str] = None, 
                            thread_ts: Optional[str] = None) -> Optional[str]:
        """
        Process user request using the simplified MultiServerMCPClient approach.
        Automatically detects and parallelizes independent tasks for better performance.
        
        Args:
            user_input: User's input/query
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
            
        Returns:
            Response from the agent
        """
        # Track request performance
        request_start_time = time.time()
        request_id = f"req_{int(time.time() * 1000)}_{self._request_count}"
        self._request_count += 1
        
        # Enhanced logging for sample prompts testing
        SAMPLE_PROMPTS_LOG.info(f"🎯 [{request_id}] PROCESSING REQUEST: '{user_input[:150]}{'...' if len(user_input) > 150 else ''}'")
        SAMPLE_PROMPTS_LOG.info(f"📍 [{request_id}] Channel: {channel_id}, Thread: {thread_ts}")
        
        # Detect if this looks like one of our Adobe-focused sample prompts
        adobe_keywords = ['adobe', 'creative suite', 'photoshop', 'creative cloud']
        is_adobe_prompt = any(keyword.lower() in user_input.lower() for keyword in adobe_keywords)
        if is_adobe_prompt:
            SAMPLE_PROMPTS_LOG.info(f"🎨 [{request_id}] ADOBE-FOCUSED PROMPT DETECTED")
        
        # PERFORMANCE OPTIMIZATION: Detect parallel tasks
        parallel_tasks = self._detect_parallel_tasks(user_input)
        if parallel_tasks:
            PERFORMANCE_LOG.info(f"⚡ [{request_id}] PARALLEL EXECUTION MODE: {len(parallel_tasks)} tasks detected")
        
        try:
            # Check if user is requesting a specific server
            requested_server = self._extract_server_preference(user_input)
            if requested_server:
                SAMPLE_PROMPTS_LOG.info(f"🎯 [{request_id}] Specific server requested: {requested_server}")
            
            # If a specific server is requested, validate authentication
            if requested_server:
                auth_status = self.validate_server_authentication(requested_server, channel_id)
                if not auth_status["authenticated"]:
                    AUTH_LOG.warning(f"🔐 [{request_id}] Authentication failed for {requested_server}")
                    if auth_status.get("missing_env_vars"):
                        env_vars = ", ".join(auth_status["missing_env_vars"])
                        return f"🔐 Authentication failed for {requested_server}: Missing environment variables: {env_vars}. Please set these variables in your .env file."
                    else:
                        return f"🔐 Authentication required for {auth_status.get('auth_config', {}).get('display_name', requested_server)}. Please authenticate first."
            
            # Setup agent if not already done (with performance timing)
            if not self.agent:
                agent_setup_start = time.time()
                SAMPLE_PROMPTS_LOG.info(f"🤖 [{request_id}] Setting up agent for first time...")

                if not (self._tools_cached and self._cached_tools):
                    logger.info("🔄 Loading tool list for agent creation...")
                    await self.get_available_tools(force_refresh=True)
                    logger.info(f"📊 Loaded {len(self._cached_tools)} tools for agent")

                tools = self._cached_tools
                tool_names = [t.name for t in tools]
                if len(tools) == 1 and 'microsoft' in tool_names[0].lower():
                    logger.error("🔴 CRITICAL: Only Microsoft Docs tool available! MCP servers failed!")
                else:
                    logger.info(f"✅ Good! Have {len(tools)} tools including MCP servers")

                success = await self._setup_agent(force_refresh=False)
                if not success:
                    SAMPLE_PROMPTS_LOG.error(f"❌ [{request_id}] Failed to initialize agent")
                    return "Failed to initialize agent. Please check server configuration."
                
                agent_setup_time = time.time() - agent_setup_start
                SAMPLE_PROMPTS_LOG.info(f"✅ [{request_id}] Agent setup completed in {agent_setup_time:.2f}s with {len(tools)} tools")
            
            # PERFORMANCE BOOST: Use parallel execution if multiple independent tasks detected
            if parallel_tasks:
                PERFORMANCE_LOG.info(f"🚀 [{request_id}] Using PARALLEL EXECUTION mode")
                try:
                    final_message = await self._execute_parallel_tasks(parallel_tasks, channel_id, thread_ts)
                    
                    # Add to conversation history
                    self.conversation_manager.add_message("user", user_input, channel_id, thread_ts)
                    self.conversation_manager.add_message("assistant", final_message, channel_id, thread_ts)
                    
                    # Record metrics
                    response_time = time.time() - request_start_time
                    self._total_response_time += response_time
                    
                    SAMPLE_PROMPTS_LOG.info(f"✅ [{request_id}] PARALLEL REQUEST COMPLETED in {response_time:.2f}s")
                    PERFORMANCE_LOG.info(f"📈 Request #{self._request_count}: {response_time:.2f}s total (PARALLEL mode)")
                    
                    return final_message
                except Exception as e:
                    PERFORMANCE_LOG.error(f"❌ [{request_id}] Parallel execution failed: {e}, falling back to sequential")
                    # Fall through to sequential execution below
            
            # Log available servers for context
            available_servers = self.get_available_servers()
            SAMPLE_PROMPTS_LOG.info(f"🌐 [{request_id}] Available servers: {', '.join(available_servers) if available_servers else 'None'}")
            
            # Log current tools available (grouped by MCP/system category)
            try:
                tools = await self.get_available_tools()
                tool_groups: Dict[str, int] = {}
                for tool in tools:
                    name = getattr(tool, "name", str(tool))
                    prefix = name.split("_")[0] if "_" in name else "unknown"
                    tool_groups[prefix] = tool_groups.get(prefix, 0) + 1
                groups_summary = ", ".join(
                    f"{k.upper()}({v})" for k, v in sorted(tool_groups.items())
                )
                SAMPLE_PROMPTS_LOG.info(
                    f"🛠️ [{request_id}] Available tools ({len(tools)}): {groups_summary}"
                )
            except Exception as e:
                SAMPLE_PROMPTS_LOG.warning(f"⚠️ [{request_id}] Could not log available tools: {e}")
            
            try:
                # Get conversation history for context (before adding current message)
                history_messages = self.conversation_manager.get_history_messages(channel_id, thread_ts)
                
                # Convert to agent format
                agent_messages = []
                for msg in history_messages:
                    agent_messages.append((msg['role'], msg['content']))
                
                # Add current user input
                agent_messages.append(("user", user_input))
                
                # Log context info
                if len(history_messages) > 0:
                    SAMPLE_PROMPTS_LOG.info(f"📚 [{request_id}] Including {len(history_messages)} previous messages for context")
                else:
                    SAMPLE_PROMPTS_LOG.info(f"📚 [{request_id}] No previous conversation history")
                
                self.conversation_manager.add_message(
                    "user", user_input, channel_id, thread_ts
                )
                agent_start_time = time.time()
                SAMPLE_PROMPTS_LOG.info(
                    f"🚀 [{request_id}] Invoking agent with {len(agent_messages)} messages..."
                )
                response = await asyncio.wait_for(
                    self.agent.ainvoke({"messages": agent_messages}),
                    timeout=self._agent_invoke_timeout,
                )
                agent_time = time.time() - agent_start_time
                SAMPLE_PROMPTS_LOG.info(f"⚡ [{request_id}] Agent completed in {agent_time:.2f}s")
                self._log_tool_calls(response, request_id)
                final_message = self._extract_ai_message_content(response)

                if final_message and str(final_message).strip():
                    self.conversation_manager.add_message(
                        "assistant", final_message, channel_id, thread_ts
                    )
                    
                    # Record successful response time and log detailed metrics
                    response_time = time.time() - request_start_time
                    self._total_response_time += response_time
                    
                    # Enhanced completion logging
                    SAMPLE_PROMPTS_LOG.info(f"✅ [{request_id}] REQUEST COMPLETED successfully in {response_time:.2f}s")
                    SAMPLE_PROMPTS_LOG.info(f"📊 [{request_id}] Response length: {len(final_message)} characters")
                    
                    # Performance metrics logging
                    PERFORMANCE_LOG.info(f"📈 Request #{self._request_count}: {response_time:.2f}s total, {agent_time:.2f}s agent")
                    
                    if is_adobe_prompt:
                        SAMPLE_PROMPTS_LOG.info(f"🎨 [{request_id}] ADOBE PROMPT COMPLETED - Response preview: {final_message[:200]}{'...' if len(final_message) > 200 else ''}")
                    
                    return final_message
                else:
                    SAMPLE_PROMPTS_LOG.warning(f"⚠️ [{request_id}] Query processed but no response content available")
                    return "Query processed successfully but no response content available."
                    
            except asyncio.TimeoutError:
                timeout_time = time.time() - request_start_time
                SAMPLE_PROMPTS_LOG.error(f"⏰ [{request_id}] Query timed out after {timeout_time:.2f}s")
                if is_adobe_prompt:
                    SAMPLE_PROMPTS_LOG.error(f"🎨 [{request_id}] ADOBE PROMPT TIMEOUT - Consider simplifying the query")
                timeout_sec = int(self._agent_invoke_timeout)
                return (
                    f"⏰ Query timed out after {timeout_sec} seconds. This could be due to:\n"
                    "• Complex query requiring multiple tool calls\n"
                    "• Server connectivity issues\n"
                    "• Heavy server load\n\n"
                    "Try breaking your request into smaller parts or check server status."
                )
            except Exception as e:
                error_time = time.time() - request_start_time
                SAMPLE_PROMPTS_LOG.error(f"❌ [{request_id}] Query failed after {error_time:.2f}s: {e}")
                if is_adobe_prompt:
                    SAMPLE_PROMPTS_LOG.error(f"🎨 [{request_id}] ADOBE PROMPT FAILED: {e}")
                return f"Error processing your request: {str(e)}"
            
        except Exception as e:
            logger.error(f"Error in request processing: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return f"Sorry, there was an error processing your request. Please try again or check server status."

    def _resolve_tool_for_action(
        self, server_name: str, action: str, tools: List
    ) -> Optional[Any]:
        """Resolve a UI action to a LangChain tool from the available MCP tools."""
        server_map = self._UI_ACTION_TO_TOOL.get(server_name, {})
        candidates = [
            server_map.get(action),
            f"{server_name}_{action}",
            action,
        ]
        candidates = [c for c in candidates if c]

        tool_by_name = {getattr(t, "name", ""): t for t in tools}
        for name in candidates:
            if name in tool_by_name:
                return tool_by_name[name]

        action_norm = action.replace("get_", "").replace("_", "")
        for tool in tools:
            tool_name = getattr(tool, "name", "")
            if not tool_name.startswith(f"{server_name}_"):
                continue
            if action_norm in tool_name.replace("_", ""):
                return tool
        return None

    async def route_to_server(
        self, server_name: str, request: Union[str, Dict[str, Any]]
    ) -> Optional[str]:
        """
        Route a direct tool call to a specific MCP server (used by Streamlit tool UI).

        Args:
            server_name: MCP server key from config (e.g. 'youtube')
            request: Dict with 'action' and tool parameters, or a natural-language string

        Returns:
            Tool result as a string, or an error message
        """
        if isinstance(request, str):
            return await self.process_request(request)

        if not isinstance(request, dict):
            return "Invalid request: expected dict or string"

        action = request.get("action")
        if not action:
            return "Invalid request: 'action' is required"

        tool_args = {k: v for k, v in request.items() if k != "action"}

        tools = await self.get_available_tools()
        tool = self._resolve_tool_for_action(server_name, action, tools)
        if not tool:
            available = [
                getattr(t, "name", str(t))
                for t in tools
                if getattr(t, "name", "").startswith(f"{server_name}_")
            ]
            hint = f" Available {server_name} tools: {', '.join(available)}" if available else ""
            return f"Tool not found for action '{action}' on server '{server_name}'.{hint}"

        try:
            logger.info(
                f"🔧 route_to_server: {server_name}.{action} -> {tool.name}({list(tool_args.keys())})"
            )
            result = await asyncio.wait_for(tool.ainvoke(tool_args), timeout=60.0)
            if isinstance(result, str):
                return result
            return json.dumps(result, indent=2, default=str)
        except asyncio.TimeoutError:
            return f"Tool '{getattr(tool, 'name', action)}' timed out after 60 seconds"
        except Exception as e:
            logger.error(f"route_to_server failed for {server_name}.{action}: {e}")
            return f"Error executing {action}: {e}"

    async def _ensure_agent_for_request(self) -> bool:
        if self.agent:
            return True
        if not (self._tools_cached and self._cached_tools):
            await self.get_available_tools(force_refresh=True)
        return await self._setup_agent(force_refresh=False)

    def get_streaming_diagnostics(self) -> Dict[str, Any]:
        """Runtime check for whether token streaming is active."""
        llm = self.llm
        return {
            "streaming_enabled": self.streaming_enabled(),
            "llm_class": type(llm).__name__ if llm else None,
            "llm_streaming": bool(getattr(llm, "streaming", False)) if llm else False,
            "agent_ready": bool(self.agent),
            "tool_count": len(self._cached_tools) if self._cached_tools else 0,
        }

    @staticmethod
    def _text_from_stream_message(message: Any) -> str:
        if isinstance(message, ToolMessage):
            return ""
        if not isinstance(message, (AIMessage, AIMessageChunk)):
            return ""
        content = message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "".join(parts)
        return str(content) if content else ""

    @staticmethod
    def _status_events_from_stream_message(message: Any) -> List[Dict[str, str]]:
        """Progress events while tools run (most wall-clock time for multi-tool prompts)."""
        events: List[Dict[str, str]] = []
        if isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", None) or "tool"
            events.append(
                {"type": "status", "content": f"✅ Finished {tool_name}"}
            )
            return events
        if not isinstance(message, (AIMessage, AIMessageChunk)):
            return events
        tool_calls = getattr(message, "tool_calls", None) or []
        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "tool")
            else:
                name = getattr(tc, "name", "tool")
            events.append(
                {"type": "status", "content": f"🔧 Running {name}..."}
            )
        return events

    async def process_request_stream(
        self,
        user_input: str,
        channel_id: Optional[str] = None,
        thread_ts: Optional[str] = None,
    ):
        """Yield SSE-friendly events: token | done | error."""
        if not await self._ensure_streaming_llm_and_agent():
            yield {"type": "error", "content": "Failed to initialize agent."}
            return

        diag = self.get_streaming_diagnostics()
        logger.info(
            "🌊 Stream session: enabled=%s llm_streaming=%s agent=%s tools=%s",
            diag["streaming_enabled"],
            diag["llm_streaming"],
            diag["agent_ready"],
            diag["tool_count"],
        )
        yield {
            "type": "status",
            "content": (
                f"🌊 Streaming on (LLM streaming={diag['llm_streaming']}). "
                "Tool steps will show progress; answer text streams after each LLM turn."
            ),
        }

        history = self.conversation_manager.get_history_messages(channel_id, thread_ts)
        agent_messages = [(m["role"], m["content"]) for m in history]
        agent_messages.append(("user", user_input))
        self.conversation_manager.add_message("user", user_input, channel_id, thread_ts)

        parts: List[str] = []
        deadline = time.time() + self._agent_invoke_timeout
        try:
            async for message, _meta in self.agent.astream(
                {"messages": agent_messages},
                stream_mode="messages",
            ):
                if time.time() > deadline:
                    timeout_sec = int(self._agent_invoke_timeout)
                    yield {
                        "type": "error",
                        "content": f"Query timed out after {timeout_sec} seconds.",
                    }
                    return
                for status_event in self._status_events_from_stream_message(message):
                    yield status_event
                text = self._text_from_stream_message(message)
                if not text:
                    continue
                parts.append(text)
                yield {"type": "token", "content": text}
            final = "".join(parts)
            if final:
                self.conversation_manager.add_message("assistant", final, channel_id, thread_ts)
            yield {"type": "done", "content": final or "Query processed successfully but no response content available."}
        except asyncio.TimeoutError:
            timeout_sec = int(self._agent_invoke_timeout)
            yield {"type": "error", "content": f"Query timed out after {timeout_sec} seconds."}
        except Exception as e:
            logger.exception("process_request_stream failed: %s", e)
            yield {"type": "error", "content": str(e)}

    def _is_cache_valid(self) -> bool:
        """Check if the current cache is still valid (not expired)."""
        if not self._cache_timestamp:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_expiry_seconds
    
    def _clear_cache_internal(self) -> None:
        """Internal method to clear cache without logging."""
        self._tools_cached = False
        self._agent_initialized = False
        self._cached_tools = []
        self.agent = None
        self._cache_timestamp = None
    
    def clear_cache(self) -> None:
        """Clear cached tools and agent to force refresh on next request."""
        self._clear_cache_internal()
        logger.info("🔄 Performance cache cleared - will refresh on next request")
    
    async def refresh_tools_and_agent(self) -> bool:
        """Force refresh of tools and agent - useful when servers are restarted."""
        logger.info("🔄 Forcing complete refresh of tools and agent...")
        
        # Clear cache
        self._clear_cache_internal()
        
        # Get fresh tools
        tools = await self.get_available_tools(force_refresh=True)
        logger.info(f"✅ Refreshed {len(tools)} tools")
        
        # Recreate agent with fresh tools
        success = await self._setup_agent(force_refresh=True)
        if success:
            logger.info("✅ Agent refreshed successfully")
        else:
            logger.error("❌ Failed to refresh agent")
        
        return success
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get current cache status for performance monitoring."""
        cache_age = None
        if self._cache_timestamp:
            cache_age = time.time() - self._cache_timestamp
            
        avg_response_time = None
        if self._request_count > 0:
            avg_response_time = self._total_response_time / self._request_count
            
        return {
            "tools_cached": self._tools_cached,
            "agent_initialized": self._agent_initialized,
            "cached_tools_count": len(self._cached_tools) if self._cached_tools else 0,
            "agent_available": self.agent is not None,
            "cache_age_seconds": round(cache_age, 2) if cache_age else None,
            "cache_valid": self._is_cache_valid(),
            "request_count": self._request_count,
            "cache_hits": self._cache_hits,
            "average_response_time": round(avg_response_time, 2) if avg_response_time else None,
            "cache_hit_rate": round(self._cache_hits / max(self._request_count, 1) * 100, 1) if self._request_count > 0 else 0
        }
    
    def get_server_health_status(self) -> Dict[str, bool]:
        """Get health status of all servers for performance optimization."""
        health_status = {}
        
        # Check MCP client health
        if self.mcp_client:
            health_status["mcp_client"] = True
        else:
            health_status["mcp_client"] = False
            
        # Check HTTP agents health
        for agent_name, agent in self.http_agents.items():
            health_status[agent_name] = True  # HTTP agents are generally reliable
            
        # Check authentication status
        for server_name, is_authenticated in self.authenticated_servers.items():
            health_status[f"{server_name}_auth"] = is_authenticated
            
        return health_status
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics for monitoring and optimization."""
        cache_status = self.get_cache_status()
        
        return {
            "performance": {
                "total_requests": self._request_count,
                "cache_hits": self._cache_hits,
                "cache_hit_rate_percent": cache_status["cache_hit_rate"],
                "average_response_time_seconds": cache_status["average_response_time"],
                "total_response_time_seconds": round(self._total_response_time, 2)
            },
            "cache": {
                "tools_cached": cache_status["tools_cached"],
                "cached_tools_count": cache_status["cached_tools_count"],
                "agent_initialized": cache_status["agent_initialized"],
                "cache_age_seconds": cache_status["cache_age_seconds"],
                "cache_valid": cache_status["cache_valid"],
                "cache_expiry_seconds": self._cache_expiry_seconds
            },
            "system": {
                "mcp_client_active": self.mcp_client is not None,
                "http_agents_count": len(self.http_agents),
                "conversation_threads": self.conversation_manager.get_thread_count()
            }
        }

    def get_available_servers(self) -> list:
        """Get list of available server names."""
        return self.config_manager.get_all_server_names()

    def get_server_capabilities(self, server_name: str) -> str:
        """Get capabilities description for a specific server."""
        return self.config_manager.get_server_config(server_name).get('description', 'No description available')

    def clear_conversation_history(self, channel_id: Optional[str] = None, 
                                 thread_ts: Optional[str] = None) -> None:
        """
        Clear conversation history for a specific channel/thread.
        
        Args:
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
        """
        self.conversation_manager.clear_history(channel_id, thread_ts)

    def clear_all_conversations(self) -> None:
        """Clear all conversation history."""
        self.conversation_manager.clear_all_history()

    def _debug_server_connections(self, connections: Dict[str, Any]) -> None:
        """Debug server connections to identify problematic servers."""
        logger.info("🔍 Debugging server connections...")
        
        for server_name, config in connections.items():
            logger.info(f"📋 Debugging server: {server_name}")
            
            # Check transport type
            transport = config.get('transport', 'unknown')
            logger.info(f"  Transport: {transport}")
            
            if transport == 'stdio':
                # Check if command exists
                command = config.get('command')
                if command:
                    logger.info(f"  Command: {command}")
                    
                    # Check if it's a system command
                    if command in ['uv', 'npx', 'docker']:
                        import shutil
                        if shutil.which(command):
                            logger.info(f"  ✅ Command '{command}' found in PATH")
                        else:
                            logger.error(f"  ❌ Command '{command}' NOT found in PATH - this will cause failures!")
                    
                    # Check environment variables
                    env_vars = config.get('env', {})
                    if env_vars:
                        logger.info(f"  Environment variables required: {len(env_vars)}")
                        for key, value in env_vars.items():
                            if not value:
                                logger.error(f"    ❌ {key}: EMPTY - this will cause failures!")
                            elif '${' in str(value):
                                logger.warning(f"    ⚠️  {key}: Contains variable substitution - check if resolved correctly")
                            else:
                                logger.info(f"    ✅ {key}: Set")
                else:
                    logger.error(f"  ❌ No command specified for stdio server!")
            
            elif transport == 'streamable_http':
                url = config.get('url')
                if url:
                    logger.info(f"  URL: {url}")
                else:
                    logger.error(f"  ❌ No URL specified for HTTP server!")
            
            else:
                logger.error(f"  ❌ Unknown transport type: {transport}")
    
    async def test_individual_servers(self) -> Dict[str, str]:
        """Test each server individually to identify which ones are problematic."""
        logger.info("🧪 Testing individual servers...")
        
        servers = self.config_manager.load_server_configs()
        results = {}
        
        for server_name, server_config in servers.items():
            logger.info(f"🔍 Testing server: {server_name}")
            
            # Skip HTTP servers for now (they're handled differently)
            if server_config.get('transport') == 'streamable_http':
                results[server_name] = "SKIPPED (HTTP server)"
                continue
            
            # Test stdio servers
            if 'command' in server_config:
                try:
                    # Create a single server connection
                    single_connection = {
                        server_name: {
                            'command': server_config['command'],
                            'args': server_config.get('args', []),
                            'transport': 'stdio'
                        }
                    }
                    
                    # Add environment variables if present
                    if 'env' in server_config:
                        env_vars = {}
                        for key, value in server_config['env'].items():
                            if value.startswith('${') and value.endswith('}'):
                                env_var = value[2:-1]
                                env_vars[key] = os.getenv(env_var, '')
                            else:
                                env_vars[key] = value
                        single_connection[server_name]['env'] = env_vars
                    
                    # Try to create a client for just this server
                    test_client = MultiServerMCPClient(single_connection)
                    
                    # Try to get tools with a short timeout
                    tools = await asyncio.wait_for(test_client.get_tools(), timeout=10.0)
                    results[server_name] = f"✅ SUCCESS ({len(tools)} tools)"
                    logger.info(f"  ✅ {server_name}: {len(tools)} tools available")
                    
                except asyncio.TimeoutError:
                    results[server_name] = "❌ TIMEOUT (server not responding)"
                    logger.error(f"  ❌ {server_name}: Timeout")
                except Exception as e:
                    results[server_name] = f"❌ ERROR: {str(e)}"
                    logger.error(f"  ❌ {server_name}: {e}")
            else:
                results[server_name] = "SKIPPED (no command)"
        
        # Summary
        logger.info("📊 Individual server test results:")
        for server_name, result in results.items():
            logger.info(f"  {server_name}: {result}")
        
        return results

    async def close(self) -> None:
        """Close all connections and cleanup resources."""
        try:
            # Close HTTP agents
            for agent_name in self.http_agents:
                logger.info(f"Closing HTTP agent: {agent_name}")
        
            # MultiServerMCPClient doesn't need explicit closing in the current implementation
            # but we can add cleanup logic here if needed
            
            logger.info("All connections closed successfully")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


    def _extract_ai_message_content(self, response: Dict[str, Any]) -> Optional[str]:
        """
        Extract AI message content from agent response.
        
        Args:
            response: Agent response containing messages
            
        Returns:
            AI message content or None if not found
        """
        if not response.get('messages'):
            return None
            
        # Try different approaches to find AI message content
        messages = response['messages']
        
        # Approach 1: Look for the last message with content
        for msg in reversed(messages):
            # Handle LangChain message objects
            if hasattr(msg, 'content') and msg.content:
                return str(msg.content)
            
            # Handle dict-based messages
            elif isinstance(msg, dict) and msg.get('content'):
                # Skip tool calls, prefer final responses
                if not msg.get('tool_calls') and not msg.get('function_call'):
                    return str(msg['content'])
        
        # Approach 2: Look specifically for AI/assistant messages
        for msg in reversed(messages):
            if isinstance(msg, dict):
                msg_type = msg.get('type', '').lower()
                msg_role = msg.get('role', '').lower()
                
                if msg_type in ['ai', 'assistant'] or msg_role == 'assistant':
                    content = msg.get('content', '')
                    if content and not msg.get('tool_calls'):
                        return str(content)
        
        return None 

    def _log_tool_calls(self, response: Dict[str, Any], request_id: str = None) -> None:
        """
        Log which tools were called along with their server names.
        
        Args:
            response: Agent response containing messages with potential tool calls
            request_id: Optional request ID for enhanced logging
        """
        if not response.get('messages'):
            return
            
        tool_calls_found = []
        tool_responses_found = []
        
        for i, msg in enumerate(response['messages']):
            # Handle LangChain message objects
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tool_call in msg.tool_calls:
                    tool_name = getattr(tool_call, 'name', 'unknown')
                    tool_args = getattr(tool_call, 'args', {})
                    server_name = self._get_server_name_from_tool(tool_name)
                    
                    tool_calls_found.append({
                        'tool_name': tool_name,
                        'server_name': server_name,
                        'args': tool_args,
                        'message_index': i
                    })
                    
            # Handle dict-based messages
            elif isinstance(msg, dict):
                # Check for tool_calls in message
                if 'tool_calls' in msg and msg['tool_calls']:
                    for tool_call in msg['tool_calls']:
                        if isinstance(tool_call, dict):
                            tool_name = tool_call.get('name', 'unknown')
                            tool_args = tool_call.get('args', {})
                        else:
                            tool_name = getattr(tool_call, 'name', 'unknown')
                            tool_args = getattr(tool_call, 'args', {})
                            
                        server_name = self._get_server_name_from_tool(tool_name)
                        
                        tool_calls_found.append({
                            'tool_name': tool_name,
                            'server_name': server_name,
                            'args': tool_args,
                            'message_index': i
                        })
                
                # Check for function_call (alternative format)
                elif 'function_call' in msg and msg['function_call']:
                    func_call = msg['function_call']
                    tool_name = func_call.get('name', 'unknown')
                    tool_args = func_call.get('arguments', {})
                    server_name = self._get_server_name_from_tool(tool_name)
                    
                    tool_calls_found.append({
                        'tool_name': tool_name,
                        'server_name': server_name,
                        'args': tool_args,
                        'message_index': i
                    })
                
                # Check for tool responses
                elif msg.get('type') == 'tool' or 'tool_call_id' in msg:
                    tool_response = {
                        'tool_call_id': msg.get('tool_call_id', 'unknown'),
                        'name': msg.get('name', 'unknown'),
                        'content': str(msg.get('content', ''))[:200] + "..." if len(str(msg.get('content', ''))) > 200 else str(msg.get('content', '')),
                        'message_index': i
                    }
                    tool_responses_found.append(tool_response)
        
        # Enhanced logging with better formatting and request ID
        req_prefix = f"[{request_id}] " if request_id else ""
        
        if tool_calls_found:
            TOOL_ROUTING_LOG.info(f"🔧 {req_prefix}TOOL ROUTING ({len(tool_calls_found)} total calls):")
            
            # Group by server for better readability
            server_tools = {}
            for tool_call in tool_calls_found:
                server_name = tool_call['server_name']
                if server_name not in server_tools:
                    server_tools[server_name] = []
                server_tools[server_name].append(tool_call)
            
            # Log by server
            for server_name, tools in server_tools.items():
                server_display = server_name.upper() if server_name != 'unknown' else 'UNKNOWN SERVER'
                TOOL_ROUTING_LOG.info(f"  📡 {req_prefix}{server_display} ({len(tools)} tool(s)):")
                
                for idx, tool_call in enumerate(tools, 1):
                    args_preview = str(tool_call['args'])[:80] + "..." if len(str(tool_call['args'])) > 80 else str(tool_call['args'])
                    TOOL_ROUTING_LOG.info(f"    {idx}. 🛠️  {tool_call['tool_name']}")
                    if args_preview and args_preview != '{}':
                        TOOL_ROUTING_LOG.info(f"       📋 Args: {args_preview}")
        
        if tool_responses_found:
            TOOL_ROUTING_LOG.info(f"📋 {req_prefix}Tool responses received ({len(tool_responses_found)} total):")
            for idx, tool_response in enumerate(tool_responses_found, 1):
                response_preview = tool_response['content'][:100] + "..." if len(tool_response['content']) > 100 else tool_response['content']
                TOOL_ROUTING_LOG.info(f"  {idx}. ✅ {tool_response['name']} - Response: {response_preview}")
        
        if not tool_calls_found and not tool_responses_found:
            TOOL_ROUTING_LOG.info(f"💬 {req_prefix}DIRECT RESPONSE - No tools required")
        else:
            # Enhanced summary with Adobe-specific detection
            servers_used = list(set(tc['server_name'] for tc in tool_calls_found if tc['server_name'] != 'unknown'))
            tools_used = [tc['tool_name'] for tc in tool_calls_found]
            
            # Check for Adobe-related tools
            adobe_tools = [tool for tool in tools_used if any(keyword in tool.lower() for keyword in ['adobe', 'creative', 'photoshop'])]
            
            if servers_used:
                TOOL_ROUTING_LOG.info(f"📊 {req_prefix}ROUTING SUMMARY: {len(servers_used)} server(s) [{', '.join(servers_used)}] | {len(tools_used)} tool(s) [{', '.join(tools_used)}]")
                if adobe_tools:
                    TOOL_ROUTING_LOG.info(f"🎨 {req_prefix}Adobe-related tools used: {', '.join(adobe_tools)}")
            else:
                TOOL_ROUTING_LOG.info(f"⚠️  {req_prefix}ROUTING SUMMARY: {len(tools_used)} tool(s) from unknown servers")

    def _get_server_name_from_tool(self, tool_name: str) -> str:
        """
        Extract server name from tool name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Server name or 'unknown' if not found
        """
        # For HTTP agents (like Microsoft Docs)
        for agent_name in self.http_agents:
            if tool_name.startswith(agent_name) or agent_name in tool_name:
                return agent_name
        
        # Special handling for Microsoft Docs tools
        if 'microsoft' in tool_name.lower() or 'docs' in tool_name.lower():
            return 'microsoft_docs'
        
        # For MCP servers - tool names often contain server info
        if not self.mcp_client:
            return 'unknown'
        
        # Try to match with available servers
        available_servers = self.get_available_servers()
        for server_name in available_servers:
            # Check if server name is in tool name
            if server_name in tool_name or tool_name.startswith(server_name):
                return server_name
            
            # Check common patterns
            server_patterns = [
                f"{server_name}_",
                f"_{server_name}_",
                server_name.replace('_', '-'),
                server_name.replace('-', '_')
            ]
            
            for pattern in server_patterns:
                if pattern in tool_name:
                    return server_name
        
        # Try to extract from tool name patterns
        if '_' in tool_name:
            # Pattern like "weather_get_current" -> "weather"
            potential_server = tool_name.split('_')[0]
            if potential_server in available_servers:
                return potential_server
        
        return 'unknown' 

    def _extract_server_preference(self, user_input: str) -> Optional[str]:
        """Extract server preference from user input if specified"""
        import re
        
        # Look for [Server: server_name] pattern
        pattern = r'\[Server:\s*([^\]]+)\]'
        match = re.search(pattern, user_input, re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        return None
    
    def log_sample_prompt_test_start(self, prompt_text: str, prompt_category: str) -> str:
        """
        Log the start of a sample prompt test and return a test ID.
        
        Args:
            prompt_text: The sample prompt being tested
            prompt_category: Category of the prompt (e.g., "Sales Lead Pipeline", "Adobe Product Training")
            
        Returns:
            Test ID for tracking this specific test
        """
        test_id = f"test_{int(time.time() * 1000)}"
        test_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        SAMPLE_PROMPTS_LOG.info(f"🧪 [{test_id}] SAMPLE PROMPT TEST STARTED")
        SAMPLE_PROMPTS_LOG.info(f"📝 [{test_id}] Category: {prompt_category}")
        SAMPLE_PROMPTS_LOG.info(f"💬 [{test_id}] Prompt: {prompt_text}")
        SAMPLE_PROMPTS_LOG.info(f"⏰ [{test_id}] Started at: {test_timestamp}")
        
        return test_id
    
    def log_sample_prompt_test_result(self, test_id: str, success: bool, response_time: float, 
                                     tools_used: List[str], servers_used: List[str], 
                                     error_msg: str = None) -> None:
        """
        Log the result of a sample prompt test.
        
        Args:
            test_id: Test ID from log_sample_prompt_test_start
            success: Whether the test was successful
            response_time: Time taken for the response
            tools_used: List of tools that were used
            servers_used: List of servers that were used
            error_msg: Error message if test failed
        """
        status = "✅ PASSED" if success else "❌ FAILED"
        SAMPLE_PROMPTS_LOG.info(f"🧪 [{test_id}] SAMPLE PROMPT TEST {status}")
        SAMPLE_PROMPTS_LOG.info(f"⏱️  [{test_id}] Response time: {response_time:.2f}s")
        SAMPLE_PROMPTS_LOG.info(f"🛠️  [{test_id}] Tools used ({len(tools_used)}): {', '.join(tools_used)}")
        SAMPLE_PROMPTS_LOG.info(f"📡 [{test_id}] Servers used ({len(servers_used)}): {', '.join(servers_used)}")
        
        if error_msg:
            SAMPLE_PROMPTS_LOG.error(f"❌ [{test_id}] Error: {error_msg}")
        
        # Log performance category
        if response_time < 5.0:
            SAMPLE_PROMPTS_LOG.info(f"🚀 [{test_id}] Performance: EXCELLENT (< 5s)")
        elif response_time < 10.0:
            SAMPLE_PROMPTS_LOG.info(f"⚡ [{test_id}] Performance: GOOD (< 10s)")
        elif response_time < 20.0:
            SAMPLE_PROMPTS_LOG.info(f"⏰ [{test_id}] Performance: ACCEPTABLE (< 20s)")
        else:
            SAMPLE_PROMPTS_LOG.warning(f"🐌 [{test_id}] Performance: SLOW (> 20s)") 