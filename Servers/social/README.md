# Social Media MCP Servers

This directory contains MCP servers for social media analytics and content management, including YouTube video analysis and Twitter/X analytics capabilities.

## Servers Overview

### 📺 YouTube Server (`youtube.py`)
Advanced YouTube video analysis with transcript processing, comment analysis, and intelligent search functionality.

### 🐦 Twitter Analytics Server (`twitter_analytics_mcp.py`)
Twitter/X hashtag analytics, sentiment analysis, and social media monitoring capabilities.

---

## YouTube Server

### Features

#### 🔍 Intelligent Search & Intent Analysis
- **Tool**: `parse_search_intent`
- **Purpose**: Analyze user queries and extract search intent
- **Capabilities**: Determines if queries need clarification or can proceed to search
- **Smart routing**: Routes to appropriate search strategies based on intent

#### 📹 Video Search
- **Tool**: `search`
- **Purpose**: Search YouTube videos with optional channel filtering
- **Parameters**: Query, max results, channel filter
- **Returns**: Video titles, descriptions, URLs, and channel information

#### 📝 Transcript Analysis
- **Tool**: `get_transcript`
- **Purpose**: Extract and format video transcripts
- **Language support**: Prioritizes English, falls back to available languages
- **Error handling**: Graceful handling of unavailable transcripts

#### 💬 Comments Analysis
- **Tool**: `get_comments`
- **Purpose**: Retrieve top-level comments with engagement metrics
- **Data**: Author, text, like count, publish date
- **Sorting**: Returns most relevant/recent comments

#### 🤖 AI-Powered Video Analysis
- **Tool**: `analyze_video`
- **Purpose**: Comprehensive video analysis using LLM
- **Capabilities**: 
  - Content summarization
  - Comment sentiment analysis
  - Key theme identification
  - Engagement metrics analysis

#### 📊 Results Presentation
- **Tool**: `present_search_results`
- **Purpose**: Format and present search results according to user requirements
- **Smart formatting**: Adapts to user's specific format requests

### Configuration

Requires YouTube API key in environment:
```bash
YOUTUBE_API_KEY=your_youtube_api_key_here
```

### Usage Examples

```python
# Search for videos
await search("Adobe Photoshop tutorials", max_results=5)

# Get video transcript
await get_transcript("dQw4w9WgXcQ")

# Get video comments
await get_comments("dQw4w9WgXcQ", max_results=10)

# Analyze video content
await analyze_video("Summarize this tutorial", "dQw4w9WgXcQ", transcript="...", comments=[...])
```

### Example Queries
- "My Adobe Photoshop is crashing, provide me YouTube video resolution URLs"
- "Find tutorials for Lightroom photo editing"
- "Search for After Effects animation tutorials from Adobe channel"

---

## Twitter Analytics Server

### Features

#### 📊 Hashtag Tweet Fetching
- **Tool**: `fetch_hashtag_tweets`
- **Purpose**: Retrieve recent tweets for specific hashtags
- **Parameters**: Hashtag, max results
- **Returns**: Tweet text, user, timestamp

#### 😊 Sentiment Analysis
- **Tool**: `analyze_hashtag_sentiment`
- **Purpose**: Analyze sentiment distribution of tweets
- **Output**: Positive/neutral/negative counts with examples
- **Visualization**: Ready for chart/graph integration

#### 📈 Trend Summarization
- **Tool**: `summarize_hashtag_trends`
- **Purpose**: Extract trending topics and engagement metrics
- **Analysis**: Keywords, top users, engagement statistics
- **Insights**: Trend identification and user behavior patterns

#### 🔍 Social Pulse Analysis
- **Tool**: `get_hashtag_social_pulse`
- **Purpose**: Comprehensive hashtag analysis (combined tool)
- **Workflow**: Fetch → Analyze → Summarize
- **Output**: Complete social media intelligence report

### Usage Examples

```python
# Get social pulse for a hashtag
await get_hashtag_social_pulse("#adobe-photoshop", max_results=100)

# Analyze specific tweet sentiment
tweets = await fetch_hashtag_tweets("#design", 50)
sentiment = await analyze_hashtag_sentiment(tweets)

# Get trend summary
trends = await summarize_hashtag_trends(tweets)
```

### Example Queries
- "What's the social sentiment around #CreativeCloud?"
- "Analyze trending topics for #PhotoshopTips"
- "Get social media pulse for #AdobeMAX hashtag"

---

## Configuration

### YouTube Server Setup
1. Obtain YouTube Data API v3 key from Google Cloud Console
2. Set environment variable: `YOUTUBE_API_KEY`
3. Configure in `mcp_servers.json`:

```json
{
  "youtube": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "path/to/youtube.py"],
    "env": {
      "YOUTUBE_API_KEY": "${YOUTUBE_API_KEY}",
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8000"
    }
  }
}
```

### Twitter Server Setup
```json
{
  "twitter": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "path/to/twitter_analytics_mcp.py"],
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8009"
    }
  }
}
```

## Dependencies

### YouTube Server
- `google-api-python-client`: YouTube Data API client
- `youtube-transcript-api`: Transcript extraction
- `langchain-openai`: LLM integration for analysis
- `httpx`: HTTP client
- `mcp[cli]`: MCP framework

### Twitter Server
- `mcp[cli]`: MCP framework
- Future: Twitter API integration libraries

## AI Integration

Both servers integrate with Azure OpenAI for:
- **Intent Analysis**: Understanding user search intent
- **Content Analysis**: Video/tweet content summarization
- **Sentiment Analysis**: Emotion and opinion extraction
- **Trend Analysis**: Pattern recognition and insights

## Prompt Templates

### YouTube Analysis Prompt
Specialized for video content analysis:
- Content summarization
- Comment sentiment analysis
- Key theme identification
- User query-specific insights

### Search Intent Prompt
Determines if user queries are:
- Clear enough for search
- Need clarification
- Require specific formatting

## Error Handling

- **API Rate Limiting**: Graceful handling of quota limits
- **Missing Content**: Fallback when transcripts/comments unavailable
- **Network Issues**: Retry logic and timeout handling
- **Authentication**: Clear error messages for API key issues

## Future Enhancements

### YouTube Server
- Video recommendation algorithms
- Channel analytics
- Trending video tracking
- Content creator insights

### Twitter Server
- Real Twitter API integration
- Advanced sentiment models
- Influencer identification
- Real-time trend monitoring

---

*These social media servers provide comprehensive analytics and content discovery capabilities for YouTube and Twitter platforms.* 