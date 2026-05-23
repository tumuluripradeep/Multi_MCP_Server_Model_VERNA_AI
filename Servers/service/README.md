# Customer Service Case Management MCP Server

This MCP server provides comprehensive customer support case management capabilities, including case retrieval, resolution generation, problem analysis, and integration with both Dynamics 365 and vector search systems for intelligent support automation.

## Features

### 🎫 Case Management
- **Tool**: `handle_case_related_questions`
- **Purpose**: Handle all types of case-related queries with intelligent routing
- **AI Integration**: Automatic intent extraction and ticket number identification
- **Multi-source**: Integrates D365 data with vector search for comprehensive support

### 📋 Case Summary Generation
- **Tool**: `get_case_summary`
- **Purpose**: Generate concise summaries of support cases
- **Data Processing**: Extracts key information from case details
- **Localization**: Multi-language support for global operations

### 🔧 Resolution Generation  
- **Tool**: `get_resolution`
- **Purpose**: Generate step-by-step resolutions for support issues
- **Context-Aware**: Uses case data and knowledge base for targeted solutions
- **Integration**: Combines ticket data with vector search results

### 🔍 Case Search & Analysis
- **Tool**: `search_cases_by_query`
- **Purpose**: Find similar cases based on problem statements
- **AI-Powered**: Uses LLM to extract problem statements from queries
- **Similarity Matching**: Vector-based search for related issues

## Architecture

### Multi-Layer Support System
1. **Query Analysis**: LLM extracts intent, ticket numbers, and problem statements
2. **Data Retrieval**: Fetches case data from Dynamics 365 systems
3. **Knowledge Search**: Vector database search for relevant solutions
4. **Resolution Generation**: AI-powered resolution synthesis
5. **Response Formatting**: Human-friendly output generation

### Integration Points
- **Dynamics 365**: Primary case data source
- **Vector Database**: Knowledge base and solution repository
- **Azure OpenAI**: LLM processing for analysis and generation
- **Custom APIs**: Case summary and resolution services

## Configuration

### Environment Variables Required
```bash
# D365 Customer Service System
D365_API_BASE_URL=https://your-case-api.adobe.io/api/v1
D365_DYNAMICS_API_URL=https://your-org.api.crm.dynamics.com/api/data/v9.2
D365_TOKEN_URL=https://login.microsoftonline.com/your_tenant/oauth2/v2.0/token
D365_CLIENT_ID=your_client_id
D365_CLIENT_SECRET=your_client_secret
D365_SCOPE=https://your-org.crm.dynamics.com/.default

# LLM and Summary Services
SUMMARY_API_BASE_URL=https://aria-llm-dev.adobe.io/api/v1/llm
GENERATE_URL=https://aria-llm-dev.adobe.io/api/v1/llm/generate
```

### MCP Server Configuration
```json
{
  "service_system": {
    "name": "service_system_case",
    "description": "Handles all customer support, troubleshooting, and resolution...",
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "path/to/case_mcp.py"],
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8006"
    }
  }
}
```

## Tools Available

### 1. handle_case_related_questions
```python
# Intelligent case handling
await handle_case_related_questions("What's the status of ticket E-001234567?")
await handle_case_related_questions("Find similar cases to Photoshop crashing issue")
await handle_case_related_questions("Get resolution for installation error")
```

**Process Flow**:
1. Extract intent and ticket number from query
2. Retrieve case data if ticket number provided
3. Search for similar cases using vector search
4. Generate comprehensive response with context

### 2. get_case_summary
```python
# Generate case summaries
await get_case_summary("E-001234567", locale="en-US")
await get_case_summary("E-001234567", locale="es-ES")
```

**Returns**: Structured summary including:
- Case overview and priority
- Key issues and symptoms
- Actions taken
- Current status
- Next steps

### 3. get_resolution
```python
# Generate targeted resolutions
await get_resolution("Photoshop crashes on startup", ticketNumber="E-001234567")
await get_resolution("Installation fails with error 1603")  # General query
```

**Process Flow**:
1. Retrieve case data (if ticket provided)
2. Search knowledge base for relevant solutions
3. Generate step-by-step resolution
4. Include troubleshooting steps and verification

### 4. search_cases_by_query
```python
# Find similar support cases
await search_cases_by_query("Adobe Premiere Pro export issues", max_results=10)
await search_cases_by_query("Creative Cloud activation problems")
```

**Returns**: List of similar cases with:
- Case IDs and titles
- Problem descriptions
- Resolution status
- Similarity scores

## AI Integration

### LLM Configuration
- **Model**: Azure GPT-4o Mini
- **Temperature**: 0.2 (factual, consistent responses)
- **Max Tokens**: 1000
- **Timeout**: 60 seconds with retry logic

### Prompt Templates

#### Problem Statement Extraction
```
Extract the core problem statement from the user's query:

Your task is to identify the main technical problem or issue being described. Focus on:
1. The specific product or service mentioned
2. The specific issue or error
3. Any contextual details that help clarify the problem

Return ONLY the problem statement as a simple phrase for database searching.
```

#### Case Intent Extraction
```
Extract the intent and ticket number from the following user question.

Return a JSON object with:
- "intent": what the user wants to accomplish
- "ticket_number": extracted ticket number if present
```

## Usage Examples

### Example Queries
The server handles various types of support queries:

**Case Status Queries**:
- "What's the status of case E-001234567?"
- "Who is the support engineer for ticket E-987654321?"
- "When was case E-555666777 last updated?"

**Problem Resolution Queries**:
- "How do I fix Photoshop crashing on Windows 11?"
- "Get resolution for Creative Cloud installation error"
- "Help with Lightroom photo import issues"

**Case Search Queries**:
- "Find similar cases to Premiere Pro export problems"
- "Show me cases about Acrobat PDF printing issues"
- "Search for After Effects rendering errors"

### Response Examples

#### Case Status Response
```
📋 Case E-001234567 Status Update:

🔧 Support Engineer: Sarah Johnson (sarah.johnson@adobe.com)
📅 Last Updated: January 15, 2024, 2:30 PM PST
⚠️ Priority: High
📊 Status: In Progress

📝 Issue Summary:
Customer experiencing Photoshop crashes when opening large PSD files on Windows 11 system.

🔍 Recent Activity:
- Diagnostic logs received and analyzed
- Graphics driver compatibility checked
- Memory optimization recommendations provided
- Awaiting customer confirmation on fix effectiveness

📞 Next Steps:
- Follow-up scheduled for January 17, 2024
- Additional memory diagnostics if issue persists
```

#### Resolution Response
```
🔧 Resolution for Photoshop Startup Crashes:

📋 Problem: Adobe Photoshop crashes immediately upon startup

✅ Step-by-Step Solution:

1. **Reset Photoshop Preferences**
   - Hold Ctrl+Alt+Shift (Windows) while starting Photoshop
   - Click "Yes" when prompted to delete settings
   - Test if Photoshop starts normally

2. **Check Graphics Driver**
   - Update graphics drivers to latest version
   - Disable GPU acceleration temporarily (Edit > Preferences > Performance)

3. **Clear Font Cache**
   - Close all Adobe applications
   - Navigate to font cache folder and delete contents
   - Restart Photoshop

4. **Verify Installation**
   - Run Creative Cloud app as administrator
   - Use "Repair" option for Photoshop installation

🔍 Additional Resources:
- KB Article: PS-2024-001 "Startup Crash Troubleshooting"
- Video Tutorial: "Photoshop Won't Start - Complete Fix Guide"

⚡ Success Rate: 87% of users resolve the issue with these steps
```

## Error Handling

### Authentication & Access
- OAuth token refresh automation
- Graceful degradation when APIs unavailable
- Permission-based feature availability
- Secure credential management

### Data Processing
- Malformed case data handling
- Missing ticket number scenarios
- Network timeout recovery
- Vector search fallback options

### AI Processing
- LLM response validation
- JSON parsing error recovery
- Intent extraction failures
- Context length management

## Performance Optimization

### Caching Strategy
- Authentication token caching
- Frequently accessed case data
- Vector search result caching
- LLM response optimization

### Concurrent Processing
- Parallel API calls when possible
- Asynchronous data retrieval
- Background knowledge base updates
- Efficient resource utilization

## Integration Capabilities

### Vector Database Integration
- Seamless knowledge base access
- Hybrid search capabilities (vector + keyword)
- Relevance scoring and ranking
- Content source attribution

### Dynamics 365 Integration
- Real-time case data access
- Multi-entity relationship handling
- Advanced filtering and querying
- Bulk operation support

### External Systems
- **Power Automate**: Workflow automation
- **Power BI**: Analytics and reporting
- **Azure Monitor**: Performance tracking
- **Microsoft Graph**: Additional data sources

## Monitoring & Analytics

### Performance Metrics
- Response time tracking
- Success/failure rates
- User satisfaction scores
- Case resolution effectiveness

### Usage Analytics
- Query type distribution
- Most common problems
- Resolution success rates
- Knowledge base utilization

---

*This server provides intelligent customer service automation by combining real-time case data with AI-powered analysis and resolution generation.* 