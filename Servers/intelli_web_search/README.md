# Web Search, Scrape & RAG MCP Server

A comprehensive Model Context Protocol (MCP) server that performs intelligent web research using a 5-step process: query refinement, web search, content scraping, and AI-powered analysis to provide actionable solutions.

## 🎯 Overview

This server transforms user questions into comprehensive, actionable answers by:

1. **Query Analysis** - Understanding user intent and problem context
2. **Query Refinement** - Optimizing search terms using LLM (optional)
3. **Web Search** - Finding top 3 most relevant results via Google Custom Search API
4. **Content Scraping** - Extracting meaningful content from web pages
5. **Solution Generation** - Creating step-by-step solutions with source attribution

## ✨ Key Features

### 🔍 Intelligent Search
- **Google Custom Search API** - High-quality search results with reliable access
- **Site Filtering** - Restrict searches to specific domains (e.g., `learn.microsoft.com`)
- **Relevance Scoring** - Advanced ranking based on query matching
- **Retry Logic** - Automatic fallback with exponential backoff

### 📄 Content Processing
- **Smart Scraping** - Extracts meaningful content, filters out navigation/ads
- **Content Cleaning** - Removes noise and formats text properly
- **Timeout Protection** - Configurable timeouts to prevent hanging
- **Error Handling** - Graceful failure with informative messages

### 🧠 AI-Powered Analysis
- **Multi-Provider LLM Support** - Supports Azure OpenAI, OpenAI, Google Gemini, Claude, and Mistral
- **Structured Responses** - Consistent formatting with direct answers and step-by-step instructions
- **Source Attribution** - Automatic citation of all sources used
- **Fallback Summaries** - Works even when LLM is unavailable

### ⚡ Performance Modes
- **Fast Mode** (Default) - Quick results under 12 seconds for MCP timeouts
- **Full Mode** - Comprehensive analysis with LLM refinement and detailed scraping

## 🛠️ Setup

### Prerequisites

- Python 3.8+
- Google Custom Search API access and API key
- LLM provider access (Azure OpenAI, OpenAI, Google Gemini, Claude, or Mistral)
- Required Python packages (installed automatically):
  - `google-api-python-client`
  - `langchain-openai` (or other provider packages)
  - `beautifulsoup4`
  - `aiohttp`
  - `mcp`

### Environment Variables

Set these in your `.env` file:

```env
# Google Custom Search API Configuration (Required)
GOOGLE_API_KEY=your_google_api_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id

# LLM Configuration (Required - choose one or more providers)
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_api_key
AZURE_OPENAI_DEPLOYMENT=your_deployment_name

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Google Gemini
GOOGLE_API_KEY=your_google_api_key

# Claude
ANTHROPIC_API_KEY=your_claude_api_key

# Mistral
MISTRAL_API_KEY=your_mistral_api_key

# Optional: MCP Server Configuration
MCP_HOST=127.0.0.1
MCP_PORT=8009
```

### Google Custom Search Setup

1. **Create a Google Cloud Project**: Go to [Google Cloud Console](https://console.cloud.google.com/)
2. **Enable Custom Search API**: In the API Library, enable "Custom Search API"
3. **Create API Key**: Go to "Credentials" and create an API key
4. **Set up Custom Search Engine**: 
   - Visit [Google Custom Search](https://cse.google.com/)
   - Create a new search engine 
   - Note your search engine ID for the environment variable
5. **Add API Key to Environment**: Set `GOOGLE_API_KEY` and `GOOGLE_SEARCH_ENGINE_ID` in your `.env` file

### LLM Configuration

The server uses a centralized LLM factory that supports multiple providers. Configure your preferred LLM provider in `Servers/config/llm_config.json`:

```json
{
    "provider": "azureopenai",
    "model": "gpt-4o",
    "temperature": 0.5,
    "max_tokens": 4000,
    "max_retries": 3,
    "azure": {
        "deployment": "your_deployment_name",
        "api_version": "2024-02-15-preview",
        "api_key": "YOUR_AZURE_KEY",
        "endpoint": "YOUR_AZURE_ENDPOINT"
    },
    "openai": {
        "api_key": "YOUR_OPENAI_KEY"
    },
    "gemini": {
        "api_key": "YOUR_GEMINI_KEY"
    },
    "claude": {
        "api_key": "YOUR_CLAUDE_KEY"
    },
    "mistral": {
        "api_key": "YOUR_MISTRAL_KEY"
    }
}
```

**Supported Providers:**
- `azureopenai` - Azure OpenAI Service
- `openai` - OpenAI API
- `gemini` - Google Gemini
- `claude` - Anthropic Claude
- `mistral` - Mistral AI

The factory will automatically fall back to environment variables if config values are placeholders (`YOUR_*`).

### Installation

The server is automatically configured when you run the main MCP server. It's defined in `Servers/config/mcp_servers.json`:

```json
{
  "web_search_scrape_rag": {
    "command": "uv",
    "args": [
      "run",
      "--with",
      "mcp[cli]",
      "mcp",
      "run",
      "path/to/web_search_scrape_rag.py"
    ],
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8009"
    },
    "description": "Intelligent web search with scraping and RAG capabilities"
  }
}
```

## 🎯 Usage

### Intelligent Web Search

```python
# Simple query with AI analysis
result = await intelligent_web_search("How to create Azure App Service")

# With site filtering
result = await intelligent_web_search(
    "Azure security best practices",
    site_filter="learn.microsoft.com"
)

# Fast mode (default) - Quick results under 12s
result = await intelligent_web_search(
    query="Python async programming tutorial",
    fast_mode=True
)

# Full mode - Comprehensive LLM analysis (may take longer)
result = await intelligent_web_search(
    query="Machine learning deployment strategies",
    fast_mode=False
)
```

### Simple Web Search

```python
# Basic search without AI analysis
result = await simple_web_search("Python tutorials")

# With site filtering
result = await simple_web_search(
    "React best practices",
    site_filter="github.com"
)
```

### URL Analysis

```python
# Analyze a specific URL's content
result = await analyze_url("https://example.com/article")

# Different analysis types
result = await analyze_url(
    "https://docs.python.org/3/library/asyncio.html",
    analysis_type="summary"
)
```

## 📋 Tool Parameters

### `intelligent_web_search`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | Required | Your question or search query |
| `num_sources` | int | 3 | Number of sources to process (fixed at 3) |
| `fast_mode` | bool | `True` | Fast mode for quick results vs comprehensive analysis |
| `site_filter` | str | `None` | Optional domain filter (e.g., "stackoverflow.com") |

### `simple_web_search`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | Required | Your search query |
| `site_filter` | str | `None` | Optional domain filter (e.g., "github.com") |

### `analyze_url`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | Required | The URL to analyze |
| `analysis_type` | str | "content" | Type of analysis ("content", "summary", "structure") |

## 📊 Response Format

The server returns structured responses in this format:

```markdown
# ✅ Direct Answer

[One clear sentence answering the question]

## 🔧 Step-by-Step Instructions

1. [First specific action with exact details]
2. [Second action with button/menu names]
3. [Third action with precise options]

## ⚠️ Important Notes

• [Prerequisites or requirements]
• [Common mistakes to avoid]
• [Key things to remember]

## 💡 Quick Tips

• [Helpful shortcuts or best practices]
• [Alternative approaches]

---

## 🔍 Sources

- **[domain.com](https://example.com)**
- **[anotherdomain.com](https://example2.com)**
```

## ⚙️ Configuration

### Timeout Settings

```python
# Default timeouts (in seconds)
SCRAPE_TIMEOUT = 3        # Per-page scraping
SEARCH_TIMEOUT = 12       # Web search operation
OVERALL_TIMEOUT = 12      # Total operation timeout
QUERY_REFINE_TIMEOUT = 3  # LLM query refinement
SOLUTION_TIMEOUT = 5      # LLM solution generation
```

### Rate Limiting

```python
MAX_SEARCH_RETRIES = 2    # Number of retry attempts
RETRY_DELAY_BASE = 0.5    # Base delay between retries
RETRY_DELAY_MAX = 2       # Maximum retry delay
```

### Content Processing

```python
MAX_SEARCH_RESULTS = 3    # Fixed number of search results
MAX_CONTENT_LENGTH = 400000  # Maximum content length per page
```

## 🚀 Performance Modes

### Fast Mode (Default)
- **Query Refinement**: Skipped (uses original query)
- **Content Scraping**: First URL only
- **Solution Generation**: Simple summary without LLM
- **Timeout**: 8-12 seconds total
- **Use Case**: Quick answers, MCP timeout protection

### Full Mode
- **Query Refinement**: LLM-powered optimization
- **Content Scraping**: All 3 URLs
- **Solution Generation**: LLM analysis with detailed formatting
- **Timeout**: 15-20 seconds total
- **Use Case**: Comprehensive research, detailed analysis

## 🔧 Example Queries

### Technical Troubleshooting
```
"How to fix Docker container networking issues"
"Python memory leak debugging steps"
"Azure Function deployment errors"
```

### Learning & Documentation
```
"React hooks best practices" (site_filter="reactjs.org")
"Kubernetes deployment tutorial" (site_filter="kubernetes.io")
"AWS Lambda pricing model"
```

### Current Events & Research
```
"Latest AI developments 2024"
"Climate change impact studies"
"Cybersecurity trends analysis"
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Search Timeout Errors
```
Error: Search timed out after 12 seconds
```
**Solution**: Use `fast_mode=True` or check internet connection

#### 2. Rate Limiting
```
Error: DuckDuckGo rate limiting detected
```
**Solution**: Wait 30-60 seconds, then retry. Server has built-in retry logic.

#### 3. No Results Found
```
No search results found for your query
```
**Solutions**:
- Try broader, simpler terms
- Remove site filter if used
- Check for typos in query

#### 4. LLM Connection Issues
```
Error: LLM not available for solution generation
```
**Solution**: Check Azure OpenAI credentials and endpoint configuration

#### 5. Content Scraping Failures
```
Note: Content scraping was not available
```
**Cause**: Some websites block scraping or have complex structures
**Impact**: Server still provides search results with summaries

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
```

### Health Check

Test the server with a simple query:

```python
result = await intelligent_web_search("Python hello world", fast_mode=True)
```

## 📈 Best Practices

### Query Optimization
- **Be Specific**: "How to deploy React app to Vercel" vs "web deployment"
- **Include Context**: "Python async timeout handling" vs "timeout"
- **Use Site Filters**: For authoritative sources (docs, official sites)

### Mode Selection
- **Use Fast Mode**: For quick answers, MCP client integration
- **Use Full Mode**: For research, detailed analysis, complex queries

### Site Filtering
```python
# Documentation searches
site_filter="docs.microsoft.com"
site_filter="developer.mozilla.org"

# Community/Q&A
site_filter="stackoverflow.com"
site_filter="reddit.com"

# News/Updates
site_filter="techcrunch.com"
site_filter="news.ycombinator.com"
```

## 🔒 Security & Privacy

- **No Data Storage**: Queries and results are not stored
- **External Requests**: Only to DuckDuckGo search and target websites
- **Rate Limiting**: Respects website robots.txt and rate limits
- **User Agent**: Uses standard browser user agent for scraping

## 📄 API Reference

### Tool: `intelligent_web_search`

**Purpose**: Perform comprehensive web research with AI analysis

**Parameters**:
- `query` (str, required): Search query or question
- `num_sources` (int, optional): Fixed at 3 sources
- `fast_mode` (bool, optional): Default `True` for speed
- `site_filter` (str, optional): Domain restriction

**Returns**: Formatted markdown string with solution and sources

**Exceptions**:
- Timeout errors for long-running operations
- Search errors for connectivity issues
- Rate limiting errors (handled automatically)

## 🤝 Contributing

### Adding New Features

1. **Search Providers**: Add alternative search engines
2. **Content Extractors**: Improve scraping for specific sites
3. **Response Formats**: Add specialized formatting for different query types
4. **Caching**: Implement result caching for common queries

### Testing

Test with various query types:
- Technical how-to questions
- Current events queries
- Documentation searches
- Troubleshooting scenarios

## 📊 Monitoring

### Key Metrics
- **Success Rate**: Percentage of successful searches
- **Response Time**: Average time per query
- **Scraping Success**: Percentage of successful content extraction
- **LLM Usage**: Query refinement and solution generation calls

### Log Analysis
```bash
# Check for rate limiting issues
grep "rate limit" server.log

# Monitor timeout patterns
grep "timeout" server.log

# Track successful operations
grep "Step 5.*completed successfully" server.log
```

## 🔮 Roadmap

### Planned Features
- [ ] **Multiple Search Engines**: Bing, Google Custom Search
- [ ] **Content Caching**: Redis-based result caching
- [ ] **Advanced Filtering**: Date ranges, content types
- [ ] **Parallel Processing**: Concurrent scraping optimization
- [ ] **Custom Extractors**: Site-specific content extraction
- [ ] **Analytics Dashboard**: Usage metrics and performance monitoring

### Performance Improvements
- [ ] **Smart Timeouts**: Dynamic timeout adjustment
- [ ] **Connection Pooling**: Reuse HTTP connections
- [ ] **Result Ranking**: Machine learning-based relevance scoring
- [ ] **Progressive Loading**: Stream results as they become available

---

## 📞 Support

For issues, questions, or feature requests:
1. Check the troubleshooting section above
2. Enable debug logging for detailed error information
3. Test with simple queries to isolate issues
4. Review Azure OpenAI and DuckDuckGo service status

**Note**: This server is optimized for MCP client integration with fast response times and comprehensive error handling. 