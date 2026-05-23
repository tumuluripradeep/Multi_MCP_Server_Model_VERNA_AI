"""
OAuth Token Manager for MCP Servers

Handles OAuth 2.0 authentication flows including:
- Authorization code exchange
- Token storage and retrieval
- Automatic token refresh
- Token expiration management
"""

import os
import json
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class OAuthTokenManager:
    """Manages OAuth tokens for MCP servers"""
    
    def __init__(self, token_storage_path: str = ".oauth_tokens"):
        """
        Initialize the OAuth token manager.
        
        Args:
            token_storage_path: Path to store OAuth tokens securely
        """
        self.token_storage_path = Path(token_storage_path)
        self.token_storage_path.mkdir(exist_ok=True)
        self.tokens: Dict[str, Dict[str, Any]] = {}
        self._load_tokens()
    
    def _load_tokens(self) -> None:
        """Load stored tokens from disk"""
        token_file = self.token_storage_path / "tokens.json"
        if token_file.exists():
            try:
                with open(token_file, 'r') as f:
                    self.tokens = json.load(f)
                logger.info(f"✅ Loaded {len(self.tokens)} stored OAuth tokens")
            except Exception as e:
                logger.error(f"❌ Failed to load tokens: {e}")
                self.tokens = {}
    
    def _save_tokens(self) -> None:
        """Save tokens to disk"""
        token_file = self.token_storage_path / "tokens.json"
        try:
            with open(token_file, 'w') as f:
                json.dump(self.tokens, f, indent=2)
            logger.debug("💾 Saved OAuth tokens to disk")
        except Exception as e:
            logger.error(f"❌ Failed to save tokens: {e}")
    
    def exchange_authorization_code(
        self,
        server_name: str,
        auth_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Exchange an authorization code for an access token.
        
        Args:
            server_name: Name of the server
            auth_config: OAuth configuration containing:
                - token_url: URL to exchange code for token
                - client_id: OAuth client ID
                - client_secret: OAuth client secret
                - code: Authorization code
                - grant_type: OAuth grant type (default: authorization_code)
        
        Returns:
            Token response dict or None if failed
        """
        token_url = auth_config.get('token_url')
        client_id = auth_config.get('client_id')
        client_secret = auth_config.get('client_secret')
        code = auth_config.get('code')
        grant_type = auth_config.get('grant_type', 'authorization_code')
        
        # Expand environment variables if they're still in ${VAR} format
        # (they may already be resolved by server_manager)
        if client_id and isinstance(client_id, str) and client_id.startswith('${'):
            client_id = os.path.expandvars(client_id)
        if client_secret and isinstance(client_secret, str) and client_secret.startswith('${'):
            client_secret = os.path.expandvars(client_secret)
        if code and isinstance(code, str) and code.startswith('${'):
            code = os.path.expandvars(code)
        
        if not all([token_url, client_id, client_secret, code]):
            logger.error(f"❌ Missing OAuth configuration for {server_name}")
            logger.error(f"   token_url: {'SET' if token_url else 'NOT SET'}")
            logger.error(f"   client_id: {'SET' if client_id else 'NOT SET'}")
            logger.error(f"   client_secret: {'SET' if client_secret else 'NOT SET'}")
            logger.error(f"   code: {'SET' if code else 'NOT SET'}")
            return None
        
        logger.info(f"🔄 Exchanging authorization code for {server_name}...")
        
        try:
            # Prepare token request
            data = {
                'grant_type': grant_type,
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            # Make token request
            response = requests.post(token_url, data=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Store token with expiration
                self.tokens[server_name] = {
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token'),
                    'token_type': token_data.get('token_type', 'Bearer'),
                    'expires_in': token_data.get('expires_in', 3600),
                    'expires_at': (datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat(),
                    'obtained_at': datetime.now().isoformat()
                }
                
                self._save_tokens()
                logger.info(f"✅ Successfully obtained access token for {server_name}")
                logger.info(f"   Token expires in {token_data.get('expires_in', 3600)} seconds")
                
                return self.tokens[server_name]
            else:
                logger.error(f"❌ Token exchange failed for {server_name}: {response.status_code}")
                logger.error(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception during token exchange for {server_name}: {e}")
            return None
    
    def get_access_token(self, server_name: str) -> Optional[str]:
        """
        Get a valid access token for a server.
        
        Args:
            server_name: Name of the server
        
        Returns:
            Access token string or None if not available
        """
        if server_name not in self.tokens:
            return None
        
        token_info = self.tokens[server_name]
        
        # Check if token is expired
        if self._is_token_expired(server_name):
            logger.warning(f"⚠️  Access token for {server_name} has expired")
            # Try to refresh if refresh token available
            if token_info.get('refresh_token'):
                logger.info(f"🔄 Attempting to refresh token for {server_name}")
                # Token refresh will be implemented separately
                return None
            return None
        
        return token_info.get('access_token')
    
    def _is_token_expired(self, server_name: str) -> bool:
        """Check if a token is expired"""
        if server_name not in self.tokens:
            return True
        
        token_info = self.tokens[server_name]
        expires_at = token_info.get('expires_at')
        
        if not expires_at:
            return True
        
        try:
            expiry_time = datetime.fromisoformat(expires_at)
            # Consider expired if less than 5 minutes remaining
            buffer_time = timedelta(minutes=5)
            return datetime.now() >= (expiry_time - buffer_time)
        except Exception:
            return True
    
    def refresh_token(
        self,
        server_name: str,
        token_url: str,
        client_id: str,
        client_secret: str
    ) -> Optional[Dict[str, Any]]:
        """
        Refresh an access token using a refresh token.
        
        Args:
            server_name: Name of the server
            token_url: URL to refresh token
            client_id: OAuth client ID
            client_secret: OAuth client secret
        
        Returns:
            New token response dict or None if failed
        """
        if server_name not in self.tokens:
            logger.error(f"❌ No token found for {server_name} to refresh")
            return None
        
        refresh_token = self.tokens[server_name].get('refresh_token')
        if not refresh_token:
            logger.error(f"❌ No refresh token available for {server_name}")
            return None
        
        logger.info(f"🔄 Refreshing access token for {server_name}...")
        
        try:
            data = {
                'grant_type': 'refresh_token',
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            response = requests.post(token_url, data=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Update stored token
                self.tokens[server_name].update({
                    'access_token': token_data.get('access_token'),
                    'refresh_token': token_data.get('refresh_token', refresh_token),
                    'expires_in': token_data.get('expires_in', 3600),
                    'expires_at': (datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))).isoformat(),
                    'refreshed_at': datetime.now().isoformat()
                })
                
                self._save_tokens()
                logger.info(f"✅ Successfully refreshed token for {server_name}")
                
                return self.tokens[server_name]
            else:
                logger.error(f"❌ Token refresh failed for {server_name}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Exception during token refresh for {server_name}: {e}")
            return None
    
    def get_auth_header(self, server_name: str) -> Optional[Dict[str, str]]:
        """
        Get the authorization header for a server.
        
        Args:
            server_name: Name of the server
        
        Returns:
            Dict with Authorization header or None
        """
        access_token = self.get_access_token(server_name)
        if not access_token:
            return None
        
        token_type = self.tokens[server_name].get('token_type', 'Bearer')
        return {
            'Authorization': f'{token_type} {access_token}'
        }
    
    def clear_token(self, server_name: str) -> None:
        """Clear stored token for a server"""
        if server_name in self.tokens:
            del self.tokens[server_name]
            self._save_tokens()
            logger.info(f"🗑️  Cleared token for {server_name}")
    
    def get_token_status(self, server_name: str) -> Dict[str, Any]:
        """
        Get detailed status of a token.
        
        Args:
            server_name: Name of the server
        
        Returns:
            Dict with token status information
        """
        if server_name not in self.tokens:
            return {
                'status': 'no_token',
                'message': f'No token stored for {server_name}',
                'has_token': False
            }
        
        token_info = self.tokens[server_name]
        is_expired = self._is_token_expired(server_name)
        
        if is_expired:
            return {
                'status': 'expired',
                'message': f'Token for {server_name} has expired',
                'has_token': True,
                'has_refresh_token': bool(token_info.get('refresh_token')),
                'expired_at': token_info.get('expires_at')
            }
        
        return {
            'status': 'valid',
            'message': f'Valid token available for {server_name}',
            'has_token': True,
            'expires_at': token_info.get('expires_at'),
            'token_type': token_info.get('token_type')
        }


# Global OAuth manager instance
oauth_manager = OAuthTokenManager()
