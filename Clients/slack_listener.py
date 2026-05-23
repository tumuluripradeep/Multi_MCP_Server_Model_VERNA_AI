import os
import json
import asyncio
import logging
import sys
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from dotenv import load_dotenv

# Add the parent directory to Python path to find ServerManager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ServerManager import ServerManager
from langchain_openai import AzureChatOpenAI
from urllib.parse import urlparse, parse_qs
import re

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Environment and Slack App Setup ---

# Load environment variables
load_dotenv()

# Get Slack configuration from environment variables
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')
SLACK_TEAM_ID = os.environ.get('SLACK_TEAM_ID')
SLACK_CHANNEL_IDS = os.environ.get('SLACK_CHANNEL_IDS')

if not all([SLACK_BOT_TOKEN, SLACK_APP_TOKEN, SLACK_TEAM_ID, SLACK_CHANNEL_IDS]):
    raise ValueError("Missing required Slack environment variables")

# Initialize Slack app (async)
app = AsyncApp(token=SLACK_BOT_TOKEN)

# Initialize LLM
llm = AzureChatOpenAI(
    azure_deployment="ats-aria-gpt-4o",
    api_version="2024-02-15-preview",
    temperature=0.5,
    max_tokens=2000,
    max_retries=3
)

# Initialize server manager
server_manager = ServerManager()
server_manager.initialize(llm=llm)

# --- Prompts and Constants ---

CONVERSATION_SUMMARY_PROMPT = """
Summarize the following Slack conversation in a concise, actionable, and visually organized way. 
Use bullet points, emojis, and short headlines for each key point, similar to a status update or executive summary.

Conversation:
{conversation_history}

Format:
- Each bullet should start with an emoji and a short headline.
- Use clear, direct language.
- Only include the most important issues, actions, and updates.

Summary:
"""

# --- Helper Functions ---

def build_feedback_blocks(main_text, dynamic_buttons=None):
    """Build Slack message blocks with feedback and optional dynamic action buttons."""
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": main_text}
        }
    ]
    actions = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "👍"},
            "value": "feedback_positive",
            "action_id": "feedback_positive"
        },
        {
            "type": "button",
            "text": {"type": "plain_text", "text": "👎"},
            "value": "feedback_negative",
            "action_id": "feedback_negative"
        }
    ]
    if dynamic_buttons:
        for btn in dynamic_buttons:
            actions.append({
                "type": "button",
                "text": {"type": "plain_text", "text": btn["text"]},
                "value": btn["value"],
                "action_id": btn["action_id"]
            })
    blocks.append({"type": "actions", "elements": actions})
    return blocks

def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    url = url.strip().strip('<>')
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    if 'youtu.be' in url:
        try:
            return url.split('/')[-1].split('?')[0].split('&')[0]
        except:
            pass
    if 'youtube.com' in url:
        try:
            if '/watch' in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if 'v' in query_params:
                    return query_params['v'][0]
            if '/embed/' in url:
                return url.split('/embed/')[1].split('?')[0]
            if '/v/' in url:
                return url.split('/v/')[1].split('?')[0]
            if '/shorts/' in url:
                return url.split('/shorts/')[1].split('?')[0]
        except:
            pass
    video_id_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(video_id_pattern, url)
    if match:
        return match.group(1)
    return None

# --- YouTube Handlers ---

async def handle_youtube_request_slack(server_manager, user_input: str, say, thread_ts):
    """Handle YouTube-related requests for Slack and send results to Slack."""
    video_id = extract_video_id(user_input)
    if not video_id:
        await say(
            text=("Could not find a valid YouTube video ID in your input. "
                  "Please provide a valid YouTube URL or video ID."),
            thread_ts=thread_ts
        )
        return
    
    await say(text=f"Video ID: {video_id}", thread_ts=thread_ts)
    
    try:
        # Use the simplified approach - let ServerManager handle the YouTube request
        youtube_query = f"Analyze this YouTube video: {video_id}. {user_input}"
        
        await say(text="Processing your request with the agent...", thread_ts=thread_ts)
        
        # Use process_request instead of route_to_server
        response = await server_manager.process_request(youtube_query, thread_ts=thread_ts)
        
        if response:
            dynamic_buttons = []
            if "jira" in response.lower():
                dynamic_buttons.append({
                    "text": "Escalate (Jira Ticket)",
                    "value": "jira_escalate",
                    "action_id": "jira_escalate"
                })
            if "crm" in response.lower():
                dynamic_buttons.append({
                    "text": "Create Dynamics CRM Case",
                    "value": "crm_create",
                    "action_id": "crm_create"
                })
            
            await say(
                blocks=build_feedback_blocks(f"*Analysis Results:*\n```\n{response}\n```", dynamic_buttons),
                thread_ts=thread_ts
            )
        else:
            await say(text="Could not process the request. Please try again.", thread_ts=thread_ts)
            
    except Exception as e:
        await say(text=f"Error processing request: {str(e)}", thread_ts=thread_ts)

async def handle_youtube_search_slack(server_manager, user_input: str, say, thread_ts):
    """Handle YouTube search requests for Slack."""
    try:
        # Use the simplified approach - let ServerManager handle the YouTube search
        search_query = f"Search YouTube for: {user_input}"
        
        await say(text="Searching YouTube and analyzing results...", thread_ts=thread_ts)
        
        # Use process_request instead of route_to_server
        response = await server_manager.process_request(search_query, thread_ts=thread_ts)
        
        if response:
            dynamic_buttons = []
            if "jira" in response.lower():
                dynamic_buttons.append({
                    "text": "Escalate (Jira Ticket)",
                    "value": "jira_escalate",
                    "action_id": "jira_escalate"
                })
            if "crm" in response.lower():
                dynamic_buttons.append({
                    "text": "Create Dynamics CRM Case",
                    "value": "crm_create",
                    "action_id": "crm_create"
                })
            await say(
                blocks=build_feedback_blocks(f"*Search Results:*\n```\n{response}\n```", dynamic_buttons),
                thread_ts=thread_ts
            )
        else:
            await say(text="Could not analyze the search results. Please try again.", thread_ts=thread_ts)
    except Exception as e:
        await say(text=f"Error during YouTube search: {str(e)}", thread_ts=thread_ts)

# --- Slack Event Handlers ---

@app.event("app_mention")
async def handle_app_mention(body, say):
    """Handle direct mentions of the bot in Slack."""
    logger.debug(f"Received app mention: {body}")
    await handle_message_events(body, say, None)

@app.event("message")
async def handle_message_events(body, say, client, logger):
    """Handle all message events in Slack channels."""
    event = body.get("event", {})
    channel_id = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")
    message_ts = event.get("ts")
    message_text = event.get("text", "")

    # Get bot user ID (cache it for efficiency)
    if not hasattr(handle_message_events, "bot_user_id"):
        auth_info = await client.auth_test()
        handle_message_events.bot_user_id = auth_info["user_id"]
    bot_user_id = handle_message_events.bot_user_id

    # Determine if this is the first message in the thread
    is_first_in_thread = (message_ts == thread_ts)

    # If not the first message in thread, only respond if bot is mentioned
    if not is_first_in_thread:
        if f"<@{bot_user_id}>" not in message_text:
            return  # Ignore unless bot is tagged

    # --- Begin main logic (use conversation_history as context) ---
    # Always fetch thread history
    conversation_history = []
    if thread_ts:
        try:
            history_response = await client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=20  # Adjust as needed
            )
            if history_response.get("ok"):
                conversation_history = [msg.get("text", "") for msg in history_response.get("messages", [])]
                logger.debug(f"Retrieved {len(conversation_history)} messages from thread history")
        except Exception as e:
            logger.warning(f"Could not fetch thread history: {e}")

    # Handle YouTube requests with search detection logic
    youtube_keywords = ['youtube', 'video', 'transcript', 'comments']
    is_youtube_request = any(keyword in message_text.lower() for keyword in youtube_keywords) or \
                        'youtube.com' in message_text or 'youtu.be' in message_text
    
    if is_youtube_request:
        search_keywords = ['search', 'find', 'look for', 'provide', 'get me', 'show me']
        is_search_current = any(keyword in message_text.lower() for keyword in search_keywords)
        has_url = 'youtube.com' in message_text or 'youtu.be' in message_text

        # Check if there was a recent YouTube search in thread history
        is_followup_to_search = False
        if conversation_history:
            for msg in conversation_history[-5:]:
                if any(keyword in msg.lower() for keyword in search_keywords) and 'youtube' in msg.lower():
                    is_followup_to_search = True
                    break
            for msg in conversation_history[-3:]:
                if "*Search Results:*" in msg or "Search query:" in msg:
                    is_followup_to_search = True
                    break

        # Determine search vs analysis
        if (is_search_current and not has_url) or (is_followup_to_search and not has_url):
            context_for_search = message_text
            if conversation_history and is_followup_to_search:
                recent_context = "\n".join(conversation_history[-3:])
                context_for_search = f"{recent_context}\n{message_text}"

            await handle_youtube_search_slack(server_manager, context_for_search, say, thread_ts)
        else:
            await handle_youtube_request_slack(server_manager, message_text, say, thread_ts)
        return

    # Handle general queries using process_request (simplified approach)
    try:
        logger.debug(f"Processing request: {message_text}")
        response = await server_manager.process_request(
            message_text, channel_id, thread_ts
        )
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        response = f"❌ Error processing your query: {str(e)}"
    
    if response:
        dynamic_buttons = []
        if "jira" in message_text.lower():
            dynamic_buttons.append({
                "text": "Escalate (Jira Ticket)",
                "value": "jira_escalate",
                "action_id": "jira_escalate"
            })
        if "crm" in message_text.lower():
            dynamic_buttons.append({
                "text": "Create Dynamics CRM Case",
                "value": "crm_create",
                "action_id": "crm_create"
            })
        await say(
            blocks=build_feedback_blocks(response, dynamic_buttons),
            thread_ts=thread_ts
        )
    
    # --- End main logic ---

# --- Main Entrypoint ---

async def main():
    """Start the Slack app in Socket Mode."""
    logger.info("Starting Slack app in Socket Mode...")
    handler = AsyncSocketModeHandler(app, SLACK_APP_TOKEN)
    await handler.start_async()
    logger.info("Slack app started successfully")

if __name__ == "__main__":
    asyncio.run(main()) 