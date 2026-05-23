"""
Microsoft Teams Listener
This file implements the Teams bot integration for listening to and sending messages in Teams channels.
"""

import os
import asyncio
import logging
import sys
from dotenv import load_dotenv
# Microsoft Bot Framework imports
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings, TurnContext, ConversationState, MemoryStorage
from botbuilder.schema import Activity, ActivityTypes
from aiohttp import web

# Add the parent directory to Python path to find ServerManager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ServerManager import ServerManager
from langchain_openai import AzureChatOpenAI

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()

APP_ID = os.environ.get("TEAMS_APP_ID")
APP_PASSWORD = os.environ.get("TEAMS_APP_PASSWORD")
PORT = int(os.environ.get("TEAMS_PORT", 3978))

if not APP_ID or not APP_PASSWORD:
    raise ValueError("Missing required Teams bot environment variables (TEAMS_APP_ID, TEAMS_APP_PASSWORD)")

# --- Bot Adapter Setup ---
SETTINGS = BotFrameworkAdapterSettings(APP_ID, APP_PASSWORD)
adapter = BotFrameworkAdapter(SETTINGS)

# Conversation state (in-memory for demo)
memory = MemoryStorage()
conversation_state = ConversationState(memory)

# --- MCP Server and LLM Setup ---
llm = AzureChatOpenAI(
    azure_deployment="ats-aria-gpt-4o",
    api_version="2024-02-15-preview",
    temperature=0.5,
    max_tokens=2000,
    max_retries=3
)
server_manager = ServerManager()
server_manager.initialize(llm=llm)

# --- Message Handler ---
async def on_message_activity(turn_context: TurnContext):
    user_message = turn_context.activity.text.strip()
    user_id = turn_context.activity.from_property.id
    channel_id = turn_context.activity.conversation.id
    logger.info(f"Received message from user {user_id} in channel {channel_id}: {user_message}")

    try:
        # Process the message using ServerManager (it will select appropriate server automatically)
        response = await server_manager.process_request(user_message)
        if not response:
            response = "No response from the server."
        await turn_context.send_activity(Activity(type=ActivityTypes.message, text=str(response)))
    except Exception as e:
        logger.error(f"Error processing Teams message: {e}")
        await turn_context.send_activity(Activity(type=ActivityTypes.message, text=f"Error: {str(e)}"))

# --- Main Bot Logic ---
async def messages(req):
    # Handle incoming requests from Teams
    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")

    async def aux_func(turn_context):
        if activity.type == ActivityTypes.message:
            await on_message_activity(turn_context)
        else:
            logger.info(f"Received non-message activity: {activity.type}")

    await adapter.process_activity(activity, auth_header, aux_func)
    return web.Response(status=201)

# --- App Entrypoint ---
def run_ms_teams_listener():
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    logger.info(f"Starting Microsoft Teams bot listener on port {PORT}...")
    web.run_app(app, port=PORT)

if __name__ == "__main__":
    run_ms_teams_listener() 