# Weather Analysis MCP Server

This MCP server provides weather information and analysis capabilities using the National Weather Service (NWS) API. It offers real-time weather alerts, forecasts, and location-based weather data for the United States.

## Features

### 🌦️ Weather Alerts
- **Tool**: `get_alerts`
- **Purpose**: Get all active weather alerts for a given US state
- **Data Source**: National Weather Service API
- **Includes**: Event type, severity, time range, descriptions, and instructions

### 🌡️ Weather Forecasts
- **Tool**: `get_forecast`
- **Purpose**: Get detailed weather forecast for specific coordinates
- **Input**: Latitude and longitude coordinates
- **Output**: 5-period forecast with temperature, wind, and detailed conditions

### 📍 Location-Based Services
- Automatic conversion from coordinates to NWS forecast points
- Supports all US locations covered by the National Weather Service

## Configuration

The server is configured in `Servers/config/mcp_servers.json`:

```json
{
  "weather": {
    "command": "uv",
    "args": ["run", "--with", "mcp[cli]", "mcp", "run", "path/to/weather_analysis_mcp.py"],
    "env": {
      "MCP_HOST": "127.0.0.1",
      "MCP_PORT": "8001"
    },
    "description": "Handles weather information queries..."
  }
}
```

## Tools Available

### 1. get_alerts
```python
# Get weather alerts for a state
await get_alerts("CA")  # California alerts
await get_alerts("TX")  # Texas alerts
```

**Returns**: Formatted string with:
- Event type (e.g., "Winter Storm Warning")
- Severity level
- Effective and expiration times
- Detailed description
- Safety instructions

### 2. get_forecast
```python
# Get forecast for specific coordinates
await get_forecast(34.0522, -118.2437)  # Los Angeles, CA
await get_forecast(40.7128, -74.0060)   # New York, NY
```

**Returns**: Formatted forecast with:
- 5-period outlook (today, tonight, tomorrow, etc.)
- Temperature and wind information
- Detailed weather conditions

## API Integration

### National Weather Service API
- **Base URL**: `https://api.weather.gov`
- **User Agent**: Custom user agent for identification
- **Rate Limiting**: Respectful API usage with proper timeouts
- **Error Handling**: Graceful degradation when API is unavailable

## Usage Examples

### Example Queries
The server automatically handles queries like:

- "What are the weather alerts for California?"
- "Get me the forecast for Los Angeles"
- "Are there any severe weather warnings in Texas?"
- "What's the weather going to be like at coordinates 40.7, -74.0?"

### Response Format
```
Event: Winter Storm Warning
Severity: Moderate
Time: 2024-01-15T06:00:00Z - 2024-01-16T18:00:00Z
Description: Heavy snow expected. Total snow accumulations of 6 to 12 inches...
Instructions: If you must travel, keep an extra flashlight, food, and water...
```

## Error Handling

The server includes robust error handling for:
- Network connectivity issues
- Invalid coordinates or state codes
- API rate limiting
- Malformed API responses
- Timeout scenarios

## Prompt Templates

### weather_prompt
Specialized prompt for weather alert queries:
```python
@mcp.prompt("weather_prompt")
def weather_prompt(state: str) -> str:
    return f"Get the weather alerts for {state}."
```

## Dependencies

- `httpx`: For HTTP requests to NWS API
- `mcp[cli]`: MCP server framework
- `asyncio`: For asynchronous operations

## Data Sources

- **Primary**: National Weather Service API (weather.gov)
- **Coverage**: United States and territories
- **Update Frequency**: Real-time for alerts, hourly for forecasts
- **Reliability**: Government-provided, authoritative weather data

## Limitations

- **Geographic Scope**: US locations only
- **API Dependency**: Requires NWS API availability
- **Rate Limits**: Subject to NWS API rate limiting
- **Coordinate Precision**: Works best with standard GPS coordinates

---

*This server provides reliable, government-sourced weather information for the United States through the National Weather Service API.* 