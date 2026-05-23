from typing import Any
import httpx
import logging
import sys
from mcp.server.fastmcp import FastMCP

# Configure logging to stderr to avoid interfering with MCP JSON protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Initialize the MCP server
logger.info("Initializing Weather MCP server...")
mcp = FastMCP("weather")

#Constants
NWS_API_BASE_URL = "https://api.weather.gov"
USER_AGENT = "Weather-app/1.0"

async def make_nws_request(url: str) -> dict[str, Any] |None:
    """
    Make a request to the NWS API and return the response as a dictionary.
    """
    logger.info(f"make_nws_request called with URL: {url}")
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            logger.info("NWS request successful.")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error in make_nws_request: {e}")
            return None
    
def format_alert(feature: dict[str, Any]) -> str:
    """
    Format an alert feature from the NWS API into a string.
    """
    props = feature["properties"]
    return f"""
    Event: {props["event"]}
    Severity: {props["severity"]}
    Time: {props["effective"]} - {props["expires"]}
    Description: {props["description"]}
    Instructions: {props["instruction"]}
    """
    
@mcp.tool()
async def weather_get_alerts(state: str) -> str:
    """
    Get all active weather alerts for a given US state.
    
    Args:
        state (str): The US state to get alerts for.
        
    Returns:
        str: A string containing all active weather alerts for the given state.
    """
    logger.info(f"weather_get_alerts called with state: {state}")
    url = f"{NWS_API_BASE_URL}/alerts/active/area/{state}"
    data = await make_nws_request(url)

    if not data or "features" not in data:
        logger.warning("No data or features in NWS response.")
        return "No alerts found for the given state."
    
    if not data["features"]:
        logger.info("No active alerts found for the given state.")
        return "No active alerts found for the given state."
    
    alerts = [format_alert(feature) for feature in data["features"]]
    logger.info(f"Returning {len(alerts)} alerts.")
    return "\n\n".join(alerts)


@mcp.tool()
async def weather_get_forecast(latitude: float, longitude: float) -> str:
    """
    Get the weather forecast for a given latitude and longitude.

    Args:
        latitude (float): The latitude of the location.
        longitude (float): The longitude of the location.

    Returns:
        str: A string containing the weather forecast.
    """
    # Get the forecast URL from the NWS API
    points_url = f"{NWS_API_BASE_URL}/points/{latitude},{longitude}"
    points_data = await make_nws_request(points_url)
    if not points_data or "properties" not in points_data or "forecast" not in points_data["properties"]:
        return "Unable to fetch forecast data for this location."

    forecast_url = points_data["properties"]["forecast"]
    forecast_data = await make_nws_request(forecast_url)
    if not forecast_data or "properties" not in forecast_data or "periods" not in forecast_data["properties"]:
        return "Unable to fetch detailed forecast."

    periods = forecast_data["properties"]["periods"]
    forecasts = []
    for period in periods[:5]:  # Only show next 5 periods
        forecast = f"""
            {period['name']}:
            Temperature: {period['temperature']}°{period['temperatureUnit']}
            Wind: {period['windSpeed']} {period['windDirection']}
            Forecast: {period['detailedForecast']}
            """
        forecasts.append(forecast.strip())
    return "\n\n".join(forecasts)
    
    
@mcp.resource("echo://{message}")
def echo_resource(message: str) -> str:
    """
    Echo a message back to the user.
    """
    return f"Resource echo: {message}"

@mcp.prompt("weather_prompt")
def weather_prompt(state: str) -> str:
    """
    A prompt for getting weather alerts for a given state.
    """
    return f"Get the weather alerts for {state}."

if __name__ == "__main__":
    mcp.run(transport = 'streamable-http')

