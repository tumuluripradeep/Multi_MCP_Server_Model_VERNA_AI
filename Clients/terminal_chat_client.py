import asyncio
import sys

# Fix Windows asyncio subprocess issue
if sys.platform == "win32":
    # Set Windows-specific event loop policy
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import re,os
from urllib.parse import urlparse, parse_qs

# Add the parent directory to Python path to find ServerManager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ServerManager import ServerManager


# NOTE: ServerManager now loads all server configs from a single unified mcp_servers.json file.
# No need to specify or manage individual config files for each server.

# Add this wrapper class at the top of the file (after imports)
class DictSessionWrapper:
    def __init__(self, data):
        self.data = data
    def get_all_active_sessions(self):
        return {}
    def __getattr__(self, attr):
        # Fallback to dict attributes
        return getattr(self.data, attr, None)

def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    # Clean the input string
    url = url.strip()
    
    # If it's just the video ID (11 characters)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    # Handle youtu.be URLs
    if 'youtu.be' in url:
        try:
            return url.split('/')[-1].split('?')[0].split('&')[0]
        except:
            pass
    
    # Handle youtube.com URLs
    if 'youtube.com' in url:
        try:
            # Handle watch URLs
            if '/watch' in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if 'v' in query_params:
                    return query_params['v'][0]
            
            # Handle embed URLs
            if '/embed/' in url:
                return url.split('/embed/')[1].split('?')[0]
            
            # Handle /v/ URLs
            if '/v/' in url:
                return url.split('/v/')[1].split('?')[0]
                
            # Handle /shorts/ URLs
            if '/shorts/' in url:
                return url.split('/shorts/')[1].split('?')[0]
        except:
            pass
    
    # Try to find video ID in the text
    # This handles cases where the URL might be part of a longer text
    video_id_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(video_id_pattern, url)
    if match:
        return match.group(1)
    
    return None

async def handle_youtube_request(server_manager, user_input: str) -> None:
    """Handle YouTube-related requests."""
    video_id = extract_video_id(user_input)
    if not video_id:
        print("Could not find a valid YouTube video ID in your input.")
        print("Please provide a valid YouTube URL or video ID.")
        return
    
    print(f"Video ID: {video_id}")
    
    try:
        # Use the simplified approach - let ServerManager handle the YouTube request
        youtube_query = f"Analyze this YouTube video: {video_id}. {user_input}"
        
        print("Processing your request with the agent...")
        
        # Use process_request instead of route_to_server
        response = await server_manager.process_request(youtube_query)
        
        if response:
            print(f"\nAnalysis Results:\n{response}")
        else:
            print("Could not process the request. Please try again.")
            
    except Exception as e:
        print(f"Error processing request: {str(e)}")

async def handle_youtube_search(server_manager, user_input: str) -> None:
    """Handle YouTube search requests."""
    try:
        # Use the simplified approach - let ServerManager handle the YouTube search
        search_query = f"Search YouTube for: {user_input}"
        
        print("Searching YouTube and analyzing results...")
        
        # Use process_request instead of route_to_server
        response = await server_manager.process_request(search_query)
        
        if response:
            print(f"\nSearch Results:\n{response}")
        else:
            print("Could not analyze the search results. Please try again.")
    except Exception as e:
        print(f"Error during YouTube search: {str(e)}")

async def run_memory_chat():
    """Run a memory chat with the MCP agent."""
    
    # Initialize server manager
    server_manager = ServerManager()
    server_manager.initialize()
    await server_manager.warm_up_agent()
    if server_manager.streaming_enabled():
        print("🌊 Streaming enabled — responses will print token-by-token.")

    if not server_manager.get_available_servers():
        print("No servers were successfully initialized. Exiting...")
        return
    
    print("\nAvailable servers:")
    for server in server_manager.get_available_servers():
        print(f"- {server}")
    print("\nType 'exit' to quit or 'clear' to reset conversation history.")
    print("\nExample queries:")
    print("- Get the transcript of this video and summarize it: https://youtube.com/watch?v=...")
    print("- Analyze the sentiment of comments on this video: https://youtube.com/watch?v=...")
    print("- Get the engagement rate and top comments from this video: https://youtube.com/watch?v=...")
    print("- How to create a main form in Dynamics CRM?")
    print("- What are the best practices for Azure security?")
    print("- Find recent news about artificial intelligence developments")
    print("- How to troubleshoot network connectivity issues in Windows?")
    
    try:
        while True:
            try:
                user_input = input("\nYou: ").strip()
                
                # Handle empty input
                if not user_input:
                    continue
                
                # Handle special commands
                if user_input.lower() in ["exit", "quit"]:
                    print("Exiting the chat...")
                    break
                    
                if user_input.lower() in ["clear", "reset"]:
                    server_manager.clear_all_conversations()
                    print("Conversation history cleared.")
                    continue
                
                try:
                    print("Processing your request...", flush=True)
                    response = await server_manager.process_request(user_input)
                    print(f"\nResponse: {response}\n")
                    
                except Exception as e:
                    print(f"Error processing request: {e}")
                    print("Please try again or rephrase your query.")
                    
            except (EOFError, KeyboardInterrupt):
                print("\nExiting the chat...")
                break
            except Exception as e:
                print(f"\nUnexpected error: {e}")
                print("Please try again.")
                
    finally:
        try:
            await server_manager.close()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        print("Chat session ended.")
            
if __name__ == "__main__":
    try:
        asyncio.run(run_memory_chat())
    except KeyboardInterrupt:
        print("\nProgram terminated by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)