"""
Configuration management for MCP servers.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages MCP server configurations."""
    
    def __init__(self, config_dir: str = "Servers/config"):
        """
        Initialize configuration manager.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = config_dir
        self._servers: Dict[str, Any] = {}
        self._config_loaded = False
    
    def load_server_configs(self) -> Dict[str, Any]:
        """
        Load all server configurations from the unified config file.
        
        Returns:
            Dictionary of server configurations
        """
        if self._config_loaded:
            return self._servers
        
        possible_paths = self._get_config_file_paths()
        config_path = self._find_existing_config_file(possible_paths)
        
        if not config_path:
            logger.warning(f"Unified config file not found in any of these locations:")
            for path in possible_paths:
                logger.warning(f"  - {path.absolute()}")
            return {}
        
        try:
            self._servers = self._load_config_from_file(config_path)
            self._config_loaded = True
            logger.info(f"Loaded {len(self._servers)} server configurations from: {config_path.absolute()}")
            return self._servers
        except Exception as e:
            logger.error(f"Error reading config file {config_path}: {e}")
            return {}
    
    def _get_config_file_paths(self) -> List[Path]:
        """Get list of possible configuration file paths."""
        return [
            Path(self.config_dir) / "mcp_servers.json",
            Path("Servers/config/mcp_servers.json"),
            Path("../Servers/config/mcp_servers.json"),
            Path(__file__).parent.parent / "Servers/config/mcp_servers.json"
        ]
    
    def _find_existing_config_file(self, paths: List[Path]) -> Path:
        """Find the first existing configuration file from the list of paths."""
        for path in paths:
            if path.exists():
                return path
        return None
    
    def _load_config_from_file(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration from a specific file."""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
            # Handle both old format (mcpServers wrapper) and new direct format
            if 'mcpServers' in config:
                servers = config['mcpServers']
            else:
                # New format: direct server configurations at root level
                servers = config
            
        # Process environment variables in server configs
        for server_name, server_config in servers.items():
            if 'env' in server_config:
                server_config['env'] = self._process_environment_variables(server_config['env'])
        
        return servers
    
    def _process_environment_variables(self, env_config: Dict[str, Any]) -> Dict[str, Any]:
        """Process environment variable references in configuration."""
        processed_env = {}
        for key, value in env_config.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                env_var_name = value[2:-1]  # Remove ${ and }
                processed_env[key] = os.environ.get(env_var_name, value)
            else:
                processed_env[key] = value
        return processed_env
    
    def get_server_config(self, server_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Server configuration dictionary
        """
        if not self._config_loaded:
            self.load_server_configs()
        return self._servers.get(server_name, {})
    
    def get_mcp_client_configs(self) -> Dict[str, Any]:
        """
        Get all server configurations cleaned for MCP client use.
        Removes fields that are not needed by the MCP client (like 'description').
        
        Returns:
            Dictionary of cleaned server configurations
        """
        if not self._config_loaded:
            self.load_server_configs()
        
        cleaned_configs = {}
        for server_name, config in self._servers.items():
            # Create a copy and remove the description field
            cleaned_config = {k: v for k, v in config.items() if k != 'description'}
            cleaned_configs[server_name] = cleaned_config
        
        return cleaned_configs
    
    def get_all_server_names(self) -> List[str]:
        """
        Get list of all configured server names.
        
        Returns:
            List of server names
        """
        if not self._config_loaded:
            self.load_server_configs()
        return list(self._servers.keys())
    
    def get_server_descriptions(self) -> str:
        """
        Create a formatted description of available servers.
        
        Returns:
            Formatted string describing all servers
        """
        if not self._config_loaded:
            self.load_server_configs()
        
        descriptions = []
        for i, (name, config) in enumerate(self._servers.items(), 1):
            description = config.get('description', 'No description available')
            descriptions.append(f"{i}. {name} - {description}")
        
        return "\n".join(descriptions)
    
    def get_server_capabilities(self, server_name: str) -> str:
        """
        Get capabilities description for a specific server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Formatted capabilities description
        """
        server_config = self.get_server_config(server_name)
        description = server_config.get('description', 'No description available')
        return f"Server: {server_name}\nDescription: {description}"
    
    def reload_configs(self) -> Dict[str, Any]:
        """
        Force reload of server configurations.
        
        Returns:
            Updated server configurations
        """
        self._config_loaded = False
        self._servers.clear()
        return self.load_server_configs()
    
    def has_server(self, server_name: str) -> bool:
        """
        Check if a server configuration exists.
        
        Args:
            server_name: Name of the server to check
            
        Returns:
            True if server exists, False otherwise
        """
        if not self._config_loaded:
            self.load_server_configs()
        return server_name in self._servers 
    
    def check_environment_variables(self) -> Dict[str, str]:
        """
        Check for missing environment variables and return status.
        
        Returns:
            Dictionary with environment variable status and messages
        """
        import os
        from dotenv import load_dotenv
        
        # Load environment variables
        load_dotenv()
        
        env_status = {
            "missing_vars": [],
            "warnings": [],
            "status": "ok"
        }
        
        # Check required environment variables
        required_vars = {
            "GOOGLE_API_KEY": "Google Custom Search API",
            "GOOGLE_CSE_ID": "Google Custom Search Engine ID",
            "AZURE_OPENAI_ENDPOINT": "Azure OpenAI Endpoint",
            "AZURE_OPENAI_API_KEY": "Azure OpenAI API Key",
            "YOUTUBE_API_KEY": "YouTube Data API Key"
        }
        
        for var_name, description in required_vars.items():
            value = os.getenv(var_name)
            if not value:
                env_status["missing_vars"].append(f"{var_name} ({description})")
                env_status["status"] = "missing_required"
            elif value.startswith("your_") or value == "":
                env_status["warnings"].append(f"{var_name} appears to be a placeholder")
                env_status["status"] = "has_warnings"
        
        return env_status
    
    def get_environment_status_report(self) -> str:
        """
        Generate a human-readable environment status report.
        
        Returns:
            Formatted environment status report
        """
        status = self.check_environment_variables()
        
        if status["status"] == "ok":
            return "✅ All required environment variables are configured."
        
        report = "🔧 **Environment Configuration Status**\n\n"
        
        if status["missing_vars"]:
            report += "❌ **Missing Required Variables:**\n"
            for var in status["missing_vars"]:
                report += f"   • {var}\n"
            report += "\n"
        
        if status["warnings"]:
            report += "⚠️ **Warnings:**\n"
            for warning in status["warnings"]:
                report += f"   • {warning}\n"
            report += "\n"
        
        report += "**Setup Instructions:**\n"
        report += "1. Copy `.env.example` to `.env` if not already done\n"
        report += "2. Fill in the required API keys and configuration values\n"
        report += "3. Restart the application\n"
        
        return report 