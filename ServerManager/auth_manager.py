"""
Shared Authentication Manager for MCP Servers

This module provides a centralized authentication system that can be used
across all clients (Chrome Extension, Streamlit, Slack, Terminal, etc.)
to handle server authentication consistently.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AuthManager:
    """Centralized authentication manager for MCP servers"""
    
    def __init__(self):
        self.authenticated_sessions: Dict[str, Dict[str, Any]] = {}
        self.auth_config = self._load_auth_config()
    
    def _load_auth_config(self) -> Dict[str, Any]:
        """Load authentication configuration for servers"""
        return {
            "service_system": {
                "requires_auth": True,
                "auth_type": "dynamics_crm",
                "display_name": "Dynamics CRM Service System",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["D365_CLIENT_ID", "D365_CLIENT_SECRET", "D365_TENANT_ID"]
            },
            "sales_system": {
                "requires_auth": True,
                "auth_type": "dynamics_365",
                "display_name": "Dynamics 365 Sales",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["DYNAMICS_SALES_CLIENT_ID", "DYNAMICS_SALES_CLIENT_SECRET", "DYNAMICS_SALES_TENANT_ID"]
            },
            "slack": {
                "requires_auth": True,
                "auth_type": "slack_oauth",
                "display_name": "Slack Workspace",
                "auth_url": "https://slack.com/oauth/v2/authorize",
                "scopes": ["chat:write", "channels:read", "groups:read", "im:read", "mpim:read"],
                "env_vars": ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_TEAM_ID"]
            },
            "mcp-atlassian": {
                "requires_auth": True,
                "auth_type": "atlassian_api",
                "display_name": "Atlassian (Jira/Confluence)",
                "auth_url": "https://auth.atlassian.com/authorize",
                "scopes": ["read:jira-work", "read:confluence-content.all"],
                "env_vars": ["ATLASSIAN_API_TOKEN", "ATLASSIAN_SITE_URL", "ATLASSIAN_EMAIL"]
            },
            "audio_video_rag": {
                "requires_auth": True,
                "auth_type": "databricks",
                "display_name": "Databricks RAG System",
                "auth_url": "https://databricks.com/login",
                "scopes": ["workspace:read", "clusters:read"],
                "env_vars": ["DATABRICKS_WORKSPACE_URL", "DATABRICKS_ACCESS_TOKEN"]
            },
            "hr_system": {
                "requires_auth": True,
                "auth_type": "dynamics_365",
                "display_name": "Dynamics 365 HR",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["DYNAMICS_HR_CLIENT_ID", "DYNAMICS_HR_CLIENT_SECRET", "DYNAMICS_HR_TENANT_ID"]
            },
            "accounting_system": {
                "requires_auth": True,
                "auth_type": "dynamics_365",
                "display_name": "Dynamics 365 Finance",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["DYNAMICS_FINANCE_CLIENT_ID", "DYNAMICS_FINANCE_CLIENT_SECRET", "DYNAMICS_FINANCE_TENANT_ID"]
            },
            "marketing_system": {
                "requires_auth": True,
                "auth_type": "dynamics_365",
                "display_name": "Dynamics 365 Marketing",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["DYNAMICS_MARKETING_CLIENT_ID", "DYNAMICS_MARKETING_CLIENT_SECRET", "DYNAMICS_MARKETING_TENANT_ID"]
            },
            "csm_system": {
                "requires_auth": True,
                "auth_type": "dynamics_365",
                "display_name": "Dynamics 365 Customer Service",
                "auth_url": "https://login.microsoftonline.com/",
                "scopes": ["https://dynamics.microsoft.com/.default"],
                "env_vars": ["DYNAMICS_CSM_CLIENT_ID", "DYNAMICS_CSM_CLIENT_SECRET", "DYNAMICS_CSM_TENANT_ID"]
            },
            "s4_hana": {
                "requires_auth": True,
                "auth_type": "sap_oauth",
                "display_name": "SAP S/4HANA",
                "auth_url": "https://your-sap-system.com/oauth/authorize",
                "scopes": ["sap:read", "sap:write"],
                "env_vars": ["SAP_CLIENT_ID", "SAP_CLIENT_SECRET", "SAP_SYSTEM_URL"]
            },
            # Systems that don't require authentication
            "intelli_web_search": {"requires_auth": False},
            "youtube": {"requires_auth": False},
            "weather": {"requires_auth": False},
            "microsoft.docs.mcp": {"requires_auth": False},
            "playwright": {"requires_auth": False},
            "content-analysis": {"requires_auth": False}
        }
    
    def requires_authentication(self, server_name: str) -> bool:
        """Check if a server requires authentication"""
        return self.auth_config.get(server_name, {}).get("requires_auth", False)
    
    def is_authenticated(self, server_name: str, session_id: str = None) -> bool:
        """Check if a server is authenticated for a session"""
        if not self.requires_authentication(server_name):
            return True
        
        if not session_id:
            # For non-session clients, check environment variables
            return self._check_env_auth(server_name)
        
        session_key = f"{session_id}_{server_name}"
        session_data = self.authenticated_sessions.get(session_key)
        
        if not session_data:
            return False
        
        # Check if session is still valid
        if session_data.get("expires_at"):
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now() > expires_at:
                # Session expired
                del self.authenticated_sessions[session_key]
                return False
        
        return True
    
    def _check_env_auth(self, server_name: str) -> bool:
        """Check if required environment variables are set for authentication"""
        auth_config = self.auth_config.get(server_name, {})
        required_env_vars = auth_config.get("env_vars", [])
        
        if not required_env_vars:
            return True
        
        # Check if all required environment variables are set
        for env_var in required_env_vars:
            if not os.environ.get(env_var):
                logger.debug(f"Missing environment variable {env_var} for {server_name}")
                return False
        
        return True
    
    def authenticate_session(self, server_name: str, session_id: str, credentials: Dict[str, Any]) -> bool:
        """Authenticate a session for a specific server"""
        auth_config = self.auth_config.get(server_name, {})
        
        if not auth_config.get("requires_auth", False):
            return True
        
        # Validate credentials based on auth type
        if self._validate_credentials(server_name, credentials):
            # Store authenticated session
            session_key = f"{session_id}_{server_name}"
            self.authenticated_sessions[session_key] = {
                "server_name": server_name,
                "session_id": session_id,
                "authenticated_at": datetime.now().isoformat(),
                "expires_at": (datetime.now() + timedelta(hours=24)).isoformat(),
                "credentials": credentials  # In production, store encrypted tokens
            }
            logger.info(f"Successfully authenticated session {session_id} for {server_name}")
            return True
        
        return False
    
    def _validate_credentials(self, server_name: str, credentials: Dict[str, Any]) -> bool:
        """Validate credentials based on server auth type"""
        auth_config = self.auth_config.get(server_name, {})
        auth_type = auth_config.get("auth_type", "generic")
        
        if auth_type in ["dynamics_crm", "dynamics_365"]:
            required_fields = ["tenant_id", "client_id", "client_secret"]
        elif auth_type == "slack_oauth":
            required_fields = ["workspace_url", "bot_token", "app_token"]
        elif auth_type == "atlassian_api":
            required_fields = ["site_url", "email", "api_token"]
        elif auth_type == "databricks":
            required_fields = ["workspace_url", "access_token"]
        elif auth_type == "sap_oauth":
            required_fields = ["system_url", "client_id", "client_secret"]
        elif auth_type == "api_key":
            required_fields = ["api_key"]
        else:
            required_fields = ["username", "password"]
        
        # Check if all required fields are provided
        return all(field in credentials for field in required_fields)
    
    def logout_session(self, server_name: str, session_id: str) -> bool:
        """Logout a session from a specific server"""
        session_key = f"{session_id}_{server_name}"
        if session_key in self.authenticated_sessions:
            del self.authenticated_sessions[session_key]
            logger.info(f"Successfully logged out session {session_id} from {server_name}")
            return True
        return False
    
    def get_auth_status(self, session_id: str = None) -> Dict[str, Any]:
        """Get authentication status for all servers"""
        status = {}
        
        for server_name, config in self.auth_config.items():
            status[server_name] = {
                "requires_auth": config.get("requires_auth", False),
                "is_authenticated": self.is_authenticated(server_name, session_id),
                "display_name": config.get("display_name", server_name),
                "auth_type": config.get("auth_type", "generic"),
                "auth_url": config.get("auth_url"),
                "scopes": config.get("scopes", [])
            }
        
        return status
    
    def get_server_config(self, server_name: str) -> Dict[str, Any]:
        """Get authentication configuration for a specific server"""
        return self.auth_config.get(server_name, {})
    
    def get_missing_env_vars(self, server_name: str) -> List[str]:
        """Get list of missing environment variables for a server"""
        auth_config = self.auth_config.get(server_name, {})
        required_env_vars = auth_config.get("env_vars", [])
        
        missing_vars = []
        for env_var in required_env_vars:
            if not os.environ.get(env_var):
                missing_vars.append(env_var)
        
        return missing_vars
    
    def validate_server_auth(self, server_name: str, session_id: str = None) -> Dict[str, Any]:
        """Validate authentication for a server and return detailed status"""
        auth_config = self.auth_config.get(server_name, {})
        
        if not auth_config.get("requires_auth", False):
            return {
                "status": "success",
                "message": f"No authentication required for {server_name}",
                "authenticated": True
            }
        
        if self.is_authenticated(server_name, session_id):
            return {
                "status": "success", 
                "message": f"Successfully authenticated to {auth_config.get('display_name', server_name)}",
                "authenticated": True
            }
        
        missing_env_vars = self.get_missing_env_vars(server_name)
        if missing_env_vars:
            return {
                "status": "error",
                "message": f"Missing environment variables for {server_name}: {', '.join(missing_env_vars)}",
                "authenticated": False,
                "missing_env_vars": missing_env_vars
            }
        
        return {
            "status": "error",
            "message": f"Authentication required for {auth_config.get('display_name', server_name)}",
            "authenticated": False,
            "auth_config": auth_config
        }

# Global auth manager instance
auth_manager = AuthManager() 