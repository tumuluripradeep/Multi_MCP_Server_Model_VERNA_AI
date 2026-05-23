from googleapiclient.discovery import build
import os
from youtube_transcript_api import YouTubeTranscriptApi
from langchain_openai import AzureChatOpenAI
import asyncio
import logging
import sys
import json
from typing import Any
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Configure logging to stderr to avoid interfering with MCP JSON protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# =============================
# Load Environment Variables
# =============================
load_dotenv()

# Initialize the MCP server
logger.info("Initializing YouTube MCP server...")
mcp = FastMCP("youtube")

YOUTUBE_ANALYSIS_PROMPT = """You are a YouTube video analysis assistant. Analyze the following video data based on the user's request.

User Query: {user_query}

Video ID: {video_id}
Transcript Language: {transcript_language}

Transcript:
{transcript}

Comments:
{comments}

Please analyze this data and provide insights based on the user's request. Focus on:
- Summarizing the content if transcript is available
- Analyzing comment sentiment and engagement
- Identifying key themes or topics
- Providing relevant statistics or metrics

Your analysis should be clear, concise, and directly address the user's query.
"""

SEARCH_INTENT_PROMPT = """Extract the core problem statement from the user's request for YouTube search:

User Input: {user_input}

Analyze if the user's intent is clear enough to perform a search. Look for:
1. A specific problem or issue they're facing
2. A clear search topic
3. Enough context to understand what they want

If the intent IS CLEAR, return a JSON object with:
- "query": the core problem statement
- "channel_filter": specific channel name if mentioned (null if not)
- "intent": what type of solution they're looking for
- "needs_clarification": false

If the intent IS NOT CLEAR or ambiguous, return:
- "needs_clarification": true
- "clarification_questions": ["question1", "question2", ...]

Examples of CLEAR intents:
Input: "My Adobe Photoshop is crashing, please provide me youtube video resolution url's"
Output: {{"query": "Adobe Photoshop crashing", "channel_filter": null, "intent": "solution videos", "needs_clarification": false}}

Examples of UNCLEAR intents that need clarification:
Input: "Help me with my computer"
Output: {{"needs_clarification": true, "clarification_questions": ["What specific issue are you having with your computer?", "What type of computer problem are you experiencing?"]}}

Input: "Find video"
Output: {{"needs_clarification": true, "clarification_questions": ["What topic would you like to find videos about?", "What specific subject or problem do you want help with?"]}}
"""

RESULTS_PRESENTATION_PROMPT = """Present YouTube search results based on user's request and intent.

User Request: {user_input}
Search Query: {search_query}
Channel Filter: {channel_filter}
User Intent: {intent}

Search Results:
{results}

Instructions:
- Follow the user's specific formatting requirements (e.g., "2 points", "numbered list", etc.)
- Focus on videos that directly address the problem stated in the search query
- Prioritize credible channels and recent videos
- Include direct YouTube URLs for each recommended video
- If the user asked for resolution/solution URLs, emphasize videos that provide step-by-step fixes

Present the results in the exact format requested by the user.
"""

# Initialize YouTube API client and LLM
def get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("YOUTUBE_API_KEY not found in environment variables")
        raise ValueError("YOUTUBE_API_KEY not found in environment variables")
    return build('youtube', 'v3', developerKey=api_key)

def get_llm():
    return AzureChatOpenAI(
        azure_deployment="ats-aria-gpt-4o-mini",
        api_version="2024-02-15-preview",
        temperature=0.5,
        max_tokens=2000,
        max_retries=3
    )

@mcp.tool()
async def youtube_search_youtube(query: str, max_results: int = 10, channel_filter: str = None) -> str:
    """
    Search YouTube videos based on a query.
    
    Args:
        query (str): The search query for YouTube videos.
        max_results (int): Maximum number of results to return (default: 10).
        channel_filter (str): Optional channel name to filter results.
        
    Returns:
        str: A JSON string containing search results with video details.
    """
    logger.info(f"youtube_search_youtube called with query: {query}, max_results: {max_results}, channel_filter: {channel_filter}")
    
    try:
        youtube = get_youtube_client()
        
        # Modify query if channel filter is provided
        search_query = query
        if channel_filter:
            search_query = f"{query} channel:{channel_filter}"
        
        search_response = youtube.search().list(
            q=search_query,
            part='id,snippet',
            maxResults=max_results,
            type='video'
        ).execute()
        
        videos = []
        for item in search_response.get('items', []):
            video = {
                'title': item['snippet']['title'],
                'description': item['snippet']['description'],
                'video_id': item['id']['videoId'],
                'url': f'https://www.youtube.com/watch?v={item["id"]["videoId"]}',
                'channel': item['snippet']['channelTitle'],
                'published_at': item['snippet']['publishedAt']
            }
            videos.append(video)
        
        logger.info(f"Found {len(videos)} videos for query: {query}")
        return json.dumps({'results': videos}, indent=2)
        
    except Exception as e:
        logger.error(f"Error searching YouTube: {str(e)}")
        return json.dumps({'error': f'Search failed: {str(e)}'})

@mcp.tool()
async def youtube_get_video_transcript(video_id: str) -> str:
    """
    Get the transcript of a YouTube video.
    
    Args:
        video_id (str): The YouTube video ID.
        
    Returns:
        str: A JSON string containing the video transcript and language information.
    """
    logger.info(f"youtube_get_video_transcript called with video_id: {video_id}")
    
    try:
        # Create an instance of YouTubeTranscriptApi
        ytt_api = YouTubeTranscriptApi()
        
        # First, check if transcripts are available for this video
        transcript_list = ytt_api.list(video_id)
        
        # Get available transcript languages
        available_languages = [t.language_code for t in transcript_list]
        
        # Try to find the best transcript
        transcript = None
        try:
            # Try English first
            transcript = transcript_list.find_transcript(['en'])
        except:
            try:
                # Try US English
                transcript = transcript_list.find_transcript(['en-US'])
            except:
                try:
                    # Try any available transcript
                    transcript = next(iter(transcript_list))
                except:
                    logger.warning(f"No transcripts available for video: {video_id}")
                    return json.dumps({
                        'error': 'No transcripts available for this video',
                        'video_id': video_id,
                        'available_languages': available_languages
                    })
        
        # Fetch the transcript data
        transcript_data = transcript.fetch()
        formatted_transcript = '\n'.join([item.text for item in transcript_data])
        
        result = {
            'video_id': video_id,
            'language': transcript.language,
            'language_code': transcript.language_code,
            'transcript': formatted_transcript,
            'available_languages': available_languages
        }
        
        logger.info(f"Successfully retrieved transcript for video: {video_id}")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error getting transcript for video {video_id}: {str(e)}")
        error_msg = str(e).lower()
        
        # Provide more specific error messages
        if 'no element found' in error_msg or 'could not retrieve' in error_msg:
            error_response = {
                'error': 'This video does not have transcripts available. The video may be private, deleted, or the creator has disabled transcripts.',
                'video_id': video_id
            }
        elif 'video unavailable' in error_msg:
            error_response = {
                'error': 'Video is unavailable. It may have been removed or set to private.',
                'video_id': video_id
            }
        elif 'invalid video id' in error_msg:
            error_response = {
                'error': 'Invalid video ID provided.',
                'video_id': video_id
            }
        else:
            error_response = {
                'error': f'Failed to get transcript: {str(e)}',
                'video_id': video_id
            }
        
        return json.dumps(error_response)

@mcp.tool()
async def youtube_get_video_comments(video_id: str, max_results: int = 10) -> str:
    """
    Get comments for a YouTube video.
    
    Args:
        video_id (str): The YouTube video ID.
        max_results (int): Maximum number of comments to return (default: 10).
        
    Returns:
        str: A JSON string containing video comments.
    """
    logger.info(f"youtube_get_video_comments called with video_id: {video_id}, max_results: {max_results}")
    
    try:
        youtube = get_youtube_client()
        
        comments_response = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=max_results,
            textFormat='plainText'
        ).execute()
        
        comments = []
        for item in comments_response.get('items', []):
            comment = {
                'author': item['snippet']['topLevelComment']['snippet']['authorDisplayName'],
                'text': item['snippet']['topLevelComment']['snippet']['textDisplay'],
                'like_count': item['snippet']['topLevelComment']['snippet']['likeCount'],
                'published_at': item['snippet']['topLevelComment']['snippet']['publishedAt']
            }
            comments.append(comment)
        
        result = {
            'video_id': video_id,
            'comments': comments
        }
        
        logger.info(f"Successfully retrieved {len(comments)} comments for video: {video_id}")
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error getting comments for video {video_id}: {str(e)}")
        return json.dumps({'error': f'Failed to get comments: {str(e)}'})

@mcp.tool()
async def youtube_analyze_video_content(user_query: str, video_id: str, transcript: str = "", 
                              transcript_language: str = "", comments: str = "") -> str:
    """
    Analyze YouTube video content using AI based on transcript and comments.
    
    Args:
        user_query (str): The user's query about the video.
        video_id (str): The YouTube video ID.
        transcript (str): The video transcript text.
        transcript_language (str): The language of the transcript.
        comments (str): The video comments as JSON string.
        
    Returns:
        str: AI analysis of the video content.
    """
    logger.info(f"analyze_video_content called for video: {video_id}")
    
    try:
        llm = get_llm()
        
        # Parse comments if provided as JSON string
        comments_list = []
        if comments:
            try:
                comments_data = json.loads(comments)
                comments_list = comments_data.get('comments', [])
            except:
                # If not JSON, treat as plain text
                comments_list = []
        
        # Format comments for analysis
        formatted_comments = '\n'.join([
            f"{i+1}. {c['author']}: {c['text']} (Likes: {c['like_count']}, Posted: {c['published_at']})"
            for i, c in enumerate(comments_list)
        ]) if comments_list else 'No comments available.'
        
        prompt = YOUTUBE_ANALYSIS_PROMPT.format(
            user_query=user_query,
            video_id=video_id,
            transcript_language=transcript_language,
            transcript=transcript,
            comments=formatted_comments
        )
        
        response = await llm.ainvoke(prompt)
        analysis = response.content if hasattr(response, 'content') else str(response)
        
        logger.info(f"Successfully analyzed video content for: {video_id}")
        return analysis
        
    except Exception as e:
        logger.error(f"Error analyzing video content: {str(e)}")
        return f"Error analyzing video content: {str(e)}"

@mcp.tool()
async def youtube_parse_search_intent(user_input: str) -> str:
    """
    Parse user input to extract search intent and determine if clarification is needed.
    
    Args:
        user_input (str): The user's input request.
        
    Returns:
        str: A JSON string containing parsed intent or clarification questions.
    """
    logger.info(f"youtube_parse_search_intent called with input: {user_input}")
    
    try:
        llm = get_llm()
        prompt = SEARCH_INTENT_PROMPT.format(user_input=user_input)
        response = await llm.ainvoke(prompt)
        
        # Extract JSON from response
        content = response.content if hasattr(response, 'content') else str(response)
        start = content.find('{')
        end = content.rfind('}') + 1
        
        if start >= 0 and end > start:
            result = json.loads(content[start:end])
            logger.info("Successfully parsed search intent")
            return json.dumps(result, indent=2)
        else:
            # If we can't parse JSON, assume clarification is needed
            logger.warning("Could not parse JSON from LLM response")
            return json.dumps({
                'needs_clarification': True,
                'clarification_questions': ["Could you please provide more details about what you're looking for?"]
            })
            
    except Exception as e:
        logger.error(f"Error parsing search intent: {str(e)}")
        # If parsing fails, ask for clarification instead of proceeding
        return json.dumps({
            'needs_clarification': True,
            'clarification_questions': ["I'm not sure I understand your request. Could you please be more specific about what you're looking for?"]
        })

@mcp.tool()
async def youtube_present_search_results(user_input: str, search_query: str, channel_filter: str = "", 
                               results: str = "", intent: str = "general search") -> str:
    """
    Present YouTube search results in a formatted way based on user intent.
    
    Args:
        user_input (str): The original user input.
        search_query (str): The extracted search query.
        channel_filter (str): Optional channel filter.
        results (str): Search results as JSON string.
        intent (str): The user's intent (default: "general search").
        
    Returns:
        str: Formatted presentation of search results.
    """
    logger.info(f"present_search_results called for query: {search_query}")
    
    try:
        llm = get_llm()
        
        # Parse results if provided as JSON string
        results_list = []
        if results:
            try:
                results_data = json.loads(results)
                results_list = results_data.get('results', [])
            except:
                logger.warning("Could not parse results JSON")
        
        # Format results for the prompt
        formatted_results = []
        for i, result in enumerate(results_list, 1):
            formatted_results.append(
                f"{i}. {result['title']}\n"
                f"   Channel: {result['channel']}\n"
                f"   URL: {result['url']}\n"
                f"   Description: {result['description'][:100]}...\n"
            )
        
        results_text = '\n'.join(formatted_results)
        
        prompt = RESULTS_PRESENTATION_PROMPT.format(
            user_input=user_input,
            search_query=search_query,
            channel_filter=channel_filter or 'None',
            intent=intent,
            results=results_text
        )
        
        response = await llm.ainvoke(prompt)
        presentation = response.content if hasattr(response, 'content') else str(response)
        
        logger.info("Successfully presented search results")
        return presentation
        
    except Exception as e:
        logger.error(f"Error presenting search results: {str(e)}")
        return f"Error presenting search results: {str(e)}"

@mcp.resource("youtube://video/{video_id}")
def video_resource(video_id: str) -> str:
    """
    Resource for accessing YouTube video information.
    """
    return f"YouTube video resource: {video_id}"

@mcp.prompt("youtube_analysis_prompt")
def youtube_analysis_prompt(query: str, video_id: str) -> str:
    """
    A prompt for analyzing YouTube video content.
    """
    return f"Analyze the YouTube video {video_id} based on this query: {query}"

if __name__ == "__main__":
    logger.info("Starting YouTube MCP server...")
    mcp.run(transport='streamable-http') 