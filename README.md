# MCP Server Model

A robust Client-Server architecture implementing the [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) **Multiple MCP Servers** pattern with bulletproof error handling and external microservice integration.

## 🎯 Architecture Overview

This project follows a **Client-Server Architecture** that seamlessly integrates multiple MCP servers and external microservices:

### 🖥️ **Client Layer**
Multiple client interfaces for diverse integration scenarios:

- **Terminal Chat Client** (`terminal_chat_client.py`) - Interactive command-line interface with rich commands
- **API Client** (`api_client.py`) - Programmatic SDK-style interface for application integration
- **Streamlit Web UI** (`streamlit_app_ui.py`) - Modern web-based interface with rich visualization
- **Chrome Extension** (`chrome_extension/`) - Browser-based client for on-the-go access
- **Slack Listener** (`slack_listener.py`) - Real-time Slack integration for team collaboration
- **MS Teams Listener** (`ms_teams_listner.py`) - Microsoft Teams integration for enterprise environments

All clients implement unified langchain-mcp-adapters patterns for consistent server communication

### ⚙️ **Server Layer**
- **STDIO Servers (8)**: youtube, weather, slack, playwright, mcp_atlassian, service_system, sales_system, web_search_scrape_rag
- **HTTP Servers (1)**: microsoft_docs
- **External Microservices**: Seamlessly integrates with externally built microservices via HTTP/REST APIs
- Each server exposes specialized tools and capabilities through standardized MCP protocol

### 🔗 **Integration Layer**
- **ServerManager** - Central orchestration hub managing all server connections
- **MultiServerMCPClient** - Unified client for cross-server tool visibility
- **Error Handling & Fallbacks** - Bulletproof error recovery and graceful degradation
- **Configuration Management** - Flexible configuration supporting STDIO and HTTP transports

## ✨ Key Features

### 🎨 Multiple Client Interfaces
- ✅ **6 Different Clients** - Terminal, Web UI, Chrome Extension, Slack, MS Teams, and API
- ✅ **Flexible Integration** - Choose the interface that fits your workflow
- ✅ **Consistent Experience** - All clients use the same unified backend
- ✅ **Team Collaboration** - Slack and Teams integration for shared access

### 🏗️ Robust Architecture
- ✅ **Client-Server Architecture** - Clean separation with centralized server management
- ✅ **Multi-Server Support** - Unified access to 9+ servers
- ✅ **External Microservice Integration** - Connect to any HTTP-based microservice
- ✅ **Cross-Server Tool Visibility** - All tools available in one unified call

### 🛡️ Production Ready
- ✅ **100% Documentation Compliance** - Follows official langchain-mcp-adapters patterns
- ✅ **Bulletproof Error Handling** - Multiple fallback layers handle all scenarios
- ✅ **Individual Server Isolation** - One failing server doesn't affect others
- ✅ **Comprehensive Logging** - Full observability and debugging support

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys
```

### 2. Choose Your Client Interface

#### Option A: Terminal Client
```bash
python Clients/terminal_chat_client.py
```

#### Option B: Streamlit Web UI
```bash
streamlit run Clients/streamlit_app_ui.py
```

#### Option C: Chrome Extension
```bash
python Clients/chrome_extension/start_extension.py
```

#### Option D: Slack Integration
```bash
python Clients/slack_listener.py
```

#### Option E: MS Teams Integration
```bash
python Clients/ms_teams_listner.py
```

#### Option F: Programmatic API Usage
```python
from ServerManager import ServerManager
from Servers.llm_factory import get_llm_from_config

# Initialize
server_manager = ServerManager()
llm = get_llm_from_config()
server_manager.initialize(llm)

# Process requests
response = await server_manager.process_request("What's the weather in Seattle?")
```

## 🛡️ Robust Error Handling

### Library Bug Workaround
The langchain-mcp-adapters library has a TaskGroup bug that we handle seamlessly:

1. **Primary**: Uses `MultiServerMCPClient.get_tools()` (documentation pattern)
2. **Fallback**: Individual server tool retrieval when primary fails
3. **Auto-Recovery**: Fallback to simplified processing if needed

### Error Scenarios Handled
- ✅ TaskGroup errors in langchain-mcp-adapters library
- ✅ Individual server connection failures  
- ✅ Tool execution errors
- ✅ JSON parsing failures
- ✅ Network connectivity problems

## 📋 Configuration

Configuration follows the langchain-mcp-adapters documentation format with support for multiple transport types:

### STDIO Server Configuration
```json
{
  "server_name": {
    "command": "python",
    "args": ["/path/to/server.py"],
    "transport": "stdio",
    "env": {
      "API_KEY": "${API_KEY}"
    }
  }
}
```

### HTTP/Microservice Configuration
```json
{
  "http_server": {
    "url": "http://localhost:8000/mcp/",
    "transport": "streamable_http",
    "headers": {
      "Content-Type": "application/json"
    }
  }
}
```

### External Microservice Integration
```json
{
  "custom_microservice": {
    "url": "https://api.example.com/mcp/",
    "transport": "streamable_http",
    "headers": {
      "Authorization": "Bearer ${API_TOKEN}",
      "Content-Type": "application/json"
    }
  }
}
```

**Key Features:**
- Environment variable substitution using `${VARIABLE_NAME}` syntax
- Support for custom headers (authentication, content-type, etc.)
- Mix and match STDIO and HTTP servers in the same configuration
- Easy integration with existing microservice infrastructure

## 📊 Server Details

### Built-in MCP Servers
- **📡 STDIO Servers (8)**: 
  - `youtube` - YouTube video processing and search
  - `weather` - Weather information retrieval
  - `slack` - Slack messaging integration
  - `playwright` - Browser automation and web scraping
  - `mcp_atlassian` - Atlassian suite integration
  - `service_system` - Service management operations
  - `sales_system` - Sales and CRM operations
  - `web_search_scrape_rag` - Web search and RAG capabilities

- **🌐 HTTP Servers (1)**: 
  - `microsoft_docs` - Microsoft documentation search and retrieval

### External Microservices
- Any HTTP/REST-based microservice can be integrated via configuration
- Supports custom authentication headers and environment variables
- Seamless integration with existing service infrastructure

## 🎯 Client Capabilities

### Terminal Client Commands
- `/status` - Show conversation statistics
- `/clear` - Clear conversation history  
- `/reset` - Reset conversation and get available servers
- `/servers` - List available servers
- `/youtube [URL]` - Process YouTube video
- `/search [query]` - Search YouTube videos
- `/config` - Show configuration status
- `/quit` or `exit` - Exit the chat

### Streamlit Web UI Features
- Interactive chat interface with message history
- Visual tool execution feedback
- Server status monitoring
- Configuration management panel
- File upload and download support

### Chrome Extension Features
- Quick access via browser toolbar
- Context menu integration
- Background processing
- Tab-specific interactions
- Popup interface for fast queries

### Slack & MS Teams Features
- Real-time message processing
- Channel and direct message support
- Thread-based conversations
- Bot mention commands
- Rich card responses (Teams)
- Slash commands support (Slack)

## 🏗️ Implementation Details

### Client Implementations

#### 1. Terminal Chat Client (`terminal_chat_client.py`)
- Interactive command-line interface with rich command support
- Conversation history management and persistence
- Real-time statistics and monitoring
- Special commands: `/status`, `/clear`, `/reset`, `/servers`, `/youtube`, `/search`, `/config`

#### 2. Streamlit Web UI (`streamlit_app_ui.py`)
- Modern web-based interface with rich visualization
- Interactive forms and real-time responses
- Session state management
- Perfect for demos and non-technical users

#### 3. Chrome Extension (`chrome_extension/`)
- Browser-based client for on-the-go access
- Background processing with content scripts
- Popup interface for quick interactions
- Seamless integration with web browsing

#### 4. Slack Listener (`slack_listener.py`)
- Real-time Slack bot integration
- Team collaboration and shared access
- Event-driven message processing
- Channel and direct message support

#### 5. MS Teams Listener (`ms_teams_listner.py`)
- Microsoft Teams bot integration
- Enterprise-ready collaboration
- Teams channel integration
- Adaptive card support

#### 6. API Client (`api_client.py`)
- Programmatic SDK-style interface
- Async/await support for non-blocking operations
- Full access to all server tools and capabilities
- Perfect for embedding in applications

### Server Management (ServerManager)
Core orchestration component implementing langchain-mcp-adapters pattern:
- `process_request()` - Primary method (alias for process_request_direct)
- `process_request_direct()` - Core langchain-mcp-adapters implementation
- `initialize()` - Sets up connections to all configured servers
- Robust tool retrieval with multi-layer fallbacks
- Cross-server tool visibility and coordination

### Configuration Management
- Supports both STDIO and HTTP transport protocols
- Environment variable substitution for secure credential management
- Automatic format detection and validation
- Easy addition of new servers and external microservices

### Error Handling & Resilience
- Multi-layer fallback system for library bugs and network issues
- Automatic graceful degradation when servers are unavailable
- Individual server failure isolation (one failing server doesn't affect others)
- Comprehensive logging and monitoring for debugging

## 📚 Documentation

- **[Implementation Guide](LANGCHAIN_MCP_ADAPTERS_IMPLEMENTATION.md)** - Detailed technical documentation
- **[Setup Guide](MCP_CLIENT_SETUP.md)** - Client setup instructions
- **[Search API Setup](SEARCH_API_SETUP_GUIDE.md)** - Search API configuration

## 🔗 Reference

- **Documentation**: https://github.com/langchain-ai/langchain-mcp-adapters
- **Section**: Multiple MCP Servers
- **Pattern**: Exact implementation with robust error handling

## 🎁 Key Benefits

1. **🎨 Multiple Client Options** - 6 different clients (Terminal, Web UI, Chrome Extension, Slack, Teams, API) for every use case
2. **🤝 Team Collaboration** - Built-in Slack and MS Teams support for shared team access
3. **🔗 Cross-server tool visibility** - All 9+ server tools available in one unified call
4. **🌐 External Microservice Integration** - Seamlessly connect to any HTTP/REST-based service
5. **🛡️ Robust error handling** - Multiple fallback mechanisms and individual server isolation
6. **🔄 Automatic recovery** - Seamless degradation when servers are unavailable
7. **📖 Documentation compliance** - Follows official langchain-mcp-adapters patterns exactly
8. **🚀 Production ready** - Comprehensive logging, monitoring, and bulletproof error handling

This implementation provides the most **versatile** and **reliable** langchain-mcp-adapters pattern integration with the most diverse set of client interfaces available.
