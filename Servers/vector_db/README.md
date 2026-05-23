# Vector Database Search MCP Server

This MCP server provides intelligent content search capabilities using vector embeddings and hybrid search techniques. It serves as a knowledge base for case resolutions, documentation lookup, and semantic content discovery across multiple data sources.

## Features

### 🔍 Vector Search
- **Tool**: `get_relevant_content`
- **Purpose**: Search knowledge base using vector embeddings
- **Technology**: Semantic similarity matching
- **Context**: Case-aware search with problem statement extraction

### 🔀 Hybrid Search
- **Tool**: `get_relevant_content_hybrid`
- **Purpose**: Combined vector and keyword search for maximum coverage
- **A2A Integration**: Designed for agent-to-agent communication
- **Optimization**: Deduplication and relevance ranking

### 🧠 Problem Statement Extraction
- **Integration**: Automatic extraction from case descriptions
- **AI-Powered**: Uses LLM to identify core technical issues
- **Search Enhancement**: Converts verbose descriptions to focused queries

## Architecture

### Multi-Modal Search Strategy
1. **Problem Analysis**: Extract core issues from natural language
2. **Vector Search**: Semantic similarity using embeddings
3. **Keyword Search**: Traditional text matching for completeness
4. **Result Fusion**: Merge and deduplicate results
5. **Relevance Ranking**: Score and sort by similarity

### Data Sources
- **Knowledge Base**: Technical documentation and solutions
- **Case History**: Previous support cases and resolutions
- **Product Manuals**: Official documentation and guides
- **Community Content**: Forums, tutorials, and user-generated content

## Configuration

### Environment Variables
```bash
# Vector Search API
VECTOR_SEARCH_URL=https://aria-llm-stage.adobe.io/api/v1/agent/search

# Problem Statement Extraction
PROBLEM_STATEMENT_URL=https://aria-llm-dev.adobe.io/api/v1/llm/generate

# Keyword Search Endpoint (Optional)
KEYWORD_SEARCH_ENDPOINT=http://localhost:8080/api/v1/keyword_search
```

### MCP Server Configuration
```json
{
  "vector_search": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "path/to/vector_search.py"],
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8010"
    }
  }
}
```

## Tools Available

### 1. get_relevant_content
```python
# Search with case context
case_data = {"description": "Photoshop crashes when opening large files"}
await get_relevant_content("startup crash", case_data=case_data, locale="en-US")

# Direct search query
await get_relevant_content("installation error 1603", locale="en-US")
```

**Process Flow**:
1. If case data provided, extract problem statement using LLM
2. Perform vector search with enhanced query
3. Return ranked results with source attribution
4. Include metadata for relevance scoring

**Returns**:
```json
[
  {
    "text": "To resolve Photoshop startup crashes...",
    "source": "KB-PS-2024-001",
    "score": 0.89,
    "metadata": {
      "document_type": "troubleshooting_guide",
      "product": "Photoshop",
      "last_updated": "2024-01-15"
    }
  }
]
```

### 2. get_relevant_content_hybrid
```python
# Agent-to-agent search calls
await get_relevant_content_hybrid(
    query="Creative Cloud activation problems", 
    locale="en-US", 
    top_k=10
)
```

**Features**:
- **Dual Search**: Vector + keyword search in parallel
- **Deduplication**: Removes duplicate content across sources
- **Ranking**: Prioritizes vector results, supplements with keyword matches
- **A2A Optimized**: Designed for inter-agent communication

**Returns**: Enhanced results with comprehensive coverage

## Search Capabilities

### Vector Search Features
- **Semantic Understanding**: Finds conceptually similar content
- **Multi-language**: Supports multiple locales
- **Contextual Relevance**: Considers query context and intent
- **Embedding Models**: State-of-the-art transformer models

### Keyword Search Features
- **Exact Matching**: Traditional term-based search
- **Fuzzy Matching**: Handles typos and variations
- **Boolean Logic**: AND/OR/NOT operations
- **Phrase Matching**: Exact phrase identification

### Hybrid Search Benefits
- **Maximum Coverage**: Combines strengths of both approaches
- **Fallback Strategy**: Keyword search when vector search fails
- **Relevance Optimization**: Best results from both methods
- **Performance**: Parallel execution for speed

## AI Integration

### Problem Statement Extraction
Uses Azure GPT-4o Mini to convert case descriptions into focused search queries:

```
Input: "Customer reports that Adobe Photoshop 2024 crashes immediately when they try to open large PSD files over 500MB. This happens on Windows 11 with 16GB RAM."

Output: "Photoshop crashes large PSD files Windows 11"
```

### LLM Configuration
- **Model**: Azure GPT-4o Mini
- **Temperature**: 0 (deterministic extraction)
- **Max Tokens**: 4000
- **Timeout**: 30 seconds

## API Integration

### Vector Search API
```json
{
  "query_text": "Photoshop startup crash",
  "top_k": 5,
  "query_type": 2,
  "metadata": {
    "locale": "en-US"
  }
}
```

### Response Format
```json
{
  "results": [
    {
      "text": "Content text...",
      "score": 0.85,
      "metadata": {
        "source": "document_id",
        "section": "troubleshooting",
        "relevance": "high"
      }
    }
  ]
}
```

## Usage Examples

### Customer Service Integration
```python
# Case resolution workflow
case_description = "User cannot install Creative Cloud, error 1603"
relevant_docs = await get_relevant_content(
    query="installation error", 
    case_data={"description": case_description}
)

# Generate resolution using found content
resolution = await generate_resolution(relevant_docs, case_description)
```

### Knowledge Discovery
```python
# Find related documentation
results = await get_relevant_content_hybrid(
    query="After Effects rendering optimization",
    top_k=15
)

# Filter by content type
guides = [r for r in results if r['metadata'].get('type') == 'user_guide']
troubleshooting = [r for r in results if r['metadata'].get('type') == 'troubleshooting']
```

### Agent-to-Agent Communication
```python
# Marketing agent queries knowledge base
marketing_content = await get_relevant_content_hybrid(
    query="Creative Cloud subscription benefits",
    locale="en-US",
    top_k=5
)

# Use results for campaign content generation
campaign_copy = await generate_marketing_copy(marketing_content)
```

## Performance Optimization

### Caching Strategy
- **Query Results**: Cache frequent searches
- **Embeddings**: Store computed embeddings
- **API Responses**: Temporary caching for repeated calls
- **Metadata**: Cache document metadata for filtering

### Search Optimization
- **Parallel Processing**: Concurrent vector and keyword search
- **Result Streaming**: Progressive result delivery
- **Index Optimization**: Efficient vector index structures
- **Query Preprocessing**: Optimize queries before search

## Error Handling

### Network Issues
- **Timeout Handling**: Graceful timeout with fallback
- **Retry Logic**: Exponential backoff for transient failures
- **Circuit Breaker**: Prevent cascade failures
- **Offline Mode**: Local fallback when APIs unavailable

### Search Failures
- **Empty Results**: Fallback to broader queries
- **API Errors**: Alternative search methods
- **Malformed Queries**: Query sanitization and correction
- **Rate Limiting**: Request throttling and queuing

## Monitoring & Analytics

### Performance Metrics
- **Search Latency**: Response time tracking
- **Result Quality**: Relevance scoring analysis
- **Cache Hit Rates**: Efficiency measurements
- **Error Rates**: Failure monitoring

### Usage Analytics
- **Query Patterns**: Most common search terms
- **Result Utilization**: Which results get used
- **Source Popularity**: Most valuable content sources
- **Search Success**: Query satisfaction rates

## Integration Points

### Customer Service
- **Case Resolution**: Automated solution discovery
- **Knowledge Base**: Support article recommendations
- **Escalation**: Similar case identification
- **Training**: Agent knowledge enhancement

### Marketing
- **Content Discovery**: Relevant material for campaigns
- **Competitive Analysis**: Market intelligence
- **Product Information**: Feature and benefit content
- **Customer Insights**: Usage pattern analysis

### Sales
- **Product Information**: Technical specifications
- **Solution Matching**: Customer need alignment
- **Competitive Positioning**: Differentiation content
- **Proposal Support**: Relevant case studies

## Future Enhancements

### Advanced Features
- **Multi-modal Search**: Image and video content
- **Real-time Updates**: Dynamic index updates
- **Personalization**: User-specific result ranking
- **Federated Search**: Cross-system content discovery

### AI Improvements
- **Custom Embeddings**: Domain-specific models
- **Intent Classification**: Query type identification
- **Auto-completion**: Search suggestion system
- **Semantic Expansion**: Query enhancement strategies

---

*This server provides the foundation for intelligent content discovery and knowledge management across the entire MCP ecosystem.* 