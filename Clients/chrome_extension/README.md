# Verna AI Chrome Extension

A Chrome extension that integrates with the Verna AI MCP (Model Context Protocol) server system to provide intelligent assistance while browsing.

## Features

### 🔗 Advanced Session Management & Conversation Context
- **Multiple Sessions**: Create and manage multiple conversation sessions per tab
- **Session Switching**: Easily switch between different conversation contexts
- **Persistent Conversations**: Each session maintains its own conversation history
- **Session Continuity**: Follow-up questions reference previous responses automatically
- **Context Awareness**: The extension remembers your conversation history per session

### 🤖 AI-Powered Assistance
- **Auto-server Selection**: Automatically chooses the most appropriate AI server for your query
- **Context-Aware Responses**: Considers page content, selected text, and conversation history
- **Multiple AI Specializations**: Access to specialized servers for different tasks

### 📄 Smart Context Integration
- **Page Content Analysis**: Optionally include current page content in queries
- **Selected Text Processing**: Analyze highlighted text from web pages
- **Tab-Specific Context**: Each tab maintains separate conversation threads

## How Session Management Works

### Session Creation
When you open the extension on a new tab:
1. A unique session ID is generated for that tab
2. The session is stored in Chrome's session storage
3. A visual indicator shows your active session

### Conversation Continuity
- Each query is linked to your tab's session
- Previous questions and answers are maintained as context
- Follow-up questions automatically reference earlier conversation

### Example Usage
```
Session 1: "How to setup new VM in Azure?"
Extension provides: [Detailed Azure VM setup guide]

Session 1: "Can you navigate and do it for me?"
Extension understands: You're referring to the Azure VM setup from your previous question

[Create new session]
Session 2: "What's the weather like today?"
Extension provides: [Weather information - completely separate conversation]

[Switch back to Session 1]
Session 1: "What about the pricing for the VM?"
Extension remembers: You're still talking about Azure VM setup
```

## Session Switching Features

### 🔄 Multiple Session Management
- **Create Sessions**: Use the ➕ button to create new conversation sessions
- **Switch Sessions**: Use the dropdown to switch between existing sessions
- **Session History**: View conversation history for each session separately
- **Session Persistence**: Sessions are saved and restored when you reopen the extension

### 📊 Session Information
- **Session Titles**: Sessions are named after their first question
- **Question Count**: Track how many questions you've asked in each session
- **Activity Timestamps**: See when each session was started and last used
- **Active Indicators**: Visual indicators show which session is currently active

### 🎯 Use Cases
- **Different Topics**: Keep separate conversations for different subjects
- **Context Switching**: Switch between work and personal questions
- **Research Projects**: Maintain separate research threads
- **Troubleshooting**: Keep different problem-solving conversations separate

## Installation

1. Clone the repository
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode"
4. Click "Load unpacked" and select the `Clients/chrome_extension` folder

## Usage

### Basic Usage
1. Click the extension icon in the toolbar
2. Ask your question in the text area
3. The extension will:
   - Maintain conversation context
   - Select the appropriate AI server
   - Provide contextual responses

### Session Features
- **Session Selector**: Use the dropdown to view and switch between sessions
- **New Session**: Click the ➕ button to create a new conversation session
- **Session Switching**: Click the 🔄 button or use the dropdown to switch sessions
- **View History**: Click the 📜 history button to see your conversation
- **Session Info**: The extension shows your active session with question count
- **Context Options**: Choose to include page content or selected text

### Context Menu
Right-click on any webpage to access quick actions:
- **Explain this**: Analyze selected text
- **Summarize this**: Summarize selected content
- **Translate this**: Translate selected text
- **Analyze page**: Get insights about the current page

## Configuration

### Settings
Access settings via the ⚙️ button:
- **API URL**: Configure the MCP server endpoint (default: `http://localhost:8001`)
- **Auto-submit**: Enable/disable automatic submission on Enter
- **History Limit**: Set maximum conversation history items
- **Floating Button**: Enable/disable the floating button on web pages

### Session Management
- Multiple sessions can be created per tab
- Session data is stored in Chrome's local storage
- Sessions persist across browser sessions (up to 7 days)
- Sessions are automatically cleaned up after 7 days of inactivity

## Technical Details

### Architecture
```
Chrome Extension Frontend (popup.js)
    ↓ (includes session_id, tab_id)
Backend API (chrome_extension_client.py)
    ↓ (channel_id, thread_ts)
ServerManager (server_manager.py)
    ↓ (conversation context)
ConversationManager (conversation_manager.py)
    ↓ (maintains history)
MCP Servers (specialized AI services)
```

### Session Parameters
- `session_id`: Unique identifier for the tab session
- `tab_id`: Chrome tab identifier
- `channel_id`: Used for conversation threading
- `thread_ts`: Thread timestamp for context separation

## API Integration

The extension communicates with the MCP server backend via:
- `POST /api/query`: Send queries with session context
- `GET /api/history`: Retrieve conversation history
- `GET /api/servers`: Get available AI servers
- `WebSocket /ws`: Real-time communication (optional)

## Troubleshooting

### Common Issues

1. **No Response from Extension**
   - Check if the MCP server is running on `localhost:8001`
   - Verify the API URL in settings

2. **Session Not Maintained**
   - Ensure you're using the same session for follow-up questions
   - Check if Chrome's local storage is enabled
   - Try switching to the correct session using the dropdown

3. **Context Not Working**
   - Verify the "Include page content" option is enabled
   - Check if the page content is accessible

4. **Session Switching Issues**
   - If sessions don't appear, refresh the extension
   - Check if local storage permissions are enabled
   - Sessions older than 7 days are automatically cleaned up

### Debug Information
- Session ID is displayed in the extension popup
- Console logs show session initialization
- History shows conversation context being maintained

## Development

### File Structure
```
chrome_extension/
├── manifest.json       # Extension configuration
├── popup.html          # Main UI
├── popup.js           # Main logic with session management
├── popup.css          # Styling
├── background.js      # Background service worker
├── content.js         # Content script
└── icons/             # Extension icons
```

### Key Features Added
- Session management in `popup.js`
- Backend session handling in `chrome_extension_client.py`
- Conversation context via `ConversationManager`
- Visual session indicators in the UI

## License

This project is part of the Verna AI MCP server system. 