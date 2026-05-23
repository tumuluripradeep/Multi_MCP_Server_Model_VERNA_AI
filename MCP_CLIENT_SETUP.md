# MCP Client Setup Guide

This guide explains how to set up and use the MCP (Message Control Protocol) client system with `MultiServerMCPClient` for managing multiple MCP servers on different ports.

## Overview

The system consists of:
- **Terminal Chat Client** - Interactive CLI interface using MultiServerMCPClient
- **Streamlit Web UI** - Web-based interface for MCP servers
- **Server Management Scripts** - Tools to start, stop, and monitor MCP servers
- **Test Scripts** - Utilities to verify server health and integration

## Quick Start

### 1. Environment Setup

First, ensure you have the required environment variables set in your `.env` file:

```bash
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=your_azure_openai_endpoint
AZURE_OPENAI_API_KEY=your_azure_openai_api_key

# YouTube API (if using YouTube server)
YOUTUBE_API_KEY=your_youtube_api_key

# Slack Integration (if using Slack server)
SLACK_BOT_TOKEN=your_slack_bot_token
SLACK_APP_TOKEN=your_slack_app_token
SLACK_TEAM_ID=your_slack_team_id
SLACK_CHANNEL_IDS=your_slack_channel_ids

# Atlassian Integration (if using Atlassian server)
CONFLUENCE_URL=your_confluence_url
CONFLUENCE_PERSONAL_TOKEN=your_confluence_token
JIRA_URL=your_jira_url
JIRA_PERSONAL_TOKEN=your_jira_token
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start MCP Servers

Use the server management script to start all servers:

```bash
# List available servers
python run_mcp_servers.py list

# Start all servers
python run_mcp_servers.py start-all

# Or start individual servers
python run_mcp_servers.py start youtube
python run_mcp_servers.py start weather
python run_mcp_servers.py start web_search_scrape_rag
```

### 4. Test the Setup

```bash
# Test all servers and integration
python test_mcp_client.py

# Test a specific server
python test_mcp_client.py --server youtube

# List available servers for testing
python test_mcp_client.py --list
```

### 5. Run the Terminal Chat Client

```bash
python Clients/terminal_chat_client.py
```

## Server Configuration

All MCP servers are configured in `Servers/config/mcp_servers.json` with unique ports:

| Server | Port | Description |
|--------|------|-------------|
| youtube | 8000 | YouTube video analysis and search |
| weather | 8001 | Weather information and forecasts |
| slack | 8002 | Slack integration and messaging |
| playwright | 8003 | Browser automation and web scraping |
| mcp-atlassian | 8004 | Jira and Confluence integration |
| service_system | 8006 | Customer service case management |
| sales_system | 8007 | Sales lead and campaign management |
| ms_learn | 8008 | Microsoft Learn documentation |
| web_search_scrape_rag | 8009 | Web search with RAG capabilities |

## Usage Examples

### Terminal Chat Client

Once the terminal client is running, you can ask questions like:

```
🙋 You: What's the weather like in Seattle?
🤖 Assistant: [Weather server responds with current conditions]

🙋 You: How to create a main form in Dynamics CRM?
🤖 Assistant: [MS Learn server provides documentation]

🙋 You: Find recent news about artificial intelligence
🤖 Assistant: [Web search RAG server provides latest news]

🙋 You: Get transcript from this YouTube video: https://youtube.com/watch?v=...
🤖 Assistant: [YouTube server analyzes the video]
```

### Special Commands

- `exit` or `quit` - Exit the chat
- `clear` or `reset` - Clear conversation history  
- `servers` - Show current server status

## Server Management

### Start/Stop Individual Servers

```bash
# Start a specific server
python run_mcp_servers.py start youtube

# Stop a specific server  
python run_mcp_servers.py stop youtube

# Check server status
python run_mcp_servers.py status

# Monitor servers continuously
python run_mcp_servers.py monitor
```

### Server Health Checks

The system automatically performs health checks before connecting to servers. You can also manually test server health:

```bash
# Test specific server health
python test_mcp_client.py --server weather

# Test all server health and integration
python test_mcp_client.py
```

## Architecture

### MultiServerMCPClient Integration

The updated `terminal_chat_client.py` uses `MultiServerMCPClient` which provides:

1. **Automatic Server Selection** - LLM-based routing to appropriate servers
2. **Health Monitoring** - Continuous monitoring of server availability
3. **Load Balancing** - Distributes requests across healthy servers
4. **Error Handling** - Graceful fallback when servers are unavailable
5. **Connection Management** - Automatic reconnection and cleanup

### MCPServerManager Class

The `MCPServerManager` class handles:

- **Server Process Management** - Starting/stopping server processes
- **Port Management** - Ensuring servers run on unique ports
- **Health Checks** - Verifying server readiness
- **Client Initialization** - Setting up MultiServerMCPClient connections
- **Graceful Shutdown** - Proper cleanup of processes and connections

## Troubleshooting

### Common Issues

1. **"No MCP servers are ready for connection"**
   - Check if servers are running: `python run_mcp_servers.py status`
   - Start servers: `python run_mcp_servers.py start-all`
   - Verify environment variables are set

2. **"Failed to initialize LLM"**
   - Check Azure OpenAI credentials in `.env` file
   - Verify endpoint and API key are correct

3. **"Port already in use"**
   - Stop existing servers: `python run_mcp_servers.py stop-all`
   - Check for other processes using the ports: `netstat -an | findstr :8000`

4. **Server fails to start**
   - Check server-specific environment variables
   - Verify dependencies are installed
   - Check server logs for error details

### Debug Mode

Enable debug logging by setting environment variable:

```bash
export LOG_LEVEL=DEBUG
python Clients/terminal_chat_client.py
```

### Manual Server Testing

Test individual servers without the client:

```bash
# Test server endpoint directly
curl http://127.0.0.1:8000/health

# Test server with specific query
python test_mcp_client.py --server youtube
```

## Development

### Adding New Servers

1. Create server implementation in `Servers/` directory
2. Add server configuration to `mcp_servers.json`
3. Assign unique port number
4. Add environment variables if needed
5. Test with `python test_mcp_client.py --server new_server`

### Custom Server Configuration

```json
{
  "mcpServers": {
    "your_server": {
      "command": "python",
      "args": ["path/to/your/server.py"],
      "env": {
        "MCP_HOST": "127.0.0.1",
        "MCP_PORT": "8010",
        "YOUR_API_KEY": "${YOUR_API_KEY}"
      },
      "description": "Description of your server"
    }
  }
}
```

## Performance Optimization

### Server Startup

- Servers start in parallel for faster initialization
- Health checks run concurrently
- Failed servers don't block others from starting

### Query Processing

- LLM-based server selection minimizes unnecessary requests
- Connection pooling reduces latency
- Automatic retry on server failures

### Resource Management

- Graceful shutdown prevents resource leaks
- Process monitoring detects failed servers
- Automatic cleanup on exit

## Security Considerations

- All servers run on localhost (127.0.0.1) by default
- Environment variables prevent hardcoded secrets
- Process isolation between servers
- Graceful handling of authentication failures

## Monitoring and Logging

The system provides comprehensive logging:

- Server startup/shutdown events
- Health check results
- Query routing decisions
- Error details and stack traces
- Performance metrics

Monitor servers continuously:

```bash
python run_mcp_servers.py monitor
```

This will show real-time status updates every 10 seconds.

## Integration with Existing Code

The updated terminal client is backward compatible and can be integrated with existing systems:

```python
from Clients.terminal_chat_client import MCPServerManager

# Initialize server manager
server_manager = MCPServerManager()
await server_manager.start_all_servers()
await server_manager.initialize_client(llm)

# Use in your application
response = await server_manager.query("Your question here")
```

## Support

For issues or questions:

1. Check server status: `python run_mcp_servers.py status`
2. Run diagnostics: `python test_mcp_client.py`
3. Review logs for error details
4. Verify environment configuration
5. Test individual servers separately

---

This setup ensures robust, scalable MCP server management with proper port isolation, health monitoring, and graceful error handling using the `MultiServerMCPClient` architecture. 