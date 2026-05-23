import asyncio
import sys

# Fix Windows asyncio subprocess issue (MUST BE FIRST)
if sys.platform == "win32":
    # Set Windows-specific event loop policy
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
import json
import re
from urllib.parse import urlparse, parse_qs
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
import logging
import uuid
from datetime import datetime

# Add the parent directory to Python path to find ServerManager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ServerManager import ServerManager
from ServerManager.auth_manager import auth_manager

# Import LLM factory
from Servers.llm_factory import get_llm_from_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Verna AI Chrome Extension Client", 
              description="API bridge for Verna AI Chrome Extension to interact with MCP servers.")

# Allow CORS for Chrome extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Chrome extensions need this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed messages"""
    logger.error(f"Validation error for {request.url}: {exc}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body}
    )

# Data models
class ExtensionRequest(BaseModel):
    query: str
    server: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    tab_url: Optional[str] = None
    tab_title: Optional[str] = None
    page_content: Optional[str] = None
    selected_text: Optional[str] = None
    session_id: Optional[str] = None
    tab_id: Optional[str] = None
    youtube_video_id: Optional[str] = None
    auth_credentials: Optional[Dict[str, Any]] = None

class ExtensionResponse(BaseModel):
    success: bool
    server: Optional[str] = None
    response: Optional[str] = None
    error: Optional[str] = None
    request_id: str
    timestamp: str

# Global variables
llm = None
server_manager = None
active_connections: List[WebSocket] = []
request_history: List[Dict[str, Any]] = []

# Use centralized authentication manager
auth_manager_instance = auth_manager

def check_authentication(server_key: str, session_id: str = None) -> bool:
    """Check if a server requires authentication and if the session is authenticated"""
    return auth_manager_instance.is_authenticated(server_key, session_id)

def authenticate_session(server_key: str, session_id: str, credentials: Dict[str, Any]) -> bool:
    """Authenticate a session for a specific server"""
    return auth_manager_instance.authenticate_session(server_key, session_id, credentials)

def get_auth_config(server_key: str) -> Dict[str, Any]:
    """Get authentication configuration for a specific server"""
    return auth_manager_instance.get_server_config(server_key)

@app.on_event("startup")
async def startup_event():
    """Initialize the LLM and ServerManager on startup with improved error handling"""
    global llm, server_manager
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Initializing Verna AI Chrome Extension Client (attempt {attempt + 1}/{max_retries})...")
            
            # Initialize LLM using factory with fallback to direct initialization
            try:
                # First try the factory approach (if environment variables are set)
                llm = get_llm_from_config(streaming=True)
                if llm:
                    logger.info("✅ LLM initialized successfully using factory (streaming)")
                else:
                    # Fallback to direct initialization (same pattern as other clients)
                    logger.info("🔄 Factory initialization failed, trying direct initialization...")
                    try:
                        llm = AzureChatOpenAI(
                            azure_deployment="ats-aria-gpt-4o-mini",
                            api_version="2024-02-15-preview",
                            temperature=0.5,
                            max_tokens=2000,
                            max_retries=3,
                            streaming=True,
                        )
                        logger.info("✅ LLM initialized successfully using direct method")
                    except Exception as direct_error:
                        logger.error(f"Direct LLM initialization also failed: {direct_error}")
                        llm = None
                
                if not llm:
                    logger.error("Failed to initialize LLM using both factory and direct methods.")
                    logger.error("Please ensure you have set the Azure OpenAI credentials:")
                    logger.error("- Either set environment variables: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT")
                    logger.error("- Or ensure your Azure credentials are available through Azure CLI or other authentication methods")
                    
                    # Continue without LLM for now, but log the issue
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying LLM initialization in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        logger.warning("Starting without LLM - functionality will be limited")
                        llm = None
                        
            except Exception as llm_error:
                logger.error(f"LLM initialization error: {llm_error}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying LLM initialization in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    logger.warning("Starting without LLM - functionality will be limited")
                    llm = None
            
            # Initialize server manager (can work without LLM for some functionality)
            server_manager = ServerManager()
            
            # Try to initialize with LLM if available
            if llm:
                try:
                    server_manager.initialize(llm=llm)
                    available_servers = server_manager.get_available_servers()
                    
                    if available_servers:
                        logger.info(f"✅ Successfully initialized with {len(available_servers)} servers")
                        await server_manager.warm_up_agent()
                        if server_manager.streaming_enabled():
                            logger.info("🌊 Streaming enabled for Chrome extension (/api/query/stream)")
                        break
                    else:
                        logger.warning("No servers were successfully initialized")
                        if attempt < max_retries - 1:
                            logger.info(f"Retrying in {retry_delay} seconds...")
                            await asyncio.sleep(retry_delay)
                            continue
                        else:
                            logger.info("Starting with limited functionality")
                            break
                except Exception as server_init_error:
                    logger.error(f"ServerManager initialization error: {server_init_error}")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        logger.warning("Starting with limited functionality")
                        break
            else:
                logger.warning("Starting without LLM - only basic functionality available")
                break
                
        except Exception as e:
            logger.error(f"Failed to initialize (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Initialization failed after all retries")
                # Don't raise exception - allow app to start with limited functionality
                logger.info("Starting with limited functionality - some features may not work")
                break
    
    # Always log the final status
    if server_manager:
        try:
            available_servers = server_manager.get_available_servers()
            logger.info(f"Chrome Extension Client started with {len(available_servers) if available_servers else 0} servers")
        except:
            logger.info("Chrome Extension Client started with limited functionality")
    else:
        logger.warning("Chrome Extension Client started without ServerManager")

@app.get("/")
async def root():
    """Root endpoint - redirect to extension popup"""
    return {"message": "Verna AI Chrome Extension Client", "status": "running"}

@app.get("/extension-popup")
async def extension_popup():
    """Serve the extension popup HTML"""
    return HTMLResponse(content=_get_popup_html())

@app.post("/api/query", response_model=ExtensionResponse)
async def process_query(request: ExtensionRequest):
    """Process a query from the Chrome extension"""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    # Debug logging - log the incoming request details
    logger.info(f"Received request: {request.model_dump()}")
    logger.info(f"Selected text: '{request.selected_text}' (length: {len(request.selected_text or '')})")
    logger.info(f"Context: {request.context}")
    
    if not server_manager:
        return ExtensionResponse(
            success=False,
            error="ServerManager not initialized. Please check configuration and restart the client.",
            request_id=request_id,
            timestamp=timestamp
        )
    
    # Check if server manager has available servers
    try:
        available_servers = server_manager.get_available_servers()
        if not available_servers:
            logger.warning("No available servers, attempting to reinitialize server manager")
            if llm:
                try:
                    # Try to reinitialize the server manager
                    server_manager.initialize(llm=llm)
                    available_servers = server_manager.get_available_servers()
                    if not available_servers:
                        return ExtensionResponse(
                            success=False,
                            error="No MCP servers are available. Please check server configuration and environment variables.",
                            request_id=request_id,
                            timestamp=timestamp
                        )
                except Exception as e:
                    logger.error(f"Failed to reinitialize server manager: {e}")
                    return ExtensionResponse(
                        success=False,
                        error=f"Server initialization failed: {str(e)}",
                        request_id=request_id,
                        timestamp=timestamp
                    )
            else:
                return ExtensionResponse(
                    success=False,
                    error="No LLM available and no servers initialized. Please check your configuration.",
                    request_id=request_id,
                    timestamp=timestamp
                )
    except Exception as e:
        logger.error(f"Error checking available servers: {e}")
        return ExtensionResponse(
            success=False,
            error=f"Error checking server availability: {str(e)}",
            request_id=request_id,
            timestamp=timestamp
        )
    
    try:
        # Enhanced query with context from the browser
        enhanced_query = _build_enhanced_query(request)
        logger.info(f"Enhanced query: {enhanced_query}")
        logger.info(f"Context flags - Include selected text: {request.context.get('includeSelectedText', True) if request.context else True}, Include page content: {request.context.get('includePageContent', True) if request.context else True}")
        
        # Process request with session context for conversation continuity
        # Ensure we pass valid strings or None for session parameters
        channel_id = request.session_id if request.session_id else None
        thread_ts = request.tab_id if request.tab_id else None
        
        # Check if user specified a server
        if request.server:
            # Check authentication before processing using centralized auth manager
            if not check_authentication(request.server, channel_id):
                # Handle authentication for specific server
                if request.auth_credentials:
                    # Attempt to authenticate with provided credentials
                    if authenticate_session(request.server, channel_id, request.auth_credentials):
                        logger.info(f"Successfully authenticated for server {request.server}")
                    else:
                        return ExtensionResponse(
                            success=False,
                            error=f"Authentication failed for {request.server}. Please check your credentials.",
                            request_id=request_id,
                            timestamp=timestamp
                        )
                else:
                    # Authentication required but no credentials provided
                    auth_config = get_auth_config(request.server)
                    return ExtensionResponse(
                        success=False,
                        error=f"Authentication required for {auth_config.get('display_name', request.server)}. Please authenticate first.",
                        request_id=request_id,
                        timestamp=timestamp,
                        server=request.server
                    )
                
                # Include server preference in the query for process_request
                enhanced_query_with_server = f"[Server: {request.server}] {enhanced_query}"
                response = await server_manager.process_request(
                    enhanced_query_with_server,
                    channel_id=channel_id,
                    thread_ts=thread_ts
                )
                server = request.server
            else:
                # Include server preference in the query for process_request
                enhanced_query_with_server = f"[Server: {request.server}] {enhanced_query}"
                response = await server_manager.process_request(
                    enhanced_query_with_server,
                    channel_id=channel_id,
                    thread_ts=thread_ts
                )
                server = request.server
        else:
            # Let ServerManager select the best server and handle conversation context
            response = await server_manager.process_request(
                enhanced_query,
                channel_id=channel_id,  # Use session_id as channel_id for conversation context
                thread_ts=thread_ts  # Use tab_id as thread_ts for tab-specific conversations
            )
            server = "auto-selected"
        
        # Store in history
        request_history.append({
            "request_id": request_id,
            "timestamp": timestamp,
            "query": request.query,
            "server": server,
            "tab_url": request.tab_url,
            "tab_title": request.tab_title,
            "response": response[:200] + "..." if len(str(response)) > 200 else response
        })
        
        # Broadcast to connected WebSocket clients
        await _broadcast_to_websockets({
            "type": "query_response",
            "request_id": request_id,
            "server": server,
            "query": request.query,
            "response": response
        })
        
        return ExtensionResponse(
            success=True,
            server=server,
            response=response,
            request_id=request_id,
            timestamp=timestamp
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        return ExtensionResponse(
            success=False,
            error=str(e),
            request_id=request_id,
            timestamp=timestamp
        )


@app.post("/api/query/stream")
async def process_query_stream(request: ExtensionRequest):
    """Stream agent tokens via Server-Sent Events (used by Chrome extension)."""
    if not server_manager:
        async def err_stream():
            yield f"data: {json.dumps({'type': 'error', 'content': 'ServerManager not initialized'})}\n\n"
        return StreamingResponse(err_stream(), media_type="text/event-stream")

    enhanced_query = _build_enhanced_query(request)
    channel_id = request.session_id if request.session_id else None
    thread_ts = request.tab_id if request.tab_id else None
    if request.server:
        enhanced_query = f"[Server: {request.server}] {enhanced_query}"

    async def event_stream():
        try:
            async for event in server_manager.process_request_stream(
                enhanced_query,
                channel_id=channel_id,
                thread_ts=thread_ts,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error("SSE stream failed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/servers")
async def get_available_servers(session_id: str = None):
    """Get list of available MCP servers with authentication status"""
    if not server_manager:
        return {"servers": [], "error": "ServerManager not initialized"}
    
    try:
        servers = server_manager.get_available_servers()
        server_info = {}
        
        for server in servers:
            try:
                capabilities = server_manager.get_server_capabilities(server)
                auth_config = get_auth_config(server)
                is_authenticated = check_authentication(server, session_id) if session_id else False
                
                server_info[server] = {
                    "name": server,
                    "capabilities": capabilities,
                    "status": "active",
                    "auth_config": auth_config,
                    "is_authenticated": is_authenticated
                }
            except Exception as e:
                server_info[server] = {
                    "name": server,
                    "capabilities": "Unable to retrieve",
                    "status": "error",
                    "error": str(e),
                    "auth_config": get_auth_config(server),
                    "is_authenticated": False
                }
        
        return {"servers": server_info}
    except Exception as e:
        logger.error(f"Error getting servers: {e}")
        return {"servers": [], "error": str(e)}

@app.get("/api/history")
async def get_request_history(limit: int = 50):
    """Get request history"""
    return {"history": request_history[-limit:]}

@app.post("/api/auth/login")
async def login_to_server(server: str, session_id: str, credentials: Dict[str, Any]):
    """Authenticate to a specific server using centralized auth manager"""
    if not server:
        return {"success": False, "error": "Server name is required"}
    
    if not session_id:
        return {"success": False, "error": "Session ID is required"}
    
    auth_config = get_auth_config(server)
    if not auth_config.get("requires_auth", False):
        return {"success": True, "message": f"No authentication required for {server}"}
    
    if authenticate_session(server, session_id, credentials):
        return {
            "success": True, 
            "message": f"Successfully authenticated to {auth_config.get('display_name', server)}"
        }
    else:
        return {
            "success": False, 
            "error": f"Authentication failed for {auth_config.get('display_name', server)}"
        }

@app.post("/api/auth/logout")
async def logout_from_server(server: str, session_id: str):
    """Logout from a specific server using centralized auth manager"""
    if not server or not session_id:
        return {"success": False, "error": "Server name and session ID are required"}
    
    if auth_manager_instance.logout_session(server, session_id):
        return {"success": True, "message": f"Successfully logged out from {server}"}
    else:
        return {"success": True, "message": f"Already logged out from {server}"}

@app.get("/api/auth/status")
async def get_auth_status(session_id: str):
    """Get authentication status for all servers using centralized auth manager"""
    if not session_id:
        return {"error": "Session ID is required"}
    
    auth_status = auth_manager_instance.get_auth_status(session_id)
    return {"auth_status": auth_status}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    active_connections.append(websocket)
    
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now - can be enhanced for specific functionality
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info("WebSocket connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if websocket in active_connections:
            active_connections.remove(websocket)

# Mount static files for Chrome extension resources
if os.path.exists("Clients/chrome_extension"):
    app.mount("/extension", StaticFiles(directory="Clients/chrome_extension"), name="extension")

# YouTube helper functions (from terminal_chat_client.py)
def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats"""
    if not url:
        return ""
    
    # Handle different YouTube URL formats
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$"  # Direct video ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return ""

def _build_enhanced_query(request: ExtensionRequest) -> str:
    """Build enhanced query with context from browser"""
    
    # Detect navigation intents that should be kept simple
    navigation_keywords = ['navigate to', 'go to', 'visit', 'open', 'browse to', 'load']
    is_navigation_intent = any(keyword in request.query.lower() for keyword in navigation_keywords)
    
    # Detect other playwright automation intents
    playwright_keywords = ['screenshot', 'click', 'type', 'scroll', 'wait', 'automate', 'browser']
    is_playwright_intent = any(keyword in request.query.lower() for keyword in playwright_keywords)
    
    # Detect content analysis intents
    content_analysis_keywords = ['summarize', 'summary', 'analyze', 'analysis', 'extract', 'key points', 'main content', 'content breakdown', 'insights', 'what is this page about']
    is_content_analysis_intent = any(keyword in request.query.lower() for keyword in content_analysis_keywords)
    
    query_parts = []
    
    # For navigation or playwright intents, keep it simple and explicit
    if is_navigation_intent or is_playwright_intent:
        # Add explicit server routing for playwright commands
        if not request.query.startswith('[Server:'):
            query_parts.append(f"[Server: playwright] {request.query}")
        else:
            query_parts.append(request.query)
        
        # For navigation, only add minimal context
        if is_navigation_intent:
            return "\n".join(query_parts)
        
        # For other playwright commands, add current URL as context if relevant
        if request.tab_url and not is_navigation_intent:
            query_parts.append(f"Current Page: {request.tab_url}")
    
    # For content analysis intents, provide explicit tool usage instructions
    elif is_content_analysis_intent and request.page_content and request.page_content.strip():
        # Build explicit content analysis query with tool instructions
        query_parts.append(f"Use the content_summarize_page tool to {request.query.lower()}")
        query_parts.append(f"Page Title: {request.tab_title or 'Not provided'}")
        query_parts.append(f"Page URL: {request.tab_url or 'Not provided'}")
        
        # Include the full page content for the tool
        content = request.page_content.strip()
        if len(content) > 5000:  # Increased limit for summarization
            content = content[:5000] + "..."
        query_parts.append(f"Page Content to Analyze: {content}")
        
        # Add selected text if available and relevant
        if request.selected_text and request.selected_text.strip():
            query_parts.append(f"Selected Text: {request.selected_text}")
            
        # Add explicit instruction
        query_parts.append("IMPORTANT: Use the provided page content above with the content_summarize_page tool. Do not try to browse or access any URLs directly.")
        
    else:
        # For non-playwright queries, use the full enhanced context as before
        # Start with the main query
        query_parts.append(request.query)
        
        # Add YouTube video ID if present
        if request.youtube_video_id:
            query_parts.append(f"YouTube Video ID: {request.youtube_video_id}")
        
        # Respect context flags from the Chrome extension frontend
        include_selected_text = True
        include_page_content = True
        
        if request.context:
            include_selected_text = request.context.get("includeSelectedText", True)
            include_page_content = request.context.get("includePageContent", True)
            
            # Add other context information (but not the flags themselves)
            context_items = {k: v for k, v in request.context.items() 
                            if k not in ["includeSelectedText", "includePageContent"]}
            if context_items:
                context_str = ", ".join([f"{k}: {v}" for k, v in context_items.items()])
                query_parts.append(f"Context: {context_str}")
        
        # Add selected text only if requested and present
        if include_selected_text and request.selected_text and request.selected_text.strip():
            query_parts.append(f"Selected Text: {request.selected_text}")
        
        # Add page context if present
        if request.tab_url:
            query_parts.append(f"Page URL: {request.tab_url}")
        
        if request.tab_title:
            query_parts.append(f"Page Title: {request.tab_title}")
        
        # Add page content only if requested and present (truncated to avoid excessive length)
        if include_page_content and request.page_content and request.page_content.strip():
            content = request.page_content.strip()
            if len(content) > 1000:
                content = content[:1000] + "..."
            query_parts.append(f"Page Content: {content}")
    
    return "\n".join(query_parts)

async def _broadcast_to_websockets(message: Dict[str, Any]):
    """Broadcast message to all connected WebSocket clients"""
    if not active_connections:
        return
    
    disconnected = []
    for websocket in active_connections:
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error broadcasting to websocket: {e}")
            disconnected.append(websocket)
    
    # Remove disconnected clients
    for websocket in disconnected:
        active_connections.remove(websocket)

def _get_popup_html() -> str:
    """Get the popup HTML for the extension"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Verna AI Chrome Extension</title>
        <style>
            body {
                width: 400px;
                padding: 20px;
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                margin: 0;
            }
            .container {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                padding: 20px;
                backdrop-filter: blur(10px);
            }
            h1 {
                text-align: center;
                margin-bottom: 20px;
                font-size: 24px;
            }
            .status {
                text-align: center;
                margin-bottom: 15px;
                padding: 10px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 5px;
            }
            .info {
                background: rgba(255, 255, 255, 0.1);
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 15px;
            }
            .info h3 {
                margin-top: 0;
                color: #ffd700;
            }
            .info p {
                margin: 5px 0;
                font-size: 14px;
            }
            .button {
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                width: 100%;
                font-size: 16px;
                margin-top: 10px;
            }
            .button:hover {
                background: #45a049;
            }
            .error {
                background: rgba(255, 0, 0, 0.3);
                color: white;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 15px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Verna AI</h1>
            <div class="status">
                <strong>Chrome Extension Client</strong>
            </div>
            <div class="info">
                <h3>📊 Status</h3>
                <p>✅ Server Running</p>
                <p>🔗 WebSocket Ready</p>
                <p>🧠 AI Agent Active</p>
            </div>
            <div class="info">
                <h3>🚀 Features</h3>
                <p>• Multi-server AI assistance</p>
                <p>• Context-aware responses</p>
                <p>• Real-time communication</p>
                <p>• Secure authentication</p>
            </div>
            <div class="info">
                <h3>🔧 Usage</h3>
                <p>Use the extension popup to interact with Verna AI directly from any webpage!</p>
            </div>
            <button class="button" onclick="window.open('/extension/popup.html', '_blank')">
                Open Extension Interface
            </button>
        </div>
    </body>
    </html>
    """

@app.get("/api/health")
async def health_check():
    """Check the health of the server manager and available servers"""
    try:
        if not server_manager:
            return {
                "status": "error",
                "message": "ServerManager not initialized",
                "available_servers": []
            }
        
        available_servers = server_manager.get_available_servers()
        
        # Test connectivity using process_request
        test_results = {}
        if available_servers:
            try:
                # Simple connectivity test using process_request
                response = await server_manager.process_request("Health check - please respond with server status")
                test_results["general"] = "connected" if response else "no_response"
            except Exception as e:
                test_results["general"] = f"error: {str(e)}"
        
        return {
            "status": "ok" if available_servers else "limited",
            "message": f"ServerManager initialized with {len(available_servers)} servers",
            "available_servers": available_servers,
            "test_results": test_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "available_servers": [],
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/diagnose/{server_name}")
async def diagnose_server(server_name: str):
    """Diagnose issues with a specific server"""
    if not server_manager:
        return {
            "status": "error",
            "message": "ServerManager not initialized",
            "server": server_name
        }
    
    try:
        # Get server capabilities first
        capabilities = None
        available_tools = []
        
        if server_name == "playwright":
            try:
                capabilities = server_manager.get_server_capabilities(server_name)
                # Try to get available tools for Playwright server
                test_tools_query = f"[Server: {server_name}] What tools are available? List all available browser automation tools."
                tools_response = await server_manager.process_request(test_tools_query)
                
                available_tools = str(tools_response) if tools_response else "No tools response"
            except Exception as e:
                logger.warning(f"Could not get capabilities for {server_name}: {e}")
        
        # Test the server with a simple query that includes server preference
        test_query = f"[Server: {server_name}] Health check for {server_name} - please respond with status"
        response = await server_manager.process_request(test_query)
        
        diagnostic_info = {
            "server_requested": server_name,
            "test_query": test_query,
            "response_received": bool(response),
            "response_length": len(str(response)) if response else 0,
            "response_preview": str(response)[:200] + "..." if response and len(str(response)) > 200 else str(response),
            "capabilities": capabilities,
            "available_tools": available_tools
        }
        
        return {
            "status": "ok",
            "server": server_name,
            "diagnostic_info": diagnostic_info,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Diagnostic failed for {server_name}: {e}")
        return {
            "status": "error",
            "server": server_name,
            "message": f"Diagnostic failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/debug/playwright-response")
async def debug_playwright_response():
    """Debug what Playwright server actually returns"""
    if not server_manager:
        return {"error": "ServerManager not initialized"}
    
    try:
        # Test exact command that's failing
        debug_command = "[Server: playwright] Execute link testing: Navigate to 'https://example.com', find all links on the page, test each link's HTTP status, measure response times, and report broken links."
        
        logger.info(f"Debug command: {debug_command}")
        response = await server_manager.process_request(debug_command)
        
        return {
            "command_sent": debug_command,
            "raw_response": str(response),
            "response_type": type(response).__name__,
            "response_length": len(str(response)),
            "contains_execution_keywords": any(keyword in str(response).lower() for keyword in [
                'navigated', 'executed', 'completed', 'screenshot', 'links tested', 'status code'
            ]),
            "contains_instruction_keywords": any(keyword in str(response).lower() for keyword in [
                'create a script', 'you can', 'below is a sample', 'const page', 'await page'
            ]),
            "available_servers": server_manager.get_available_servers(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Debug failed: {e}")
        return {
            "error": f"Debug failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/test/playwright")
async def test_playwright_execution():
    """Test Playwright server with actual execution commands"""
    if not server_manager:
        return {"error": "ServerManager not initialized"}
    
    try:
        # Test different command formats to find what works
        test_commands = [
            # Test 1: Direct tool calls (most likely to work)
            "[Server: playwright] Use browser_navigate to go to https://httpbin.org/get then use browser_take_screenshot",
            
            # Test 2: MCP tool call style
            "[Server: playwright] Call browser_navigate with url=https://example.com then call browser_snapshot",
            
            # Test 3: Natural language with tool names
            "[Server: playwright] Navigate to https://example.com using browser_navigate and capture using browser_take_screenshot",
            
            # Test 4: Simple tool request
            "[Server: playwright] browser_navigate https://httpbin.org/links/3 then browser_snapshot"
        ]
        
        results = []
        for i, command in enumerate(test_commands):
            try:
                logger.info(f"Testing Playwright command {i+1}: {command}")
                response = await server_manager.process_request(command)
                
                # More detailed response analysis
                response_str = str(response).lower()
                is_execution = any(indicator in response_str for indicator in [
                    'navigated to', 'screenshot taken', 'page loaded', 'browser opened',
                    'links found', 'status code', 'response time', 'executed successfully',
                    'automation completed', 'task completed'
                ])
                is_instructions = any(indicator in response_str for indicator in [
                    'create a script', 'you can', 'below is a sample', 'here\'s how',
                    'follow these steps', 'to automate', 'script that performs',
                    'const page', 'await page.goto', 'function'
                ])
                
                results.append({
                    "command": command,
                    "success": bool(response),
                    "response_type": "execution" if is_execution else ("instructions" if is_instructions else "unclear"),
                    "response_length": len(str(response)),
                    "response_preview": str(response)[:300] + "..." if len(str(response)) > 300 else str(response),
                    "full_response": str(response)  # Include full response for debugging
                })
            except Exception as e:
                results.append({
                    "command": command,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "playwright_server_status": "tested",
            "total_commands": len(test_commands),
            "results": results,
            "available_servers": server_manager.get_available_servers() if server_manager else [],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Playwright test failed: {e}")
        return {
            "error": f"Playwright test failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/playwright/automate")
async def playwright_automate(request: ExtensionRequest):
    """Use Playwright to automate actions based on Chrome extension context"""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    if not server_manager:
        return ExtensionResponse(
            success=False,
            error="ServerManager not initialized",
            request_id=request_id,
            timestamp=timestamp
        )
    
    try:
        # Build automation query with explicit Playwright execution commands
        action_type = request.context.get('action', 'general') if request.context else 'general'
        
        # Map actions to specific Playwright execution commands
        playwright_commands = {
            'screenshot': f"[Server: playwright] Take a screenshot of {request.tab_url}. Navigate to the page and capture a full page screenshot.",
            'fillForm': f"[Server: playwright] Navigate to {request.tab_url} and automatically fill out all forms on the page with appropriate test data.",
            'extractData': f"[Server: playwright] Navigate to {request.tab_url} and extract all structured data including tables, lists, links, prices, and contact information.",
            'testLinks': f"[Server: playwright] Navigate to {request.tab_url} and test all links on the page. Check each link's status, response time, and identify broken links.",
            'compare': f"[Server: playwright] Navigate to {request.tab_url}, extract product/service information, then search and compare with competitors.",
            'monitor': f"[Server: playwright] Navigate to {request.tab_url}, take baseline screenshots, and set up monitoring for content changes."
        }
        
        # Use specific command or fallback to general automation
        automation_query = playwright_commands.get(action_type, f"[Server: playwright] Navigate to {request.tab_url} and {request.query}")
        
        # Add context if available
        if request.selected_text:
            automation_query += f"\n\nSelected text context: {request.selected_text}"
        
        if request.page_content and len(request.page_content) > 0:
            automation_query += f"\n\nPage content preview: {request.page_content[:300]}..."
        
        # Process through server manager - it will route to appropriate Playwright server
        response = await server_manager.process_request(
            automation_query,
            channel_id=request.session_id,
            thread_ts=request.tab_id
        )
        
        return ExtensionResponse(
            success=True,
            server="playwright",
            response=response,
            request_id=request_id,
            timestamp=timestamp
        )
        
    except Exception as e:
        logger.error(f"Playwright automation error: {e}")
        return ExtensionResponse(
            success=False,
            error=str(e),
            request_id=request_id,
            timestamp=timestamp
        )

@app.post("/api/playwright/screenshot")
async def playwright_screenshot(request: ExtensionRequest):
    """Take a screenshot of the current or specified page using Playwright"""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    try:
        screenshot_query = f"[Server: playwright] Navigate to {request.tab_url} and take a full page screenshot."
        
        response = await server_manager.process_request(screenshot_query)
        
        return ExtensionResponse(
            success=True,
            server="playwright",
            response=response,
            request_id=request_id,
            timestamp=timestamp
        )
        
    except Exception as e:
        logger.error(f"Screenshot error: {e}")
        return ExtensionResponse(
            success=False,
            error=str(e),
            request_id=request_id,
            timestamp=timestamp
        )

@app.post("/api/playwright/execute")
async def playwright_execute(request: ExtensionRequest):
    """Execute specific Playwright commands directly"""
    request_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    if not server_manager:
        return ExtensionResponse(
            success=False,
            error="ServerManager not initialized",
            request_id=request_id,
            timestamp=timestamp
        )
    
    try:
        action_type = request.context.get('action', 'general') if request.context else 'general'
        
        # Direct tool call commands for Playwright MCP
        direct_commands = {
            'testLinks': f"[Server: playwright] Use the browser_navigate tool to go to {request.tab_url}, then use browser_snapshot to get page content, then test all links on the page for HTTP status.",
            'screenshot': f"[Server: playwright] Use browser_navigate to go to {request.tab_url}, then use browser_take_screenshot to capture the page.",
            'extractData': f"[Server: playwright] Use browser_navigate to go to {request.tab_url}, then use browser_snapshot to extract all structured data from the page.",
            'fillForm': f"[Server: playwright] Use browser_navigate to go to {request.tab_url}, then use browser_snapshot to identify forms, then use browser_type and browser_click to fill forms.",
            'compare': f"[Server: playwright] Use browser_navigate to go to {request.tab_url}, extract product info, then navigate to competitor sites for comparison.",
            'monitor': f"[Server: playwright] Use browser_navigate to go to {request.tab_url}, then use browser_take_screenshot for monitoring baseline."
        }
        
        # Force Playwright server execution
        execution_query = direct_commands.get(action_type, f"[Server: playwright] Execute: {request.query} on {request.tab_url}")
        
        logger.info(f"Executing Playwright command: {execution_query}")
        
        # Process with explicit server targeting
        response = await server_manager.process_request(
            execution_query,
            channel_id=request.session_id,
            thread_ts=request.tab_id
        )
        
        return ExtensionResponse(
            success=True,
            server="playwright",
            response=response,
            request_id=request_id,
            timestamp=timestamp
        )
        
    except Exception as e:
        logger.error(f"Playwright execution error: {e}")
        return ExtensionResponse(
            success=False,
            error=str(e),
            request_id=request_id,
            timestamp=timestamp
        )

if __name__ == "__main__":
    import uvicorn
    
    # Try different ports if 8001 is occupied
    import socket
    
    def is_port_available(port):
        """Check if a port is available"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False
    
    ports_to_try = [8001, 8011, 8021, 8031, 8041]
    port = None
    
    # Find an available port
    for try_port in ports_to_try:
        if is_port_available(try_port):
            port = try_port
            logger.info(f"✅ Port {port} is available")
            break
        else:
            logger.warning(f"⚠️  Port {try_port} is already in use")
    
    if port is None:
        logger.error(f"❌ No available ports found in: {ports_to_try}")
        logger.error(f"💡 Kill existing processes with: python kill_ports.py")
        sys.exit(1)
    
    # Start server on the available port
    try:
        logger.info(f"🚀 Starting Chrome Extension Client on port {port}...")
        logger.info(f"🌐 Access at: http://localhost:{port}")
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        sys.exit(1) 