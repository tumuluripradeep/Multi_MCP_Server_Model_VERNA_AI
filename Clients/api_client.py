import os
import sys
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
# Add the parent directory to Python path to find ServerManager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ServerManager import ServerManager
from Servers.llm_factory import get_llm_from_config

load_dotenv()

app = FastAPI(title="MCP API Client", description="API to interact with MCP servers via FastAPI.")

# Allow CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    query: str
    server: str | None = None

# Initialize LLM and ServerManager on startup
llm = None
server_manager = None

@app.on_event("startup")
async def startup_event():
    global llm, server_manager
    llm = get_llm_from_config(streaming=True)
    if not llm:
        raise RuntimeError("Failed to create streaming LLM from config")
    server_manager = ServerManager()
    server_manager.initialize(llm=llm)
    await server_manager.warm_up_agent()
    diag = server_manager.get_streaming_diagnostics()
    print(f"API client ready: streaming={diag['streaming_enabled']} llm_streaming={diag['llm_streaming']}")

@app.get("/")
async def root():
    return {"message": "Welcome to the MCP API Client! Use /ask to interact with MCP servers."}

@app.post("/ask")
async def ask(request: AskRequest):
    if not server_manager:
        raise HTTPException(status_code=500, detail="ServerManager not initialized.")
    query = request.query
    server = request.server
    try:
        if not server:
            response = await server_manager.process_request(query)
            server = "auto-selected"
        else:
            query_with_server = f"[Server: {server}] {query}"
            response = await server_manager.process_request(query_with_server)
        return {"server": server, "response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {e}")


@app.post("/ask/stream")
async def ask_stream(request: AskRequest):
    """SSE stream of agent tokens (same event format as Chrome extension)."""
    if not server_manager:
        raise HTTPException(status_code=500, detail="ServerManager not initialized.")

    query = request.query
    if request.server:
        query = f"[Server: {request.server}] {query}"

    async def event_stream():
        try:
            async for event in server_manager.process_request_stream(query):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
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