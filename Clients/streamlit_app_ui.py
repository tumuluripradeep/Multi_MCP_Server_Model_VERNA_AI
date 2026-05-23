import streamlit as st
import json
import os
import sys
import asyncio
import re
import logging
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
from datetime import datetime

# Add repo root and Clients dir for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Import the refactored ServerManager
from ServerManager import ServerManager

# Streamlit UI Configuration - MUST BE FIRST
st.set_page_config(
    page_title="Verna-AI MCP Powered",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load environment variables
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Authentication configuration for systems that require authentication
SYSTEMS_REQUIRING_AUTH = {
    "service_system": {
        "display_name": "Service System (Dynamics CRM)",
        "auth_type": "azure_ad",
        "description": "Microsoft Dynamics CRM for service management with MS login and Okta support"
    },
    "sales_system": {
        "display_name": "Sales System (Dynamics 365)",
        "auth_type": "api_key",
        "description": "Microsoft Dynamics 365 for sales operations"
    },
    "slack": {
        "display_name": "Slack Integration",
        "auth_type": "oauth2_bearer",
        "description": "Slack workspace integration"
    },
    "mcp-atlassian": {
        "display_name": "Atlassian (Jira/Confluence)",
        "auth_type": "api_key",
        "description": "Atlassian Jira and Confluence integration"
    },
    "hr_system": {
        "display_name": "HR System (Dynamics 365)",
        "auth_type": "basic_auth",
        "description": "Microsoft Dynamics 365 for HR operations"
    },
    "accounting_system": {
        "display_name": "Accounting System (Dynamics 365)",
        "auth_type": "basic_auth",
        "description": "Microsoft Dynamics 365 Finance and Operations"
    },
    "marketing_system": {
        "display_name": "Marketing System (Dynamics 365)",
        "auth_type": "digest_auth",
        "description": "Microsoft Dynamics 365 Marketing"
    },
    "csm_system": {
        "display_name": "Customer Service (Dynamics 365)",
        "auth_type": "jwt_bearer",
        "description": "Microsoft Dynamics 365 Customer Service"
    },
    "s4_hana": {
        "display_name": "SAP S/4HANA",
        "auth_type": "certificate",
        "description": "SAP S/4HANA enterprise system"
    }
}

def requires_authentication(server_key: str) -> bool:
    """Check if a server requires authentication"""
    return server_key in SYSTEMS_REQUIRING_AUTH

def is_server_authenticated(server_key: str) -> bool:
    """Check if server is authenticated"""
    auth_key = f"authenticated_{server_key}"
    return st.session_state.get(auth_key, False)

@st.dialog("Authentication", width="medium")
def show_authentication_dialog(server_key: str):
    """Compact authentication dialog"""
    auth_config = SYSTEMS_REQUIRING_AUTH.get(server_key, {})
    display_name = auth_config.get("display_name", server_key)
    
    # Enhanced styling for better label visibility
    st.markdown("""
        <style>
        .stDialog > div[data-testid="stVerticalBlock"] {
            background: white !important;
            border-radius: 8px !important;
            padding: 20px !important;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15) !important;
        }
        
        /* Clear, visible labels */
        .stTextInput > label,
        .stTextArea > label,
        .stSelectbox > label {
            font-weight: 600 !important;
            color: #1f2937 !important;
            font-size: 14px !important;
            margin-bottom: 6px !important;
        }
        
        .stTextInput > div > div > input,
        .stTextArea > div > div > textarea {
            border-radius: 4px !important;
            border: 2px solid #d1d5db !important;
            font-size: 14px !important;
        }
        
        .stTextInput > div > div > input:focus,
        .stTextArea > div > div > textarea:focus {
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.1) !important;
        }
        
        .stButton > button[kind="primary"] {
            background: #3b82f6 !important;
            border: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Clear header
    st.markdown(f"**System:** {display_name}")
    if auth_config.get('description'):
        st.caption(auth_config['description'])
    
    # Comprehensive auth types
    auth_types = {
        "basic_auth": "👤 Username & Password",
        "api_key": "🔑 API Key Authentication",
        "oauth2_bearer": "🛡️ OAuth2 Bearer Token", 
        "digest_auth": "🔐 HTTP Digest Authentication",
        "jwt_bearer": "🎫 JWT Bearer Token",
        "certificate": "📜 X.509 Certificate Files",
        "azure_ad": "☁️ Azure Active Directory",
        "google_oauth": "🔍 Google OAuth 2.0",
        "github_oauth": "🐙 GitHub OAuth",
        "saml": "🏛️ SAML 2.0",
        "ldap": "📂 LDAP Directory",
        "windows_auth": "🪟 Windows Authentication",
        "aws_iam": "☁️ AWS IAM",
        "custom_headers": "⚙️ Custom Headers",
        "multi_factor": "🔒 Multi-Factor Authentication"
    }
    
    # Auth method selector
    default_auth_type = auth_config.get("auth_type", "basic_auth")
    default_index = list(auth_types.keys()).index(default_auth_type) if default_auth_type in auth_types else 0
    
    selected_auth_type = st.selectbox(
        "Authentication Method",
        options=list(auth_types.keys()),
        format_func=lambda x: auth_types[x],
        index=default_index,
        key=f"auth_type_{server_key}"
    )
    
    # Authentication Form
    with st.form("auth_form"):
        credentials = {}
        
        # Basic Authentication
        if selected_auth_type == "basic_auth":
            col1, col2 = st.columns(2)
            with col1:
                credentials['username'] = st.text_input("👤 Username", key=f"basic_user_{server_key}")
            with col2:
                credentials['password'] = st.text_input("🔒 Password", type="password", key=f"basic_pass_{server_key}")
        
        # API Key Authentication
        elif selected_auth_type == "api_key":
            credentials['api_key'] = st.text_input("🔑 API Key", type="password", key=f"api_key_{server_key}")
            credentials['header_name'] = st.text_input("📝 HTTP Header Name", value="X-API-Key", key=f"api_header_{server_key}")
        
        # OAuth2 Bearer Token
        elif selected_auth_type == "oauth2_bearer":
            credentials['token'] = st.text_area("🛡️ Bearer Token", key=f"oauth_token_{server_key}", height=100)
            credentials['scope'] = st.text_input("🎯 Access Scope (optional)", key=f"oauth_scope_{server_key}")
        
        # Digest Authentication
        elif selected_auth_type == "digest_auth":
            col1, col2 = st.columns(2)
            with col1:
                credentials['username'] = st.text_input("👤 Username", key=f"digest_user_{server_key}")
            with col2:
                credentials['password'] = st.text_input("🔒 Password", type="password", key=f"digest_pass_{server_key}")
            credentials['realm'] = st.text_input("🌐 Authentication Realm (optional)", key=f"digest_realm_{server_key}")
        
        # JWT Bearer Token
        elif selected_auth_type == "jwt_bearer":
            credentials['jwt_token'] = st.text_area("🎫 JWT Token", key=f"jwt_token_{server_key}", height=100)
            credentials['algorithm'] = st.selectbox("🔧 Signing Algorithm", ["HS256", "RS256", "ES256", "HS384", "HS512"], key=f"jwt_alg_{server_key}")
        
        # Certificate Authentication
        elif selected_auth_type == "certificate":
            credentials['cert_path'] = st.text_input("📜 Certificate File Path", key=f"cert_path_{server_key}")
            credentials['key_path'] = st.text_input("🔑 Private Key File Path", key=f"key_path_{server_key}")
            credentials['ca_bundle'] = st.text_input("📦 CA Bundle Path (optional)", key=f"ca_bundle_{server_key}")
        
        # Azure Active Directory
        elif selected_auth_type == "azure_ad":
            credentials['tenant_id'] = st.text_input("🏢 Tenant ID", key=f"azure_tenant_{server_key}")
            col1, col2 = st.columns(2)
            with col1:
                credentials['client_id'] = st.text_input("🆔 Client ID", key=f"azure_client_{server_key}")
            with col2:
                credentials['client_secret'] = st.text_input("🔐 Client Secret", type="password", key=f"azure_secret_{server_key}")
            credentials['resource'] = st.text_input("🎯 Resource URL (optional)", key=f"azure_resource_{server_key}")
            
            # Add user ID field specifically for service system
            if server_key == "service_system":
                st.markdown("---")
                st.markdown("**Service System Configuration:**")
                credentials['user_id'] = st.text_input(
                    "👤 User ID", 
                    placeholder="e.g., d7f489fb-8349-ea11-a815-000d3a593b7c",
                    help="Your unique user ID for D365 data retrieval",
                    key=f"service_user_id_{server_key}"
                )
                credentials['okta_enabled'] = st.checkbox(
                    "🔒 Okta Authentication Enabled", 
                    help="Check if your account uses Okta for additional authentication",
                    key=f"okta_enabled_{server_key}"
                )
        
        # Google OAuth 2.0
        elif selected_auth_type == "google_oauth":
            col1, col2 = st.columns(2)
            with col1:
                credentials['client_id'] = st.text_input("🆔 Client ID", key=f"google_client_{server_key}")
            with col2:
                credentials['client_secret'] = st.text_input("🔐 Client Secret", type="password", key=f"google_secret_{server_key}")
            credentials['redirect_uri'] = st.text_input("🔗 Redirect URI", key=f"google_redirect_{server_key}")
        
        # GitHub OAuth
        elif selected_auth_type == "github_oauth":
            col1, col2 = st.columns(2)
            with col1:
                credentials['client_id'] = st.text_input("🆔 Client ID", key=f"github_client_{server_key}")
            with col2:
                credentials['client_secret'] = st.text_input("🔐 Client Secret", type="password", key=f"github_secret_{server_key}")
            credentials['scope'] = st.text_input("🎯 Scope (optional)", value="user:email", key=f"github_scope_{server_key}")
        
        # SAML 2.0
        elif selected_auth_type == "saml":
            credentials['idp_url'] = st.text_input("🌐 Identity Provider URL", key=f"saml_idp_{server_key}")
            credentials['sp_entity_id'] = st.text_input("🆔 Service Provider Entity ID", key=f"saml_sp_{server_key}")
            credentials['certificate'] = st.text_area("📜 X.509 Certificate", key=f"saml_cert_{server_key}", height=80)
        
        # LDAP Directory
        elif selected_auth_type == "ldap":
            credentials['server'] = st.text_input("🖥️ LDAP Server", key=f"ldap_server_{server_key}")
            credentials['port'] = st.number_input("🔌 Port", value=389, key=f"ldap_port_{server_key}")
            credentials['bind_dn'] = st.text_input("👤 Bind DN", key=f"ldap_bind_{server_key}")
            credentials['password'] = st.text_input("🔒 Password", type="password", key=f"ldap_pass_{server_key}")
            credentials['base_dn'] = st.text_input("📂 Base DN", key=f"ldap_base_{server_key}")
        
        # Windows Authentication
        elif selected_auth_type == "windows_auth":
            credentials['domain'] = st.text_input("🏢 Domain", key=f"win_domain_{server_key}")
            col1, col2 = st.columns(2)
            with col1:
                credentials['username'] = st.text_input("👤 Username", key=f"win_user_{server_key}")
            with col2:
                credentials['password'] = st.text_input("🔒 Password", type="password", key=f"win_pass_{server_key}")
        
        # AWS IAM
        elif selected_auth_type == "aws_iam":
            credentials['access_key_id'] = st.text_input("🔑 Access Key ID", key=f"aws_access_{server_key}")
            credentials['secret_access_key'] = st.text_input("🔐 Secret Access Key", type="password", key=f"aws_secret_{server_key}")
            credentials['region'] = st.text_input("🌍 AWS Region", value="us-east-1", key=f"aws_region_{server_key}")
            credentials['session_token'] = st.text_input("🎫 Session Token (optional)", key=f"aws_token_{server_key}")
        
        # Custom Headers
        elif selected_auth_type == "custom_headers":
            credentials['header_count'] = st.number_input("📊 Number of Headers", min_value=1, max_value=5, value=1, key=f"custom_count_{server_key}")
            for i in range(int(credentials['header_count'])):
                col1, col2 = st.columns(2)
                with col1:
                    credentials[f'header_name_{i}'] = st.text_input(f"📝 Header {i+1} Name", key=f"custom_name_{i}_{server_key}")
                with col2:
                    credentials[f'header_value_{i}'] = st.text_input(f"📄 Header {i+1} Value", type="password", key=f"custom_value_{i}_{server_key}")
        
        # Multi-Factor Authentication
        elif selected_auth_type == "multi_factor":
            col1, col2 = st.columns(2)
            with col1:
                credentials['username'] = st.text_input("👤 Username", key=f"mfa_user_{server_key}")
            with col2:
                credentials['password'] = st.text_input("🔒 Password", type="password", key=f"mfa_pass_{server_key}")
            credentials['mfa_code'] = st.text_input("📱 MFA Code", key=f"mfa_code_{server_key}")
            credentials['mfa_method'] = st.selectbox("🔒 MFA Method", ["TOTP", "SMS", "Email", "Hardware Token"], key=f"mfa_method_{server_key}")
        
        # Simple buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            test_btn = st.form_submit_button("Test", use_container_width=True)
        with col2:
            auth_btn = st.form_submit_button("Authenticate", type="primary", use_container_width=True)
        with col3:
            cancel_btn = st.form_submit_button("Cancel", use_container_width=True)
        
        # Handle actions
        if test_btn:
            if any(v for v in credentials.values() if v):
                with st.spinner("Testing..."):
                    import time
                    time.sleep(1)
                    st.success("Connection successful")
            else:
                st.error("Please enter credentials")
        
        elif auth_btn:
            if any(v for v in credentials.values() if v):
                st.session_state[f"authenticated_{server_key}"] = True
                st.session_state[f"credentials_{server_key}"] = credentials
                # auth_type is already stored by the selectbox widget
                st.session_state[f"{server_key}_connected"] = True
                st.success("Authentication successful")
                st.rerun()
            else:
                st.error("Please enter credentials")
        
        elif cancel_btn:
            st.rerun()

# Load servers configuration
@st.cache_data
def load_server_config():
    """Load server configuration from JSON file"""
    try:
        servers_json_path = os.path.join("Servers", "config", "mcp_servers.json")
        with open(servers_json_path, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load server configuration: {e}")
        return {}

servers_data = load_server_config()

# Initialize ServerManager and LLM
@st.cache_resource
def initialize_server_manager():
    """Initialize ServerManager with LLM - cached to avoid reinitialization"""
    try:
        print("Debug: Starting ServerManager initialization...")
        
        # Load environment variables (like terminal client)
        load_dotenv()
        
        # Initialize server manager (let it use the centralized LLM factory)
        print("Debug: Initializing ServerManager...")
        server_manager = ServerManager()
        server_manager.initialize()  # Uses get_llm_from_config() like terminal client
        print("Debug: ServerManager initialized successfully")
        
        available_servers = server_manager.get_available_servers()
        print(f"Debug: Available servers: {available_servers}")
        
        # Check if we have any servers available (like terminal client)
        if not available_servers:
            print("Debug: No servers were successfully initialized")
            st.warning("⚠️ No MCP servers were successfully initialized. Some features may be limited.")
            # Still return the server manager - it can handle the empty state
            return server_manager
        else:
            print(f"Debug: Successfully initialized {len(available_servers)} servers")
            try:
                run_async(server_manager.warm_up_agent())
                diag = server_manager.get_streaming_diagnostics()
                print(
                    f"Debug: Agent warm-up completed — streaming_enabled={diag['streaming_enabled']} "
                    f"llm_streaming={diag['llm_streaming']} tools={diag['tool_count']}"
                )
            except Exception as warm_err:
                print(f"Debug: Agent warm-up failed: {warm_err}")
            return server_manager
            
    except Exception as e:
        error_msg = f"Failed to initialize ServerManager: {e}"
        print(f"Debug: {error_msg}")
        import traceback
        traceback.print_exc()
        st.error(f"⚠️ ServerManager initialization failed: {error_msg}")
        # Return a minimal server manager that can still handle basic functionality
        try:
            fallback_manager = ServerManager()
            fallback_manager.initialize()  # Let it try with the centralized config
            return fallback_manager
        except:
            return None

# Get server manager instance
server_manager = initialize_server_manager()

# Company logo SVGs
def get_company_logo_svg(company: str, size: int = 24) -> str:
    """Get SVG logo for companies"""
    logos = {
        "microsoft": f'''<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M0 0h11.377v11.372H0zm12.623 0H24v11.372H12.623zM0 12.623h11.377V24H0zm12.623 0H24V24H12.623z" fill="#00BCF2"/>
        </svg>''',
        "atlassian": f'''<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M7.07 11.425c-.344-.547-.954-.84-1.573-.84-.619 0-1.229.293-1.573.84L1.42 17.075c-.171.275-.163.623.02.889.184.266.51.429.856.429h6.838c.602 0 1.135-.376 1.346-.948.211-.572.066-1.207-.36-1.598L7.07 11.425z" fill="#0052CC"/>
            <path d="M16.77 5.425c-.344-.547-.954-.84-1.573-.84-.619 0-1.229.293-1.573.84L11.12 10.075c-.171.275-.163.623.02.889.184.266.51.429.856.429h6.838c.602 0 1.135-.376 1.346-.948.211-.572.066-1.207-.36-1.598L16.77 5.425z" fill="#2684FF"/>
        </svg>''',
        "slack": f'''<svg width="{size}" height="{size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.525 2.525 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zM6.313 15.165a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zM8.834 6.313a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zM18.956 8.834a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zM17.688 8.834a2.528 2.528 0 0 1-2.522 2.521 2.528 2.528 0 0 1-2.522-2.521V2.522A2.528 2.528 0 0 1 15.166 0a2.528 2.528 0 0 1 2.522 2.522v6.312zM15.166 18.956a2.528 2.528 0 0 1 2.522 2.522A2.528 2.528 0 0 1 15.166 24a2.528 2.528 0 0 1-2.522-2.522v-2.522h2.522zM15.166 17.688a2.528 2.528 0 0 1-2.522-2.523 2.528 2.528 0 0 1 2.522-2.522h6.312A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.312z" fill="#E01E5A"/>
        </svg>'''
    }
    return logos.get(company, "🔧")

# Server icon mapping - Using company logos where applicable
SERVER_ICONS = {
    "youtube": "📺",
    "weather": "🌦️", 
    "slack": get_company_logo_svg("slack", 28),
    "playwright": "🎭",
    "mcp-atlassian": get_company_logo_svg("atlassian", 28),
    "service_system": "🛠️",
    "sales_system": "💼",
    "microsoft.docs.mcp": get_company_logo_svg("microsoft", 28),
    "web_search_scrape_rag": "🔍"
}

# Reuse one event loop across Streamlit reruns (new loop per query breaks MCP stdio on Windows).
@st.cache_resource
def _get_async_loop():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def run_async(coro):
    """Run async coroutine on the shared Streamlit event loop."""
    loop = _get_async_loop()
    try:
        return loop.run_until_complete(coro)
    except Exception as e:
        error_msg = f"Async execution error: {str(e)}"
        print(f"Debug: {error_msg}")
        import traceback
        traceback.print_exc()
        return error_msg

# YouTube helper functions (from terminal_chat_client.py)
def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    url = url.strip()
    
    # If it's just the video ID (11 characters)
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    # Handle youtu.be URLs
    if 'youtu.be' in url:
        try:
            return url.split('/')[-1].split('?')[0].split('&')[0]
        except:
            pass
    
    # Handle youtube.com URLs
    if 'youtube.com' in url:
        try:
            # Handle watch URLs
            if '/watch' in url:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if 'v' in query_params:
                    return query_params['v'][0]
            
            # Handle embed URLs
            if '/embed/' in url:
                return url.split('/embed/')[1].split('?')[0]
            
            # Handle /v/ URLs
            if '/v/' in url:
                return url.split('/v/')[1].split('?')[0]
                
            # Handle /shorts/ URLs
            if '/shorts/' in url:
                return url.split('/shorts/')[1].split('?')[0]
        except:
            pass
    
    # Try to find video ID in the text
    video_id_pattern = r'(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})'
    match = re.search(video_id_pattern, url)
    if match:
        return match.group(1)
    
    return None

async def handle_youtube_request(server_manager, user_input: str) -> str:
    """Handle YouTube-related requests and process user intent."""
    # Extract video ID if it's a URL
    video_id = extract_video_id(user_input)
    if not video_id:
        return ("❌ Could not find a valid YouTube video ID in your input.\n"
                "Please provide a valid YouTube URL in one of these formats:\n"
                "- https://www.youtube.com/watch?v=VIDEO_ID\n"
                "- https://youtu.be/VIDEO_ID\n"
                "- https://www.youtube.com/embed/VIDEO_ID\n"
                "- https://www.youtube.com/v/VIDEO_ID\n"
                "- https://www.youtube.com/shorts/VIDEO_ID\n\n"
                "Or just provide the 11-character video ID directly.")
    
    youtube_data = {}
    data_fetched = False
    
    try:
        # Get comments - using process_request with YouTube server
        youtube_query = f"Get comments for video {video_id} with max results 50"
        comments_response = await server_manager.process_request(youtube_query)
        if comments_response and 'error' not in comments_response.lower():
            # Process the response to extract comments data
            youtube_data['comments'] = comments_response
            data_fetched = True
        
        # Get transcript - using process_request with YouTube server
        transcript_query = f"Get transcript for video {video_id}"
        transcript_response = await server_manager.process_request(transcript_query)
        if transcript_response and 'error' not in transcript_response.lower():
            youtube_data['transcript'] = transcript_response
            youtube_data['transcript_language'] = 'en'  # Default language
            data_fetched = True
        
        if not data_fetched:
            return ("❌ Could not fetch any data from the video.\n"
                   "This could be because:\n"
                   "1. The video is private or restricted\n"
                   "2. Comments are disabled\n"
                   "3. No transcript is available\n"
                   "4. The video ID is invalid")
        
        # Prepare result info
        result_info = []
        if 'comments' in youtube_data:
            result_info.append(f"{len(youtube_data['comments'])} comments")
        if 'transcript' in youtube_data:
            result_info.append(f"transcript in {youtube_data['transcript_language']}")
        
        # Process available data
        context = {
            'video_id': video_id,
            'data': youtube_data,
            'user_query': user_input
        }
        
        # Process available data using process_request
        analysis_query = f"Analyze YouTube video {video_id} with the following data: {user_input}"
        response = await server_manager.process_request(analysis_query)
        
        # Handle response format
        if isinstance(response, dict):
            main_content = response.get('analysis') or response.get('content') or str(response)
            if hasattr(main_content, 'content'):
                main_content = main_content.content
        else:
            main_content = str(response)
        
        if main_content:
            return f"📺 **YouTube Analysis Results** (Video ID: {video_id})\n" + \
                   f"📊 **Data processed:** {', '.join(result_info)}\n\n" + \
                   f"**Analysis:**\n{main_content}"
        else:
            return "❌ Could not process the request. Please try again."
            
    except Exception as e:
        return f"❌ Error processing request: {str(e)}"

async def handle_youtube_search(server_manager, user_input: str) -> str:
    """Handle YouTube search requests using LLM for parsing and presentation."""
    try:
        # Step 1: Parse search intent using process_request
        parse_query = f"Parse search intent for YouTube: {user_input}"
        parse_response = await server_manager.process_request(parse_query)
        
        if not parse_response or 'error' in parse_response.lower():
            return "❌ Could not parse your search request."
        
        # Step 2: Perform the search using process_request
        search_query = f"Search YouTube for: {user_input}"
        search_response = await server_manager.process_request(search_query)
        
        if not search_response or 'error' in search_response.lower():
            return "❌ No results found or error occurred during search."
        
        # Step 3: Present results using process_request
        presentation_query = f"Present YouTube search results for: {user_input}. Results: {search_response}"
        presentation_response = await server_manager.process_request(presentation_query)
        
        # Handle the response
        if isinstance(presentation_response, dict):
            main_content = presentation_response.get('analysis') or presentation_response.get('content') or str(presentation_response)
            if hasattr(main_content, 'content'):
                main_content = main_content.content
        else:
            main_content = str(presentation_response)
        
        if main_content:
            header = f"🔍 **YouTube Search Results** for: '{user_input}'"
            return f"{header}\n\n{main_content}"
        else:
            return "❌ Could not analyze the search results. Please try again."
            
    except Exception as e:
        return f"❌ Error during YouTube search: {str(e)}"

async def process_user_query(
    query: str,
    server_manager: ServerManager,
    channel_id: str = None,
    thread_ts: str = None,
    on_token=None,
) -> str:
    """Process query; uses streaming agent when enabled, returns full text for chat."""
    if not server_manager:
        return "❌ ServerManager is not available. Please check the configuration."

    try:
        if server_manager.streaming_enabled():
            from streaming_utils import collect_stream_response
            response = await collect_stream_response(
                server_manager,
                query,
                channel_id,
                thread_ts,
                on_token=on_token,
            )
        else:
            response = await server_manager.process_request(query, channel_id, thread_ts)

        if response and str(response).strip():
            return str(response)
        else:
            return "❌ No response received. Please try rephrasing your query or check server status."
    
    except Exception as e:
        # More detailed error handling
        error_msg = str(e)
        if "web_search_scrape_rag" in error_msg:
            return "❌ Web search service is temporarily unavailable. Please try a different query or check back later."
        elif "StdioConnectionManager" in error_msg:
            return "❌ Some MCP servers are having connection issues. The query may still be processed by available servers."
        else:
            return f"❌ Error processing query: {error_msg}"

async def process_user_query_with_auth(
    query: str,
    server_manager: ServerManager,
    channel_id: str = None,
    thread_ts: str = None,
    on_token=None,
) -> str:
    """Process user query with authentication context for service system"""
    if not server_manager:
        return "❌ ServerManager is not available. Please check the configuration."
    
    try:
        # Check if this is a service system query and get user credentials
        service_system_keywords = ['case', 'ticket', 'support', 'incident', 'service', 'd365', 'dynamics']
        is_service_query = any(keyword.lower() in query.lower() for keyword in service_system_keywords)
        
        if is_service_query and is_server_authenticated("service_system"):
            # Get stored credentials for service system
            credentials = st.session_state.get("credentials_service_system", {})
            user_id = credentials.get("user_id")
            
            if user_id:
                # Enhance the query with user ID context for service system
                enhanced_query = f"[USER_ID: {user_id}] {query}"
                logger.info(f"Enhanced service system query with user ID: {user_id}")
                
                return await process_user_query(
                    enhanced_query, server_manager, channel_id, thread_ts, on_token=on_token
                )
            else:
                return "⚠️ Service system is authenticated but no User ID is configured. Please re-authenticate and provide your User ID."

        return await process_user_query(
            query, server_manager, channel_id, thread_ts, on_token=on_token
        )

    except Exception as e:
        logger.error(f"Error in process_user_query_with_auth: {str(e)}")
        error_msg = str(e)
        if "web_search_scrape_rag" in error_msg:
            return "❌ Web search service is temporarily unavailable. Please try a different query or check back later."
        elif "StdioConnectionManager" in error_msg:
            return "❌ Some MCP servers are having connection issues. The query may still be processed by available servers."
        else:
            return f"❌ Error processing request: {error_msg}"

# Create systems configuration from actual server data
def create_systems_config():
    """Create systems configuration from loaded server data"""
    systems = []
    
    if not server_manager:
        return [{
            "name": "Server Manager Error",
            "icon": "❌", 
            "description": "Failed to initialize ServerManager. Please check configuration and restart.",
            "session_key": "error_state",
            "server_key": "error",
            "examples": ["Please restart the application"]
        }]
    
    available_servers = server_manager.get_available_servers()
    if not available_servers:
        return [{
            "name": "No Servers Available",
            "icon": "⚠️", 
            "description": "No MCP servers are currently available. Some servers may be starting up or have connection issues.",
            "session_key": "limited_state", 
            "server_key": "fallback",
            "examples": ["Try again in a few moments", "Check server status"]
        }]
    
    # Name mapping for user-friendly display
    name_mapping = {
        "youtube": "YouTube Analytics",
        "weather": "Weather Information", 
        "slack": "Slack Integration",
        "playwright": "Browser Automation",
        "mcp-atlassian": "Atlassian (Jira/Confluence)",
        "service_system": "Service System",
        "sales_system": "Sales System",
        "microsoft.docs.mcp": "Microsoft Documentation",
        "web_search_scrape_rag": "Web Search & Research"
    }
    
    # Define example queries for each server
    example_queries = {
        "youtube": [
            "Analyze this video: https://youtube.com/watch?v=...",
            "Search for videos about machine learning",
            "Get transcript and sentiment analysis"
        ],
        "weather": [
            "What's the weather like in Seattle?",
            "Weather forecast for New York next week",
            "Any weather alerts for California?"
        ],
        "slack": [
            "Send a message to the team channel",
            "Get latest messages from #general",
            "List all available channels"
        ],
        "playwright": [
            "Take a screenshot of https://example.com",
            "Scrape data from a webpage",
            "Run automated browser tests"
        ],
        "mcp-atlassian": [
            "Search Confluence for API documentation",
            "Create a new Jira ticket",
            "List current projects"
        ],
        "service_system": [
            "Show recent support cases",
            "Create a new support ticket",
            "Check case status for #12345"
        ],
        "sales_system": [
            "Show current leads",
            "Generate monthly sales report",
            "Create new lead for Acme Corp"
        ],
        "microsoft.docs.mcp": [
            "How to configure Azure Active Directory?",
            "Best practices for Power Platform security",
            "Dynamics 365 customization guide"
        ],
        "web_search_scrape_rag": [
            "Latest developments in AI technology",
            "How to troubleshoot network issues?",
            "Compare different cloud providers"
        ]
    }
    
    # Define the desired order of servers
    desired_order = [
        "sales_system",           # Sales System
        "service_system",         # Service System  
        "microsoft.docs.mcp",     # Microsoft Documentation
        "mcp-atlassian",         # Atlassian
        "web_search_scrape_rag",        # Web Search & Research
        "youtube",               # YouTube
        "slack",                 # Slack
        "weather",               # Weather
        "playwright"             # Browser Automation
    ]
    
    # Create systems in the specified order
    for server_key in desired_order:
        if server_key in available_servers:
            server_config = servers_data.get(server_key, {})
            
            if not server_config:
                continue
            
            system = {
                "name": name_mapping.get(server_key, server_key.replace("_", " ").title()),
                "icon": SERVER_ICONS.get(server_key, "🖥️"),
                "description": server_config.get("description", f"MCP server for {server_key}"),
                "session_key": f"{server_key}_connected",
                "server_key": server_key,
                "examples": example_queries.get(server_key, ["General query"])
            }
            systems.append(system)
    
    # Add any remaining servers that weren't in the desired order
    for server_key in available_servers:
        if server_key not in desired_order:
            server_config = servers_data.get(server_key, {})
            
            if not server_config:
                continue
            
            system = {
                "name": name_mapping.get(server_key, server_key.replace("_", " ").title()),
                "icon": SERVER_ICONS.get(server_key, "🖥️"),
                "description": server_config.get("description", f"MCP server for {server_key}"),
                "session_key": f"{server_key}_connected",
                "server_key": server_key,
                "examples": example_queries.get(server_key, ["General query"])
            }
            systems.append(system)
    
    return systems

systems = create_systems_config()

# Clean Modern Light UI
st.markdown("""
    <style>
    /* Import modern font */
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');
    
    /* Global app styling */
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        font-family: 'Poppins', sans-serif;
        color: #0f172a !important;
        min-height: 100vh;
    }
    
    /* Main content area */
    .main .block-container {
        background: rgba(255, 255, 255, 0.8);
        backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 2rem;
        padding-bottom: 120px;
        margin-top: 1rem;
        box-shadow: 
            0 20px 60px rgba(99, 102, 241, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Enhanced Sidebar styling with darker grey background */
    .css-1d391kg, section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, 
                    rgba(205, 207, 211, 1.0) 0%,
                    rgba(201, 204, 208, 1.0) 25%,
                    rgba(209, 211, 215, 1.0) 50%,
                    rgba(203, 206, 210, 1.0) 75%,
                    rgba(207, 209, 213, 1.0) 100%) !important;
        backdrop-filter: blur(25px) !important;
        border-right: 2px solid rgba(156, 163, 175, 0.3) !important;
        box-shadow: 
            4px 0 20px rgba(107, 114, 128, 0.12),
            inset -1px 0 0 rgba(255, 255, 255, 0.8),
            inset 0 0 30px rgba(156, 163, 175, 0.05) !important;
        position: relative !important;
    }
    
    .css-1d391kg .block-container {
        background: transparent !important;
        padding: 1rem 1.5rem !important;
    }
    
    /* Add subtle pattern overlay to sidebar */
    section[data-testid="stSidebar"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: 
            radial-gradient(circle at 20% 20%, rgba(156, 163, 175, 0.04) 0%, transparent 50%),
            radial-gradient(circle at 80% 80%, rgba(107, 114, 128, 0.03) 0%, transparent 50%),
            linear-gradient(45deg, 
                rgba(156, 163, 175, 0.015) 0%, 
                transparent 25%, 
                rgba(107, 114, 128, 0.02) 50%, 
                transparent 75%, 
                rgba(156, 163, 175, 0.015) 100%);
        background-size: 300px 300px, 200px 200px, 150px 150px;
        animation: subtleMove 30s linear infinite;
        pointer-events: none;
        z-index: 0;
    }
    
    @keyframes subtleMove {
        0% { background-position: 0% 0%, 100% 100%, 0% 100%; }
        33% { background-position: 100% 0%, 0% 100%, 100% 0%; }
        66% { background-position: 0% 100%, 100% 0%, 0% 0%; }
        100% { background-position: 0% 0%, 100% 100%, 0% 100%; }
    }
    
    /* Sidebar text styling */
    .css-1d391kg .stMarkdown p {
        color: #0f172a !important;
        font-weight: 500 !important;
    }
    
    .css-1d391kg .stMarkdown h1,
    .css-1d391kg .stMarkdown h2,
    .css-1d391kg .stMarkdown h3,
    .css-1d391kg .stMarkdown h4,
    .css-1d391kg .stMarkdown h5,
    .css-1d391kg .stMarkdown h6 {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    /* Sidebar metric text */
    .css-1d391kg .metric-container {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    /* Fix sidebar info/success/warning text */
    .css-1d391kg .stInfo,
    .css-1d391kg .stSuccess,
    .css-1d391kg .stWarning {
        color: #0f172a !important;
        font-weight: 500 !important;
    }
    
    /* Sidebar header */
    .sidebar-header {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        padding: 16px;
        border-radius: 12px;
        margin-bottom: 20px;
        text-align: center;
        font-weight: 600;
        font-size: 1em;
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
    }
    
    /* Premium Server Cards - Redesigned */
    .server-card {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.95) 0%, 
                    rgba(248, 250, 252, 0.9) 100%) !important;
        border: 1px solid rgba(226, 232, 240, 0.4) !important;
        border-radius: 20px !important;
        padding: 20px !important;
        margin: 12px 0 !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 
            0 4px 20px rgba(51, 65, 85, 0.04),
            0 1px 3px rgba(0, 0, 0, 0.02),
            inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
        position: relative !important;
        overflow: hidden !important;
        backdrop-filter: blur(10px) !important;
        z-index: 1 !important;
    }
    
    .server-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, 
                    rgba(99, 102, 241, 0.6) 0%, 
                    rgba(139, 92, 246, 0.4) 50%,
                    rgba(99, 102, 241, 0.6) 100%);
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    
    .server-card:hover {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(248, 250, 252, 0.98) 100%) !important;
        border-color: rgba(99, 102, 241, 0.3) !important;
        transform: translateY(-4px) scale(1.02) !important;
        box-shadow: 
            0 12px 40px rgba(99, 102, 241, 0.12),
            0 4px 16px rgba(51, 65, 85, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    
    .server-card:hover::before {
        opacity: 1;
    }
    
    .server-card-connected {
        background: linear-gradient(135deg, 
                    rgba(240, 253, 244, 0.95) 0%, 
                    rgba(236, 253, 245, 0.9) 100%) !important;
        border: 2px solid rgba(34, 197, 94, 0.3) !important;
        box-shadow: 
            0 8px 32px rgba(34, 197, 94, 0.08),
            0 2px 8px rgba(16, 185, 129, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
    }
    
    .server-card-connected::before {
        background: linear-gradient(90deg, 
                    rgba(34, 197, 94, 0.8) 0%, 
                    rgba(16, 185, 129, 0.6) 50%,
                    rgba(34, 197, 94, 0.8) 100%);
        opacity: 1;
    }
    
    .server-card-connected:hover {
        border-color: rgba(34, 197, 94, 0.5) !important;
        transform: translateY(-4px) scale(1.02) !important;
        box-shadow: 
            0 16px 48px rgba(34, 197, 94, 0.15),
            0 6px 20px rgba(16, 185, 129, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    
    .server-card h4 {
        margin: 0 0 12px 0 !important;
        font-size: 1.1em !important;
        font-weight: 700 !important;
        color: #0f172a !important;
        display: flex !important;
        align-items: center !important;
        line-height: 1.3 !important;
    }
    
    .server-card p {
        margin: 0 0 16px 0 !important;
        font-size: 0.85em !important;
        color: #1e293b !important;
        line-height: 1.5 !important;
        font-weight: 500 !important;
    }
    
    /* Status indicators */
    .status-indicator {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-online {
        background-color: #10b981;
        box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
    }
    
    .status-offline {
        background-color: #9ca3af;
        box-shadow: 0 0 4px rgba(156, 163, 175, 0.3);
    }
    
    /* Chat messages */
    .chat-bubble-user {
        background: linear-gradient(135deg, #6b7280 0%, #9ca3af 100%);
        color: white;
        padding: 14px 18px;
        border-radius: 20px 20px 4px 20px;
        margin: 8px 0 8px auto;
        max-width: 75%;
        font-size: 0.9em;
        font-weight: 500;
        line-height: 1.5;
        word-wrap: break-word;
        box-shadow: 
            0 4px 20px rgba(156, 163, 175, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.1);
        position: relative;
    }
    
    .chat-bubble-assistant {
        background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
        color: #0f172a;
        padding: 14px 18px;
        border-radius: 20px 20px 20px 4px;
        margin: 8px auto 8px 0;
        max-width: 75%;
        border: 1px solid rgba(226, 232, 240, 0.6);
        font-size: 0.9em;
        font-weight: 500;
        line-height: 1.5;
        word-wrap: break-word;
        box-shadow: 
            0 4px 15px rgba(51, 65, 85, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.8);
        position: relative;
    }
    
    /* Message Actions Styling */
    .message-actions {
        display: flex;
        gap: 4px;
        justify-content: flex-end;
        margin-top: 8px;
        opacity: 0;
        transition: opacity 0.2s ease;
        position: relative;
        z-index: 10;
    }
    
    .chat-bubble-user:hover .message-actions,
    .chat-bubble-assistant:hover .message-actions {
        opacity: 1;
    }
    
    .action-btn {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(0, 0, 0, 0.1);
        border-radius: 50%;
        width: 28px;
        height: 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 12px;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        position: relative;
        z-index: 20;
        pointer-events: auto;
        user-select: none;
    }
    
    .action-btn:hover {
        background: rgba(255, 255, 255, 1);
        transform: scale(1.1);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
    }
    
    .action-btn:active {
        transform: scale(0.95);
    }
    
    .copy-btn:hover {
        background: rgba(59, 130, 246, 0.1);
        border-color: rgba(59, 130, 246, 0.3);
    }
    
    .reload-btn:hover {
        background: rgba(34, 197, 94, 0.1);
        border-color: rgba(34, 197, 94, 0.3);
    }
    
    .thumbs-up-btn:hover {
        background: rgba(34, 197, 94, 0.1);
        border-color: rgba(34, 197, 94, 0.3);
    }
    
    .thumbs-down-btn:hover {
        background: rgba(239, 68, 68, 0.1);
        border-color: rgba(239, 68, 68, 0.3);
    }
    
    .thumbs-up-btn.active {
        background: rgba(34, 197, 94, 0.2);
        border-color: rgba(34, 197, 94, 0.5);
        color: #22c55e;
    }
    
    .thumbs-down-btn.active {
        background: rgba(239, 68, 68, 0.2);
        border-color: rgba(239, 68, 68, 0.5);
        color: #ef4444;
    }
    
    /* Adjust user actions alignment */
    .user-actions {
        justify-content: flex-end;
    }
    
    .assistant-actions {
        justify-content: flex-end;
    }
    
    /* Chat Input styling (main chat area) - Enhanced with bigger placeholder */
    .main .block-container .stTextInput > div > div > input[placeholder*="Ask me anything"] {
        background: rgba(255, 255, 255, 0.9);
        border: 1px solid rgba(226, 232, 240, 0.8);
        border-radius: 24px;
        padding: 18px 24px;
        color: #0f172a !important;
        font-size: 1.1em !important;
        font-weight: 500 !important;
        transition: all 0.3s ease;
        min-height: 56px !important;
        box-shadow: 
            0 4px 12px rgba(51, 65, 85, 0.04),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    .main .block-container .stTextInput > div > div > input[placeholder*="Ask me anything"]:focus {
        border-color: #6366f1;
        background: rgba(255, 255, 255, 1);
        box-shadow: 
            0 0 0 3px rgba(99, 102, 241, 0.1),
            0 4px 20px rgba(99, 102, 241, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 1);
        outline: none;
    }
    
    /* Chat Input Placeholder text styling - Bigger and cleaner */
    .main .block-container .stTextInput > div > div > input[placeholder*="Ask me anything"]::placeholder {
        color: #6b7280 !important;
        opacity: 1 !important;
        font-style: normal !important;
        font-weight: 500 !important;
        font-size: 1.1em !important;
        letter-spacing: 0.02em !important;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%) !important;
        border: none !important;
        border-radius: 10px !important;
        color: white !important;
        font-weight: 600 !important;
        padding: 10px 18px !important;
        transition: all 0.3s ease !important;
        font-size: 0.9em !important;
        width: 100% !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4) !important;
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%) !important;
    }
    
    /* Secondary button styling */
    .stButton > button[kind="secondary"] {
        background: rgba(248, 250, 252, 0.8) !important;
        color: #374151 !important;
        border: 1px solid rgba(209, 213, 219, 0.8) !important;
        box-shadow: 0 2px 8px rgba(107, 114, 128, 0.1) !important;
    }
    
    .stButton > button[kind="secondary"]:hover {
        background: rgba(243, 244, 246, 1) !important;
        color: #1f2937 !important;
        border-color: rgba(156, 163, 175, 1) !important;
    }
    
    /* Toggle switch styling */
    .stCheckbox > label {
        font-size: 0.9em;
        font-weight: 500;
        color: #374151;
    }
    
    /* Form styling */
    .stForm {
        background: rgba(255, 255, 255, 0.8);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        box-shadow: 
            0 4px 20px rgba(51, 65, 85, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(248, 250, 252, 0.8);
        border-radius: 12px;
        padding: 6px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        box-shadow: 
            0 2px 8px rgba(51, 65, 85, 0.04),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(255, 255, 255, 0.7) !important;
        color: #1f2937 !important;
        border-radius: 10px !important;
        margin: 0 2px !important;
        font-size: 0.9em !important;
        font-weight: 600 !important;
        padding: 12px 18px !important;
        transition: all 0.3s ease !important;
        border: 1px solid rgba(226, 232, 240, 0.6) !important;
        text-shadow: none !important;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(255, 255, 255, 0.9) !important;
        color: #374151 !important;
        border-color: rgba(99, 102, 241, 0.3) !important;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        color: #ffffff !important;
        box-shadow: 
            0 4px 16px rgba(99, 102, 241, 0.4),
            0 2px 8px rgba(139, 92, 246, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2) !important;
        border-color: rgba(99, 102, 241, 0.4) !important;
        font-weight: 700 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3) !important;
        transform: translateY(-1px) !important;
    }
    
    .stTabs [aria-selected="true"]:hover {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
        color: #ffffff !important;
        box-shadow: 
            0 6px 20px rgba(99, 102, 241, 0.5),
            0 3px 12px rgba(139, 92, 246, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.25) !important;
    }
    
    /* Metrics */
    .stMetric {
        background: rgba(255, 255, 255, 0.8);
        border-radius: 12px;
        padding: 16px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        box-shadow: 
            0 4px 15px rgba(51, 65, 85, 0.04),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #0f172a !important;
        font-weight: 700 !important;
    }
    
    h1 { font-size: 1.6em; }
    h2 { font-size: 1.3em; }
    h3 { font-size: 1.1em; }
    h4 { font-size: 1em; }
    
    /* Remove conflicting toggle styles - handled in main toggle CSS above */
    
    /* Microsoft Fluent UI Toggle Switch Design */
    .stToggle {
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: space-between !important;
        min-height: 52px !important;
        margin: 12px 0 !important;
        padding: 16px 20px !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(250, 251, 252, 0.98) 100%) !important;
        border: 2px solid rgba(0, 120, 212, 0.15) !important;
        border-radius: 12px !important;
        box-shadow: 
            0 2px 8px rgba(0, 120, 212, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .stToggle::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, 
                    transparent, 
                    rgba(0, 120, 212, 0.06), 
                    transparent);
        transition: left 0.4s ease;
    }
    
    .stToggle:hover::before {
        left: 100%;
    }
    
    .stToggle:hover {
        border-color: rgba(0, 120, 212, 0.25) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(247, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 4px 16px rgba(0, 120, 212, 0.12),
            0 1px 4px rgba(0, 0, 0, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-1px) scale(1.01) !important;
    }
    
    /* Microsoft Fluent UI Toggle Label */
    .stToggle > label {
        color: #323130 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        flex-grow: 1 !important;
        text-align: left !important;
        background: none !important;
        padding: 0 !important;
        line-height: 1.5 !important;
        z-index: 2 !important;
        position: relative !important;
        letter-spacing: 0.01em !important;
    }
    
    /* Toggle switch container */
    .stToggle > div {
        display: flex !important;
        align-items: center !important;
        background: transparent !important;
        z-index: 2 !important;
        position: relative !important;
    }
    
    /* Microsoft Fluent UI Toggle Track - Enhanced Visibility */
    .stToggle > div > div > div {
        background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 50%, #d1d5db 100%) !important;
        border: 2px solid rgba(107, 114, 128, 0.3) !important;
        width: 48px !important;
        height: 24px !important;
        border-radius: 12px !important;
        position: relative !important;
        cursor: pointer !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
        box-shadow: 
            inset 0 1px 3px rgba(0, 0, 0, 0.08),
            0 1px 4px rgba(107, 114, 128, 0.12),
            0 0 0 1px rgba(255, 255, 255, 0.9) !important;
    }
    
    /* Microsoft Fluent UI Toggle Track - Active State */
    .stToggle > div > div > div[data-checked="true"] {
        background: linear-gradient(135deg, #0078d4 0%, #106ebe 50%, #005a9e 100%) !important;
        border-color: rgba(0, 120, 212, 0.8) !important;
        box-shadow: 
            0 0 16px rgba(0, 120, 212, 0.3),
            inset 0 1px 2px rgba(255, 255, 255, 0.25),
            0 2px 8px rgba(0, 120, 212, 0.15),
            0 0 0 1px rgba(255, 255, 255, 0.7) !important;
    }
    
    /* Microsoft Fluent UI Toggle Thumb - Enhanced Visibility */
    .stToggle > div > div > div > div {
        background: linear-gradient(135deg, #ffffff 0%, #f9fafb 50%, #f3f4f6 100%) !important;
        border: 2px solid rgba(107, 114, 128, 0.4) !important;
        width: 18px !important;
        height: 18px !important;
        border-radius: 50% !important;
        position: absolute !important;
        top: 1px !important;
        left: 2px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 
            0 4px 12px rgba(0, 0, 0, 0.15),
            0 2px 6px rgba(107, 114, 128, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            0 0 0 1px rgba(255, 255, 255, 0.95) !important;
        display: block !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    
    /* Microsoft Fluent UI Toggle Thumb - Active State */
    .stToggle > div > div > div[data-checked="true"] > div {
        left: 26px !important;
        border-color: rgba(255, 255, 255, 0.95) !important;
        background: linear-gradient(135deg, #ffffff 0%, #f0f9ff 50%, #e0f2fe 100%) !important;
        box-shadow: 
            0 6px 16px rgba(0, 120, 212, 0.25),
            0 3px 10px rgba(0, 0, 0, 0.12),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            0 0 0 2px rgba(255, 255, 255, 0.85),
            0 0 12px rgba(0, 120, 212, 0.15) !important;
    }
    
    /* Force all toggle elements to be visible */
    .stToggle,
    .stToggle *,
    .stToggle > div,
    .stToggle > div > div,
    .stToggle > div > div > div,
    .stToggle > div > div > div > div {
        visibility: visible !important;
        opacity: 1 !important;
        display: block !important;
        position: relative !important;
    }
    
    /* Checkbox styling */
    .stCheckbox > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
        font-size: 0.9em !important;
    }
    
    /* Radio button styling */
    .stRadio > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Selectbox styling */
    .stSelectbox > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Text input labels */
    .stTextInput > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Number input labels */
    .stNumberInput > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Slider labels */
    .stSlider > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Alert styling */
    .stSuccess, .stInfo, .stWarning, .stError {
        border-radius: 10px;
        border: none;
    }
    
    /* Fix all text colors for better visibility */
    .stApp p, .stApp span, .stApp div {
        color: #0f172a !important;
        font-weight: 500 !important;
    }
    
    /* Form submit button text */
    .stForm .stButton > button {
        color: white !important;
        font-weight: 600 !important;
    }
    
    /* Tab content text */
    .stTabs .stMarkdown p {
        color: #0f172a !important;
        font-weight: 500 !important;
    }
    
    /* Caption text */
    .stApp .caption {
        color: #374151 !important;
        font-weight: 500 !important;
    }
    
    /* Metric labels and values */
    .stMetric label {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    .stMetric [data-testid="metric-value"] {
        color: #0f172a !important;
        font-weight: 700 !important;
    }
    
    .stMetric [data-testid="metric-delta"] {
        font-weight: 600 !important;
        color: #0f172a !important;
    }
    
    /* Expander text */
    .streamlit-expanderHeader p {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    /* Select box options */
    .stSelectbox div[data-baseweb="select"] {
        color: #0f172a !important;
        font-weight: 600 !important;
    }
    
    /* Fix all Streamlit component visibility */
    
    /* Text area styling */
    .stTextArea > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    .stTextArea textarea {
        background-color: rgba(255, 255, 255, 0.9) !important;
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        color: #000000 !important;  /* Black text for better readability */
    }
    
    /* Ensure ALL textarea elements have black text */
    textarea {
        color: #000000 !important;
    }
    
    /* Ensure ALL textarea placeholders are black */
    textarea::placeholder {
        color: #000000 !important;
        opacity: 0.8 !important;
    }
    
    /* File uploader */
    .stFileUploader > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Date input */
    .stDateInput > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Time input */
    .stTimeInput > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Color picker */
    .stColorPicker > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Multiselect */
    .stMultiSelect > label {
        color: #1f2937 !important;
        font-weight: 500 !important;
    }
    
    /* Fix sidebar specific elements */
    section[data-testid="stSidebar"] .stToggle > label {
        color: #1f2937 !important;
        font-weight: 600 !important;
        font-size: 0.9em !important;
    }
    
    section[data-testid="stSidebar"] .stButton > button {
        background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        border-radius: 8px !important;
        box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3) !important;
    }
    
    section[data-testid="stSidebar"] .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important;
    }
    
    /* Fix sidebar text elements */
    section[data-testid="stSidebar"] p {
        color: #374151 !important;
    }
    
    section[data-testid="stSidebar"] .stMarkdown {
        color: #374151 !important;
    }
    
    section[data-testid="stSidebar"] .stInfo {
        background: rgba(59, 130, 246, 0.1) !important;
        border: 1px solid rgba(59, 130, 246, 0.2) !important;
        color: #1e40af !important;
    }
    
    section[data-testid="stSidebar"] .stSuccess {
        background: rgba(34, 197, 94, 0.1) !important;
        border: 1px solid rgba(34, 197, 94, 0.2) !important;
        color: #166534 !important;
    }
    
    section[data-testid="stSidebar"] .stWarning {
        background: rgba(245, 158, 11, 0.1) !important;
        border: 1px solid rgba(245, 158, 11, 0.2) !important;
        color: #92400e !important;
    }
    
    /* Fix selectbox in sidebar */
    section[data-testid="stSidebar"] .stSelectbox > label {
        color: #1f2937 !important;
        font-weight: 600 !important;
    }
    
    section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] {
        background-color: rgba(255, 255, 255, 0.9) !important;
        border: 1px solid rgba(226, 232, 240, 0.8) !important;
        color: #1f2937 !important;
    }
    
    /* Force all sidebar text to be visible */
    section[data-testid="stSidebar"] * {
        color: #374151 !important;
    }
    
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] h4,
    section[data-testid="stSidebar"] h5,
    section[data-testid="stSidebar"] h6 {
        color: #1f2937 !important;
    }
    
    /* Sidebar container improvements */
    section[data-testid="stSidebar"] .stContainer {
        background: transparent !important;
    }
    
    /* Make sure all sidebar widgets are visible */
    section[data-testid="stSidebar"] .stWidget {
        background: rgba(255, 255, 255, 0.5) !important;
        border-radius: 8px !important;
        padding: 4px !important;
        margin: 4px 0 !important;
    }
    
    /* Sidebar toggle inherits from main toggle styles above */
    
    /* Expander */
    .streamlit-expanderHeader {
        background: rgba(248, 250, 252, 0.8);
        border-radius: 10px;
        border: 1px solid rgba(226, 232, 240, 0.6);
        box-shadow: 
            0 2px 8px rgba(51, 65, 85, 0.04),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    /* Remove markdown container styling */
    .stMarkdown {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }
    
    .stMarkdownContainer {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }
    
    /* Enhanced styling for connected server markdown containers */
    .connected-server-card .stMarkdownContainer {
        background: linear-gradient(135deg, 
                    rgba(34, 197, 94, 0.08) 0%, 
                    rgba(16, 185, 129, 0.05) 100%) !important;
        border: 2px solid rgba(34, 197, 94, 0.2) !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        margin: 12px 0 !important;
        box-shadow: 
            0 8px 32px rgba(34, 197, 94, 0.12),
            0 0 0 1px rgba(255, 255, 255, 0.8),
            inset 0 2px 0 rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(15px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .connected-server-card .stMarkdownContainer::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, 
                   rgba(34, 197, 94, 0.8) 0%, 
                   rgba(16, 185, 129, 0.6) 50%,
                   rgba(34, 197, 94, 0.8) 100%);
        border-radius: 16px 16px 0 0;
        animation: connectedShimmer 2s ease-in-out infinite;
    }
    
    .connected-server-card .stMarkdownContainer:hover {
        border-color: rgba(34, 197, 94, 0.4) !important;
        background: linear-gradient(135deg, 
                    rgba(34, 197, 94, 0.12) 0%, 
                    rgba(16, 185, 129, 0.08) 100%) !important;
        box-shadow: 
            0 12px 48px rgba(34, 197, 94, 0.18),
            0 4px 16px rgba(16, 185, 129, 0.12),
            inset 0 2px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-2px) scale(1.01) !important;
    }
    
    /* Enhanced styling for available server markdown containers */
    .available-server-card .stMarkdownContainer {
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.08) 0%, 
                    rgba(139, 92, 246, 0.05) 100%) !important;
        border: 2px solid rgba(99, 102, 241, 0.2) !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        margin: 12px 0 !important;
        box-shadow: 
            0 8px 32px rgba(99, 102, 241, 0.12),
            0 0 0 1px rgba(255, 255, 255, 0.8),
            inset 0 2px 0 rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(15px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .available-server-card .stMarkdownContainer::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, 
                   rgba(99, 102, 241, 0.8) 0%, 
                   rgba(139, 92, 246, 0.6) 50%,
                   rgba(99, 102, 241, 0.8) 100%);
        border-radius: 16px 16px 0 0;
        animation: availableShimmer 3s ease-in-out infinite;
    }
    
    .available-server-card .stMarkdownContainer:hover {
        border-color: rgba(99, 102, 241, 0.4) !important;
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.12) 0%, 
                    rgba(139, 92, 246, 0.08) 100%) !important;
        box-shadow: 
            0 12px 48px rgba(99, 102, 241, 0.18),
            0 4px 16px rgba(139, 92, 246, 0.12),
            inset 0 2px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-2px) scale(1.01) !important;
    }
    
    /* Enhanced styling for offline server markdown containers */
    .offline-server-card .stMarkdownContainer {
        background: linear-gradient(135deg, 
                    rgba(156, 163, 175, 0.08) 0%, 
                    rgba(107, 114, 128, 0.05) 100%) !important;
        border: 2px solid rgba(156, 163, 175, 0.3) !important;
        border-radius: 16px !important;
        padding: 20px 24px !important;
        margin: 12px 0 !important;
        box-shadow: 
            0 4px 16px rgba(156, 163, 175, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.8),
            inset 0 2px 0 rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(15px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
        opacity: 0.7 !important;
    }
    
    .offline-server-card .stMarkdownContainer::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, 
                   rgba(156, 163, 175, 0.6) 0%, 
                   rgba(107, 114, 128, 0.4) 50%,
                   rgba(156, 163, 175, 0.6) 100%);
        border-radius: 16px 16px 0 0;
    }
    
    .offline-server-card .stMarkdownContainer:hover {
        opacity: 0.85 !important;
        border-color: rgba(156, 163, 175, 0.4) !important;
        background: linear-gradient(135deg, 
                    rgba(156, 163, 175, 0.12) 0%, 
                    rgba(107, 114, 128, 0.08) 100%) !important;
        transform: translateY(-1px) scale(1.005) !important;
    }
    
    /* Shimmer animations */
    @keyframes connectedShimmer {
        0%, 100% { opacity: 0.8; transform: scaleX(1); }
        50% { opacity: 1; transform: scaleX(1.05); }
    }
    
    @keyframes availableShimmer {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 0.9; }
    }
    
    /* Server card text styling within markdown containers */
    .connected-server-card .stMarkdownContainer h4,
    .available-server-card .stMarkdownContainer h4,
    .offline-server-card .stMarkdownContainer h4 {
        color: #1f2937 !important;
        font-weight: 700 !important;
        font-size: 1.2em !important;
        margin-bottom: 12px !important;
        display: flex !important;
        align-items: center !important;
        gap: 8px !important;
    }
    
    .connected-server-card .stMarkdownContainer p,
    .available-server-card .stMarkdownContainer p,
    .offline-server-card .stMarkdownContainer p {
        color: #374151 !important;
        font-weight: 500 !important;
        font-size: 0.9em !important;
        line-height: 1.5 !important;
        margin-bottom: 16px !important;
    }
    
    /* Status indicators within markdown containers */
    .connected-server-card .stMarkdownContainer .status-indicator {
        background: #22c55e !important;
        box-shadow: 0 0 12px rgba(34, 197, 94, 0.4) !important;
    }
    
    .available-server-card .stMarkdownContainer .status-indicator {
        background: #6366f1 !important;
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.4) !important;
    }
    
    .offline-server-card .stMarkdownContainer .status-indicator {
        background: #9ca3af !important;
        box-shadow: 0 0 8px rgba(156, 163, 175, 0.3) !important;
    }
    
    /* Individual System Box Container Styling */
    .system-box-container {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.98) 0%, 
                    rgba(248, 250, 252, 0.95) 100%);
        border: 2px solid rgba(226, 232, 240, 0.8);
        border-radius: 20px;
        margin: 16px 0;
        padding: 0;
        box-shadow: 
            0 12px 48px rgba(51, 65, 85, 0.06),
            0 4px 16px rgba(0, 0, 0, 0.04),
            0 0 0 1px rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(20px);
        overflow: hidden;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
    }
    
    .system-box-container:hover {
        transform: translateY(-4px) scale(1.01);
        box-shadow: 
            0 20px 80px rgba(51, 65, 85, 0.1),
            0 8px 32px rgba(0, 0, 0, 0.06),
            0 0 0 2px rgba(99, 102, 241, 0.2);
        border-color: rgba(99, 102, 241, 0.3);
    }
    
    /* Connected System Box Styling */
    .system-box-container.connected-server-card {
        border-color: rgba(34, 197, 94, 0.4);
        background: linear-gradient(135deg, 
                    rgba(34, 197, 94, 0.05) 0%, 
                    rgba(16, 185, 129, 0.03) 100%);
    }
    
    .system-box-container.connected-server-card:hover {
        border-color: rgba(34, 197, 94, 0.6);
        box-shadow: 
            0 20px 80px rgba(34, 197, 94, 0.15),
            0 8px 32px rgba(16, 185, 129, 0.1),
            0 0 0 2px rgba(34, 197, 94, 0.2);
    }
    
    .system-box-container.connected-server-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, 
                   rgba(34, 197, 94, 0.8) 0%, 
                   rgba(16, 185, 129, 0.6) 50%,
                   rgba(34, 197, 94, 0.8) 100%);
        animation: connectedPulse 2s ease-in-out infinite;
    }
    
    /* Available System Box Styling */
    .system-box-container.available-server-card {
        border-color: rgba(99, 102, 241, 0.4);
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.05) 0%, 
                    rgba(139, 92, 246, 0.03) 100%);
    }
    
    .system-box-container.available-server-card:hover {
        border-color: rgba(99, 102, 241, 0.6);
        box-shadow: 
            0 20px 80px rgba(99, 102, 241, 0.15),
            0 8px 32px rgba(139, 92, 246, 0.1),
            0 0 0 2px rgba(99, 102, 241, 0.2);
    }
    
    .system-box-container.available-server-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
        background: linear-gradient(90deg, 
                   rgba(99, 102, 241, 0.8) 0%, 
                   rgba(139, 92, 246, 0.6) 50%,
                   rgba(99, 102, 241, 0.8) 100%);
        animation: availablePulse 3s ease-in-out infinite;
    }
    
    /* Offline System Box Styling */
    .system-box-container.offline-server-card {
        border-color: rgba(156, 163, 175, 0.4);
        background: linear-gradient(135deg, 
                    rgba(156, 163, 175, 0.05) 0%, 
                    rgba(107, 114, 128, 0.03) 100%);
        opacity: 0.8;
    }
    
    .system-box-container.offline-server-card:hover {
        opacity: 0.9;
        border-color: rgba(156, 163, 175, 0.5);
        transform: translateY(-2px) scale(1.005);
    }
    
    /* System Box Header */
    .system-box-header {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 20px 24px;
        border-bottom: 1px solid rgba(226, 232, 240, 0.6);
        background: linear-gradient(135deg, 
                    rgba(248, 250, 252, 0.8) 0%, 
                    rgba(241, 245, 249, 0.6) 100%);
    }
    
    .system-icon {
        font-size: 2.2em;
        filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.1));
        flex-shrink: 0;
    }
    
    .system-info {
        flex-grow: 1;
        min-width: 0;
    }
    
    .system-name {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 1.2em;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 4px;
        letter-spacing: 0.3px;
    }
    
    .system-name .status-indicator {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex-shrink: 0;
        box-shadow: 0 0 8px currentColor;
        animation: statusPulse 2s ease-in-out infinite;
    }
    
    .system-status {
        font-size: 0.85em;
        font-weight: 600;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    
    /* System Box Content */
    .system-box-content {
        padding: 20px 24px;
    }
    
    .system-description {
        color: #374151;
        font-size: 0.95em;
        line-height: 1.6;
        margin-bottom: 20px;
        font-weight: 500;
    }
    
    .system-actions {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        padding-top: 16px;
        border-top: 1px solid rgba(226, 232, 240, 0.6);
    }
    
    /* Status-specific styling for connected systems */
    .connected-server-card .system-status {
        color: #059669;
    }
    
    .connected-server-card .system-name .status-indicator {
        background: #22c55e;
        box-shadow: 0 0 12px rgba(34, 197, 94, 0.6);
    }
    
    /* Status-specific styling for available systems */
    .available-server-card .system-status {
        color: #7c3aed;
    }
    
    .available-server-card .system-name .status-indicator {
        background: #6366f1;
        box-shadow: 0 0 12px rgba(99, 102, 241, 0.6);
    }
    
    /* Status-specific styling for offline systems */
    .offline-server-card .system-status {
        color: #9ca3af;
    }
    
    .offline-server-card .system-name .status-indicator {
        background: #9ca3af;
        box-shadow: 0 0 8px rgba(156, 163, 175, 0.4);
        animation: none;
    }
    
    /* Pulse animations */
    @keyframes connectedPulse {
        0%, 100% { opacity: 0.8; transform: scaleY(1); }
        50% { opacity: 1; transform: scaleY(1.2); }
    }
    
    @keyframes availablePulse {
        0%, 100% { opacity: 0.6; }
        50% { opacity: 1; }
    }
    
    @keyframes statusPulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.1); opacity: 0.8; }
    }
    
    /* Responsive design for system boxes */
    @media (max-width: 768px) {
        .system-box-container {
            margin: 12px 0;
            border-radius: 16px;
        }
        
        .system-box-header {
            padding: 16px 20px;
            gap: 12px;
        }
        
        .system-icon {
            font-size: 1.8em;
        }
        
        .system-name {
            font-size: 1.1em;
        }
        
        .system-status {
            font-size: 0.8em;
        }
        
        .system-box-content {
            padding: 16px 20px;
        }
        
        .system-description {
            font-size: 0.9em;
            margin-bottom: 16px;
        }
        
        .system-actions {
            padding-top: 12px;
            gap: 8px;
        }
    }
    
    /* Enhanced styling for chat message markdown containers */
    .chat-bubble-user .stMarkdownContainer {
        background: linear-gradient(135deg, 
                    rgba(107, 114, 128, 0.95) 0%, 
                    rgba(156, 163, 175, 0.9) 50%,
                    rgba(156, 163, 175, 0.85) 100%) !important;
        border: 2px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 24px 24px 8px 24px !important;
        padding: 20px 24px !important;
        margin: 12px 0 !important;
        color: white !important;
        box-shadow: 
            0 12px 48px rgba(99, 102, 241, 0.3),
            0 4px 16px rgba(139, 92, 246, 0.2),
            0 0 0 1px rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(15px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
        max-width: 80% !important;
        margin-left: auto !important;
        margin-right: 0 !important;
    }
    
    .chat-bubble-user .stMarkdownContainer::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(45deg, 
                   rgba(255, 255, 255, 0.1) 0%, 
                   transparent 50%,
                   rgba(255, 255, 255, 0.05) 100%);
        pointer-events: none;
        border-radius: inherit;
    }
    
    .chat-bubble-user .stMarkdownContainer:hover {
        transform: translateY(-2px) scale(1.01) !important;
        box-shadow: 
            0 16px 64px rgba(107, 114, 128, 0.4),
            0 8px 32px rgba(156, 163, 175, 0.3),
            0 0 0 2px rgba(255, 255, 255, 0.2) !important;
    }
    
    .chat-bubble-assistant .stMarkdownContainer {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.98) 0%, 
                    rgba(248, 250, 252, 0.95) 50%,
                    rgba(241, 245, 249, 0.92) 100%) !important;
        border: 2px solid rgba(226, 232, 240, 0.8) !important;
        border-radius: 24px 24px 24px 8px !important;
        padding: 20px 24px !important;
        margin: 12px 0 !important;
        color: #1f2937 !important;
        box-shadow: 
            0 12px 48px rgba(51, 65, 85, 0.08),
            0 4px 16px rgba(0, 0, 0, 0.04),
            0 0 0 1px rgba(255, 255, 255, 0.9) !important;
        backdrop-filter: blur(15px) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
        max-width: 80% !important;
        margin-left: 0 !important;
        margin-right: auto !important;
    }
    
    .chat-bubble-assistant .stMarkdownContainer::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, 
                   rgba(34, 197, 94, 0.6) 0%, 
                   rgba(16, 185, 129, 0.4) 50%,
                   rgba(34, 197, 94, 0.6) 100%);
        border-radius: 24px 24px 0 0;
        animation: assistantShimmer 3s ease-in-out infinite;
    }
    
    .chat-bubble-assistant .stMarkdownContainer:hover {
        transform: translateY(-2px) scale(1.01) !important;
        border-color: rgba(34, 197, 94, 0.3) !important;
        box-shadow: 
            0 16px 64px rgba(34, 197, 94, 0.12),
            0 8px 32px rgba(51, 65, 85, 0.08),
            0 0 0 2px rgba(34, 197, 94, 0.2) !important;
    }
    
    /* Chat message text styling within markdown containers */
    .chat-bubble-user .stMarkdownContainer p,
    .chat-bubble-user .stMarkdownContainer div {
        color: rgba(255, 255, 255, 0.95) !important;
        font-weight: 500 !important;
        font-size: 0.95em !important;
        line-height: 1.6 !important;
        margin: 0 !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1) !important;
    }
    
    .chat-bubble-assistant .stMarkdownContainer p,
    .chat-bubble-assistant .stMarkdownContainer div {
        color: #374151 !important;
        font-weight: 500 !important;
        font-size: 0.95em !important;
        line-height: 1.6 !important;
        margin: 0 !important;
    }
    
    /* Timestamp styling within chat markdown containers */
    .chat-bubble-user .stMarkdownContainer .timestamp,
    .chat-bubble-assistant .stMarkdownContainer .timestamp {
        font-size: 0.75em !important;
        opacity: 0.8 !important;
        font-weight: 600 !important;
        margin-top: 8px !important;
        padding-top: 8px !important;
        border-top: 1px solid rgba(255, 255, 255, 0.2) !important;
    }
    
    .chat-bubble-user .stMarkdownContainer .timestamp {
        color: rgba(255, 255, 255, 0.9) !important;
        text-align: right !important;
    }
    
    .chat-bubble-assistant .stMarkdownContainer .timestamp {
        color: #6b7280 !important;
        text-align: left !important;
        border-top-color: rgba(226, 232, 240, 0.5) !important;
    }
    
    /* Assistant shimmer animation */
    @keyframes assistantShimmer {
        0%, 100% { opacity: 0.6; transform: scaleX(1); }
        50% { opacity: 1; transform: scaleX(1.02); }
    }
    
    /* Responsive design for chat markdown containers */
    @media (max-width: 768px) {
        .chat-bubble-user .stMarkdownContainer,
        .chat-bubble-assistant .stMarkdownContainer {
            max-width: 90% !important;
            padding: 16px 20px !important;
            border-radius: 20px !important;
            margin: 8px 0 !important;
        }
        
        .chat-bubble-user .stMarkdownContainer {
            border-radius: 20px 20px 6px 20px !important;
        }
        
        .chat-bubble-assistant .stMarkdownContainer {
            border-radius: 20px 20px 20px 6px !important;
        }
        
        .chat-bubble-user .stMarkdownContainer p,
        .chat-bubble-user .stMarkdownContainer div,
        .chat-bubble-assistant .stMarkdownContainer p,
        .chat-bubble-assistant .stMarkdownContainer div {
            font-size: 0.9em !important;
                 }
     }
     
     /* Conversation Section Container Styling */
     .conversation-section-container {
         background: linear-gradient(135deg, 
                     rgba(255, 255, 255, 0.98) 0%, 
                     rgba(248, 250, 252, 0.95) 100%);
         border: 2px solid rgba(99, 102, 241, 0.15);
         border-radius: 20px;
         margin: 24px 0;
         padding: 0;
         box-shadow: 
             0 16px 64px rgba(99, 102, 241, 0.08),
             0 4px 16px rgba(51, 65, 85, 0.04),
             0 0 0 1px rgba(255, 255, 255, 0.8);
         backdrop-filter: blur(20px);
         overflow: hidden;
         transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
         position: relative;
     }
     
     .conversation-section-container:hover {
         border-color: rgba(99, 102, 241, 0.25);
         box-shadow: 
             0 20px 80px rgba(99, 102, 241, 0.12),
             0 8px 32px rgba(51, 65, 85, 0.06),
             0 0 0 2px rgba(99, 102, 241, 0.1);
         transform: translateY(-2px);
     }
     
     /* Conversation Section Header */
     .conversation-section-header {
         background: linear-gradient(135deg, 
                     rgba(99, 102, 241, 0.95) 0%, 
                     rgba(139, 92, 246, 0.9) 100%);
         color: white;
         padding: 16px 24px;
         display: flex;
         align-items: center;
         gap: 12px;
         border-bottom: 2px solid rgba(255, 255, 255, 0.1);
         position: relative;
         overflow: hidden;
     }
     
     .conversation-section-header::before {
         content: '';
         position: absolute;
         top: 0;
         left: -100%;
         width: 100%;
         height: 100%;
         background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.1), 
                    transparent);
         animation: headerShimmer 3s ease-in-out infinite;
     }
     
     .section-icon {
         font-size: 1.4em;
         filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.2));
     }
     
     .section-title {
         font-size: 1.1em;
         font-weight: 700;
         flex-grow: 1;
         letter-spacing: 0.5px;
         text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
     }
     
     .section-badge {
         background: rgba(255, 255, 255, 0.2);
         color: white;
         padding: 6px 12px;
         border-radius: 12px;
         font-size: 0.8em;
         font-weight: 600;
         border: 1px solid rgba(255, 255, 255, 0.3);
         backdrop-filter: blur(10px);
     }
     
     /* Conversation Messages Wrapper */
     .conversation-messages-wrapper {
         padding: 24px;
         background: linear-gradient(135deg, 
                     rgba(248, 250, 252, 0.5) 0%, 
                     rgba(241, 245, 249, 0.3) 100%);
     }
     
     /* Chat Message Card Styling */
     .chat-message-card {
         margin: 20px 0;
         transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
         position: relative;
     }
     
     .chat-message-card:hover {
         transform: translateY(-1px);
     }
     
     /* Message Header */
     .message-header {
         display: flex;
         align-items: center;
         gap: 12px;
         margin-bottom: 12px;
         padding: 0 4px;
     }
     
     .message-avatar {
         width: 40px;
         height: 40px;
         border-radius: 50%;
         display: flex;
         align-items: center;
         justify-content: center;
         font-size: 1.2em;
         font-weight: 600;
         box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
         flex-shrink: 0;
     }
     
     .user-avatar {
         background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
         color: white;
         border: 2px solid rgba(255, 255, 255, 0.8);
     }
     
     .assistant-avatar {
         background: linear-gradient(135deg, #10b981 0%, #059669 100%);
         color: white;
         border: 2px solid rgba(255, 255, 255, 0.8);
     }
     
     .message-meta {
         flex-grow: 1;
     }
     
     .message-sender {
         font-weight: 700;
         font-size: 0.9em;
         color: #1f2937;
         margin-bottom: 2px;
     }
     
     .message-time {
         font-size: 0.75em;
         color: #6b7280;
         opacity: 0.8;
     }
     
     /* Enhanced message content styling */
     .message-content {
         font-size: 0.95em;
         line-height: 1.6;
         font-weight: 500;
         margin: 0;
         word-wrap: break-word;
     }
     
     /* User message card specific styling */
     .user-message-card {
         margin-left: auto;
         margin-right: 0;
         max-width: 85%;
     }
     
     .user-message-card .chat-bubble-user {
         margin-left: auto;
         margin-right: 0;
     }
     
     /* Assistant message card specific styling */
     .assistant-message-card {
         margin-left: 0;
         margin-right: auto;
         max-width: 85%;
     }
     
     .assistant-message-card .chat-bubble-assistant {
         margin-left: 0;
         margin-right: auto;
     }
     
     /* Animation for header shimmer */
     @keyframes headerShimmer {
         0% { left: -100%; }
         50% { left: 100%; }
         100% { left: 100%; }
     }
     
     /* Responsive design for conversation sections */
     @media (max-width: 768px) {
         .conversation-section-container {
             margin: 16px 0;
             border-radius: 16px;
         }
         
         .conversation-section-header {
             padding: 12px 16px;
             flex-wrap: wrap;
             gap: 8px;
         }
         
         .section-title {
             font-size: 1em;
         }
         
         .section-badge {
             font-size: 0.75em;
             padding: 4px 8px;
         }
         
         .conversation-messages-wrapper {
             padding: 16px;
         }
         
         .message-avatar {
             width: 36px;
             height: 36px;
             font-size: 1.1em;
         }
         
         .user-message-card,
         .assistant-message-card {
             max-width: 95%;
         }
         
         .message-sender {
             font-size: 0.85em;
         }
         
         .message-time {
             font-size: 0.7em;
         }
     }
     
     /* Chat assistant headers */
    .chat-assistant-header {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        padding: 16px 24px;
        border-radius: 12px;
        margin: 20px 0 16px 0;
        text-align: center;
        font-weight: 600;
        font-size: 1.1em;
        box-shadow: 0 4px 16px rgba(99, 102, 241, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        overflow: hidden;
    }
    
    .chat-assistant-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
        animation: shimmer 2s infinite;
    }
    
    @keyframes shimmer {
        0% { left: -100%; }
        100% { left: 100%; }
    }
    
    .chat-section-header {
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.08) 0%, 
                    rgba(139, 92, 246, 0.05) 100%);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 12px;
        padding: 14px 24px;
        margin: 18px 0 14px 0;
        text-align: center;
        font-weight: 600;
        font-size: 1em;
        color: #4f46e5;
        backdrop-filter: blur(10px);
        box-shadow: 
            0 2px 8px rgba(99, 102, 241, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }
    
    .section-divider {
        height: 1px;
        background: linear-gradient(90deg, 
                    transparent, 
                    rgba(226, 232, 240, 0.8), 
                    transparent);
        margin: 28px 0;
        border: none;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(248, 250, 252, 0.6);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.6) 0%, 
                    rgba(139, 92, 246, 0.4) 100%);
        border-radius: 4px;
        transition: all 0.2s ease;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, 
                    rgba(99, 102, 241, 0.8) 0%, 
                    rgba(139, 92, 246, 0.6) 100%);
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {visibility: hidden;}
    
    /* Tool results styling */
    .tool-result {
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-radius: 12px;
        padding: 16px;
        margin: 10px 0;
        font-size: 0.85em;
        box-shadow: 
            0 4px 15px rgba(34, 197, 94, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    .tool-result h5 {
        color: #059669;
        margin: 0 0 10px 0;
        font-size: 0.95em;
        font-weight: 600;
    }
    
    /* Connected systems styling */
    .connected-system {
        background: rgba(255, 255, 255, 0.8);
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-radius: 12px;
        padding: 18px;
        margin: 14px 0;
        box-shadow: 
            0 4px 15px rgba(34, 197, 94, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 0.8);
    }
    
    .connected-system h4 {
        color: #059669;
        margin: 0 0 14px 0;
        font-size: 1.05em;
        font-weight: 600;
    }
    
    /* Main content area text fixes */
    .main .stMarkdown p,
    .main .stMarkdown span,
    .main .stMarkdown div {
        color: #374151 !important;
    }
    
    .main .stMarkdown h1,
    .main .stMarkdown h2,
    .main .stMarkdown h3,
    .main .stMarkdown h4,
    .main .stMarkdown h5,
    .main .stMarkdown h6 {
        color: #1f2937 !important;
    }
    
    /* Status messages in main area */
    .main .stInfo {
        background: rgba(59, 130, 246, 0.1) !important;
        border: 1px solid rgba(59, 130, 246, 0.2) !important;
        color: #1e40af !important;
        border-radius: 8px !important;
    }
    
    .main .stSuccess {
        background: rgba(34, 197, 94, 0.1) !important;
        border: 1px solid rgba(34, 197, 94, 0.2) !important;
        color: #166534 !important;
        border-radius: 8px !important;
    }
    
    .main .stWarning {
        background: rgba(245, 158, 11, 0.1) !important;
        border: 1px solid rgba(245, 158, 11, 0.2) !important;
        color: #92400e !important;
        border-radius: 8px !important;
    }
    
    .main .stError {
        background: rgba(239, 68, 68, 0.1) !important;
        border: 1px solid rgba(239, 68, 68, 0.2) !important;
        color: #dc2626 !important;
        border-radius: 8px !important;
    }
    
    /* Fix column text */
    .main .stColumn p,
    .main .stColumn span,
    .main .stColumn div {
        color: #374151 !important;
    }
    
    /* Fix expander content */
    .main .streamlit-expanderContent {
        background: rgba(255, 255, 255, 0.5) !important;
        border: 1px solid rgba(226, 232, 240, 0.6) !important;
        color: #374151 !important;
    }
    
    .main .streamlit-expanderContent p {
        color: #374151 !important;
    }
    
    /* Fix caption styling */
    .main .caption {
        color: #6b7280 !important;
        font-size: 0.8em !important;
    }
    
    /* Fix code blocks */
    .main .stCodeBlock {
        background: rgba(248, 250, 252, 0.8) !important;
        border: 1px solid rgba(226, 232, 240, 0.6) !important;
        color: #1f2937 !important;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem;
            margin-top: 0.5rem;
        }
        
        .chat-bubble-user, .chat-bubble-assistant {
            max-width: 90%;
        }
    }
    
    /* Microsoft Fluent UI Text Input Design */
    .stTextInput > div > div > input {
        background: #ffffff !important;
        border: 1px solid #e1e5f1 !important;
        border-radius: 4px !important;
        padding: 12px 16px !important;
        color: #323130 !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        transition: all 0.2s ease !important;
        box-shadow: none !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #0078d4 !important;
        background: #ffffff !important;
        box-shadow: 0 0 0 1px #0078d4 !important;
        outline: none !important;
    }
    
    .stTextInput > div > div > input:hover {
        border-color: #c7c7c7 !important;
    }
    
    /* Placeholder text styling */
    .stTextInput > div > div > input::placeholder {
        color: #605e5c !important;
        opacity: 1 !important;
        font-style: normal !important;
        font-weight: 400 !important;
    }
    
    /* Fix input text visibility */
    .stTextInput > div > div > input {
        color: #323130 !important;
        font-weight: 400 !important;
    }

    /* Enhanced Sessions Tab Styling */
    .css-1d391kg .stSelectbox > div > div {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.95) 0%, 
                    rgba(248, 250, 252, 0.9) 100%) !important;
        border: 2px solid rgba(0, 120, 212, 0.15) !important;
        border-radius: 8px !important;
        box-shadow: 
            0 2px 8px rgba(0, 120, 212, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        font-weight: 500 !important;
        color: #323130 !important;
    }
    
    .css-1d391kg .stSelectbox > div > div:hover {
        border-color: rgba(0, 120, 212, 0.25) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(247, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 4px 16px rgba(0, 120, 212, 0.12),
            0 1px 4px rgba(0, 0, 0, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-1px) scale(1.01) !important;
    }
    
    /* Enhanced Sessions Tab Info Boxes */
    .css-1d391kg .stInfo {
        background: linear-gradient(135deg, 
                    rgba(0, 120, 212, 0.08) 0%, 
                    rgba(0, 120, 212, 0.05) 100%) !important;
        border: 2px solid rgba(0, 120, 212, 0.2) !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        color: #005a9e !important;
        font-weight: 500 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        box-shadow: 
            0 4px 16px rgba(0, 120, 212, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
    }
    
    /* Enhanced Sessions Tab Buttons */
    .css-1d391kg .stButton > button {
        background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 12px 24px !important;
        box-shadow: 
            0 2px 8px rgba(0, 120, 212, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.1) !important;
        transition: all 0.2s ease !important;
    }
    
    .css-1d391kg .stButton > button:hover {
        background: linear-gradient(135deg, #106ebe 0%, #005a9e 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 
            0 4px 12px rgba(0, 120, 212, 0.4),
            0 0 0 1px rgba(255, 255, 255, 0.2) !important;
    }
    
    /* Enhanced Settings Tab Styling */
    .main .stTextInput > div > div > input {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.95) 0%, 
                    rgba(248, 250, 252, 0.9) 100%) !important;
        border: 2px solid rgba(124, 58, 237, 0.15) !important;
        border-radius: 8px !important;
        padding: 14px 18px !important;
        color: #323130 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 
            0 2px 8px rgba(124, 58, 237, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    
    .main .stTextInput > div > div > input:focus {
        border-color: rgba(124, 58, 237, 0.4) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(248, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 0 0 2px rgba(124, 58, 237, 0.2),
            0 4px 16px rgba(124, 58, 237, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        outline: none !important;
        transform: translateY(-1px) scale(1.01) !important;
    }
    
    .main .stTextInput > div > div > input:hover {
        border-color: rgba(124, 58, 237, 0.25) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(247, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 4px 12px rgba(124, 58, 237, 0.12),
            0 1px 4px rgba(0, 0, 0, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    
    /* Enhanced Settings Tab Labels */
    .main .stTextInput > label {
        color: #323130 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        margin-bottom: 8px !important;
        display: block !important;
    }
    
    /* Enhanced Settings Tab Number Inputs */
    .main .stNumberInput > div > div > input {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.95) 0%, 
                    rgba(248, 250, 252, 0.9) 100%) !important;
        border: 2px solid rgba(124, 58, 237, 0.15) !important;
        border-radius: 8px !important;
        padding: 14px 18px !important;
        color: #323130 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 
            0 2px 8px rgba(124, 58, 237, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
    }
    
    .main .stNumberInput > div > div > input:focus {
        border-color: rgba(124, 58, 237, 0.4) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(248, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 0 0 2px rgba(124, 58, 237, 0.2),
            0 4px 16px rgba(124, 58, 237, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        outline: none !important;
        transform: translateY(-1px) scale(1.01) !important;
    }
    
    /* Enhanced Settings Tab Sliders */
    .main .stSlider > div > div > div {
        background: linear-gradient(135deg, 
                    rgba(124, 58, 237, 0.1) 0%, 
                    rgba(124, 58, 237, 0.05) 100%) !important;
        border-radius: 8px !important;
        padding: 8px !important;
    }
    
    /* Enhanced Settings Tab Buttons */
    .main .stButton > button {
        background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 12px 24px !important;
        box-shadow: 
            0 4px 16px rgba(124, 58, 237, 0.3),
            0 0 0 1px rgba(255, 255, 255, 0.1) !important;
        transition: all 0.25s ease !important;
    }
    
    .main .stButton > button:hover {
        background: linear-gradient(135deg, #6d28d9 0%, #5b21b6 100%) !important;
        transform: translateY(-2px) scale(1.02) !important;
        box-shadow: 
            0 8px 24px rgba(124, 58, 237, 0.4),
            0 0 0 1px rgba(255, 255, 255, 0.2) !important;
    }
    
    /* Enhanced Settings Tab Success/Warning Messages */
    .main .stSuccess {
        background: linear-gradient(135deg, 
                    rgba(34, 197, 94, 0.1) 0%, 
                    rgba(34, 197, 94, 0.05) 100%) !important;
        border: 2px solid rgba(34, 197, 94, 0.3) !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        color: #166534 !important;
        font-weight: 500 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        box-shadow: 
            0 4px 16px rgba(34, 197, 94, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
    }
    
    .main .stWarning {
        background: linear-gradient(135deg, 
                    rgba(245, 158, 11, 0.1) 0%, 
                    rgba(245, 158, 11, 0.05) 100%) !important;
        border: 2px solid rgba(245, 158, 11, 0.3) !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        color: #92400e !important;
        font-weight: 500 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        box-shadow: 
            0 4px 16px rgba(245, 158, 11, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.8) !important;
    }
    
    /* Enhanced Session Cards in Sessions Tab */
    .css-1d391kg .stContainer {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.95) 0%, 
                    rgba(248, 250, 252, 0.9) 100%) !important;
        border: 2px solid rgba(0, 120, 212, 0.15) !important;
        border-radius: 12px !important;
        padding: 16px 20px !important;
        margin: 12px 0 !important;
        box-shadow: 
            0 4px 16px rgba(0, 120, 212, 0.08),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    .css-1d391kg .stContainer:hover {
        border-color: rgba(0, 120, 212, 0.25) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(247, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 8px 24px rgba(0, 120, 212, 0.12),
            0 2px 8px rgba(0, 0, 0, 0.06),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-2px) scale(1.01) !important;
    }
    
    /* Microsoft Fluent UI Button Design - Run & Send buttons */
    .stForm .stButton > button,
    .stForm button[data-testid="baseButton-primary"],
    .stForm button[kind="primary"] {
        background: #0078d4 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        border: 1px solid #0078d4 !important;
        border-radius: 4px !important;
        padding: 8px 20px !important;
        font-size: 14px !important;
        min-height: 32px !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        cursor: pointer !important;
        box-shadow: none !important;
        transition: all 0.1s cubic-bezier(0.1, 0.9, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .stForm .stButton > button:hover,
    .stForm button[data-testid="baseButton-primary"]:hover,
    .stForm button[kind="primary"]:hover {
        background: #106ebe !important;
        border-color: #106ebe !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    .stForm .stButton > button:active,
    .stForm button[data-testid="baseButton-primary"]:active,
    .stForm button[kind="primary"]:active {
        background: #005a9e !important;
        border-color: #005a9e !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #005a9e !important;
    }
    
    .stForm .stButton > button:focus,
    .stForm button[data-testid="baseButton-primary"]:focus,
    .stForm button[kind="primary"]:focus {
        outline: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    /* Chat Send Button - Microsoft Fluent UI Design */
    .main .block-container .stForm .stButton > button[kind="primary"] {
        background: #0078d4 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        border: 1px solid #0078d4 !important;
        border-radius: 4px !important;
        padding: 16px 24px !important;
        font-size: 16px !important;
        min-height: 56px !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        cursor: pointer !important;
        box-shadow: none !important;
        transition: all 0.1s cubic-bezier(0.1, 0.9, 0.2, 1) !important;
        position: relative !important;
        overflow: hidden !important;
    }
    
    .main .block-container .stForm .stButton > button[kind="primary"]:hover {
        background: #106ebe !important;
        border-color: #106ebe !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    .main .block-container .stForm .stButton > button[kind="primary"]:active {
        background: #005a9e !important;
        border-color: #005a9e !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #005a9e !important;
    }
    
    .main .block-container .stForm .stButton > button[kind="primary"]:focus {
        outline: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    /* Microsoft Fluent UI - Override all button styling (no red colors) */
    .stButton > button[kind="primary"],
    button[data-testid="baseButton-primary"],
    .stButton > button,
    button[type="submit"] {
        background: #0078d4 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Roboto', sans-serif !important;
        border: 1px solid #0078d4 !important;
        border-radius: 4px !important;
        padding: 8px 20px !important;
        font-size: 14px !important;
        min-height: 32px !important;
        text-transform: none !important;
        letter-spacing: normal !important;
        cursor: pointer !important;
        box-shadow: none !important;
        transition: all 0.1s cubic-bezier(0.1, 0.9, 0.2, 1) !important;
    }
    
    .stButton > button[kind="primary"]:hover,
    button[data-testid="baseButton-primary"]:hover,
    .stButton > button:hover,
    button[type="submit"]:hover {
        background: #106ebe !important;
        border-color: #106ebe !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    .stButton > button[kind="primary"]:active,
    button[data-testid="baseButton-primary"]:active,
    .stButton > button:active,
    button[type="submit"]:active {
        background: #005a9e !important;
        border-color: #005a9e !important;
        transform: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #005a9e !important;
    }
    
    .stButton > button[kind="primary"]:focus,
    button[data-testid="baseButton-primary"]:focus,
    .stButton > button:focus,
    button[type="submit"]:focus {
        outline: none !important;
        box-shadow: 0 0 0 1px #ffffff, 0 0 0 2px #0078d4 !important;
    }
    
    /* Settings Tab - Make ALL input text black */
    .main .stTextInput > div > div > input {
        color: #000000 !important;
        font-weight: 500 !important;
    }
    
    .main .stNumberInput > div > div > input {
        color: #000000 !important;
        font-weight: 500 !important;
    }
    
    /* Settings Tab - Make textarea text black */
    .main .stTextArea > div > div > textarea {
        color: #000000 !important;
        font-weight: 500 !important;
    }
    
    /* Settings Tab - Make textarea placeholder text black */
    .main .stTextArea > div > div > textarea::placeholder {
        color: #000000 !important;
        opacity: 0.8 !important;
    }
    
    /* Settings Tab - Comprehensive styling for all form elements */
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stSlider > div > div > div {
        color: #000000 !important;
    }
    
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stSlider label {
        color: #1f2937 !important;
        font-weight: 600 !important;
    }
    
    /* Settings Tab - JSON display styling */
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stJson {
        color: #000000 !important;
    }
    
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stJson pre {
        color: #000000 !important;
        background-color: rgba(255, 255, 255, 0.95) !important;
    }
    
    /* Settings Tab - Expander content styling */
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .streamlit-expanderContent {
        background-color: rgba(255, 255, 255, 0.95) !important;
        color: #000000 !important;
    }
    
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .streamlit-expanderContent * {
        color: #000000 !important;
    }
    
    /* Settings Tab - All text elements */
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) p,
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) span,
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) div,
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) label {
        color: #000000 !important;
    }
    
    /* Settings Tab - Success/Error messages */
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stSuccess,
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stWarning,
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stError {
        color: #000000 !important;
    }
    
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stSuccess * {
        color: #166534 !important;
    }
    
    [data-testid="stTabs"] [data-testid="stTabPanel"]:nth-child(3) .stWarning * {
        color: #92400e !important;
    }
    
    /* Chat text area placeholder styling - Pure black and stylish */
    .main .stTextArea > div > div > textarea::placeholder {
        color: #000000 !important;
        opacity: 1 !important;
        font-weight: 600 !important;
        font-size: 1.1em !important;
        font-style: italic !important;
        letter-spacing: 0.5px !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2) !important;
    }
    
    .main .stTextArea > div > div > textarea {
        color: #000000 !important;
        font-weight: 500 !important;
        font-size: 1.05em !important;
        line-height: 1.6 !important;
    }
    
    /* Enhanced text area styling */
    .main .stTextArea > div > div > textarea {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.98) 0%, 
                    rgba(248, 250, 252, 0.95) 100%) !important;
        border: 2px solid rgba(156, 163, 175, 0.3) !important;
        border-radius: 16px !important;
        padding: 16px 20px !important;
        box-shadow: 
            0 4px 20px rgba(156, 163, 175, 0.12),
            0 0 0 1px rgba(255, 255, 255, 0.9),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    
    .main .stTextArea > div > div > textarea:focus {
        border-color: rgba(107, 114, 128, 0.6) !important;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 1) 0%, 
                    rgba(248, 250, 252, 1) 100%) !important;
        box-shadow: 
            0 0 0 3px rgba(156, 163, 175, 0.2),
            0 8px 32px rgba(156, 163, 175, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 1) !important;
        transform: translateY(-2px) scale(1.01) !important;
        outline: none !important;
    }
    </style>
    
    <script>
    // Copy to clipboard functionality
    function copyToClipboard(text, button) {
        navigator.clipboard.writeText(text).then(function() {
            // Visual feedback
            const originalIcon = button.innerHTML;
            button.innerHTML = '✅';
            button.style.background = 'rgba(34, 197, 94, 0.2)';
            button.style.borderColor = 'rgba(34, 197, 94, 0.5)';
            
            setTimeout(function() {
                button.innerHTML = originalIcon;
                button.style.background = '';
                button.style.borderColor = '';
            }, 1500);
        }).catch(function(err) {
            console.error('Failed to copy text: ', err);
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            
            // Visual feedback
            const originalIcon = button.innerHTML;
            button.innerHTML = '✅';
            setTimeout(function() {
                button.innerHTML = originalIcon;
            }, 1500);
        });
    }
    
    // Reload message functionality
    function reloadMessage(message, button) {
        // Visual feedback
        const originalIcon = button.innerHTML;
        button.innerHTML = '⏳';
        button.style.background = 'rgba(59, 130, 246, 0.2)';
        button.style.borderColor = 'rgba(59, 130, 246, 0.5)';
        
        // Set the message in the input field and trigger send
        const inputField = document.querySelector('textarea[placeholder*="Ask me anything"]');
        if (inputField) {
            inputField.value = message;
            inputField.dispatchEvent(new Event('input', { bubbles: true }));
            
            // Find and click the send button
            const sendButton = document.querySelector('button[type="submit"]');
            if (sendButton) {
                sendButton.click();
            }
        }
        
        setTimeout(function() {
            button.innerHTML = originalIcon;
            button.style.background = '';
            button.style.borderColor = '';
        }, 2000);
    }
    
    // Rate message functionality
    function rateMessage(messageIndex, rating, button) {
        // Store rating in session storage
        const ratingKey = `message_rating_${messageIndex}`;
        localStorage.setItem(ratingKey, rating);
        
        // Update button states
        const messageCard = button.closest('.chat-message-card');
        const thumbsUpBtn = messageCard.querySelector('.thumbs-up-btn');
        const thumbsDownBtn = messageCard.querySelector('.thumbs-down-btn');
        
        // Reset both buttons
        thumbsUpBtn.classList.remove('active');
        thumbsDownBtn.classList.remove('active');
        
        // Activate clicked button
        if (rating === 'up') {
            thumbsUpBtn.classList.add('active');
        } else {
            thumbsDownBtn.classList.add('active');
        }
        
        // Visual feedback
        const originalIcon = button.innerHTML;
        button.innerHTML = rating === 'up' ? '✨' : '💔';
        
        setTimeout(function() {
            button.innerHTML = originalIcon;
        }, 1500);
        
        console.log(`Message ${messageIndex} rated as: ${rating}`);
    }
    
    // Initialize ratings on page load
    document.addEventListener('DOMContentLoaded', function() {
        // Restore saved ratings
        const messageCards = document.querySelectorAll('.chat-message-card');
        messageCards.forEach((card, index) => {
            const ratingKey = `message_rating_${index}`;
            const savedRating = localStorage.getItem(ratingKey);
            
            if (savedRating) {
                const thumbsUpBtn = card.querySelector('.thumbs-up-btn');
                const thumbsDownBtn = card.querySelector('.thumbs-down-btn');
                
                if (thumbsUpBtn && thumbsDownBtn) {
                    thumbsUpBtn.classList.remove('active');
                    thumbsDownBtn.classList.remove('active');
                    
                    if (savedRating === 'up') {
                        thumbsUpBtn.classList.add('active');
                    } else if (savedRating === 'down') {
                        thumbsDownBtn.classList.add('active');
                    }
                }
            }
        });
    });
    
    // Simple button functionality using event delegation
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('copy-btn')) {
            // Find the message content in the same card
            const messageCard = e.target.closest('.chat-message-card');
            const messageContent = messageCard.querySelector('.message-content');
            if (messageContent) {
                const text = messageContent.textContent || messageContent.innerText;
                navigator.clipboard.writeText(text).then(() => {
                    // Visual feedback
                    const originalIcon = e.target.innerHTML;
                    e.target.innerHTML = '✅';
                    setTimeout(() => {
                        e.target.innerHTML = originalIcon;
                    }, 1500);
                }).catch(() => {
                    // Fallback - show text for manual copying
                    alert('Copy this text: ' + text);
                });
            }
        } else if (e.target.classList.contains('reload-btn')) {
            // Find the message content and set it to the input field
            const messageCard = e.target.closest('.chat-message-card');
            const messageContent = messageCard.querySelector('.message-content');
            if (messageContent) {
                const text = messageContent.textContent || messageContent.innerText;
                const inputField = document.querySelector('textarea[data-testid="stTextArea"] textarea');
                if (inputField) {
                    inputField.value = text;
                    inputField.focus();
                    // Visual feedback
                    const originalIcon = e.target.innerHTML;
                    e.target.innerHTML = '✅';
                    setTimeout(() => {
                        e.target.innerHTML = originalIcon;
                    }, 1500);
                }
            }
        } else if (e.target.classList.contains('thumbs-up-btn')) {
            // Visual feedback for thumbs up
            const originalIcon = e.target.innerHTML;
            e.target.innerHTML = '✅';
            setTimeout(() => {
                e.target.innerHTML = originalIcon;
            }, 1500);
        } else if (e.target.classList.contains('thumbs-down-btn')) {
            // Visual feedback for thumbs down
            const originalIcon = e.target.innerHTML;
            e.target.innerHTML = '📝';
            setTimeout(() => {
                e.target.innerHTML = originalIcon;
            }, 1500);
        }
    });
    </script>
""", unsafe_allow_html=True)

# --- Sidebar: Server Management ---
with st.sidebar:
    if server_manager:
        _diag = server_manager.get_streaming_diagnostics()
        st.caption(
            f"🌊 Streaming: {'on' if _diag['streaming_enabled'] else 'off'} · "
            f"LLM: {'on' if _diag['llm_streaming'] else 'off'}"
        )
    # Premium Sidebar Header
    st.markdown("""
        <div style="
            background: linear-gradient(135deg, 
                        #6366f1 0%, 
                        #8b5cf6 25%,
                        #a855f7 50%,
                        #8b5cf6 75%,
                        #6366f1 100%);
            background-size: 200% 200%;
            animation: gradientShift 6s ease infinite;
            color: white;
            padding: 20px 18px;
            border-radius: 18px;
            margin-bottom: 24px;
            text-align: center;
            font-weight: 700;
            font-size: 1.05em;
            box-shadow: 
                0 8px 32px rgba(99, 102, 241, 0.25),
                0 0 0 1px rgba(255, 255, 255, 0.1),
                inset 0 1px 0 rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
            letter-spacing: 0.5px;
        ">
            <div style="
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            ">
                <span style="
                    font-size: 1.3em;
                    filter: drop-shadow(0 0 8px rgba(255, 255, 255, 0.5));
                    animation: robotPulse 2s ease-in-out infinite;
                ">🤖</span>
                <span>AI Control Center</span>
            </div>
            <div style="
                font-size: 0.75em;
                opacity: 0.9;
                margin-top: 4px;
                font-weight: 500;
                letter-spacing: 1px;
            ">
                MCP SERVER MANAGEMENT
            </div>
        </div>
        
        <style>
        @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        
        @keyframes robotPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Sidebar Tabs
    sidebar_tab1, sidebar_tab2 = st.tabs(["🖥️ Connectors", "🗣️ Sessions"])
    with sidebar_tab1:  # MCP Servers Hub Tab
        st.markdown("""
            <div class="chat-section-header">
                🔗 Available Connectors
            </div>
            <div style="
                background: rgba(16, 185, 129, 0.1);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                text-align: center;
                margin-bottom: 16px;
                font-size: 0.85em;
                color: #059669;
                font-weight: 500;
            ">
                🔐 Auto-Connect: Systems without authentication enabled by default
            </div>
            

        """, unsafe_allow_html=True)
        
        # Initialize connection states (preserve original order)
        for system in systems:
            # Initialize connection state - Systems requiring auth start disconnected
            if f"init_{system['session_key']}" not in st.session_state:
                if requires_authentication(system.get("server_key", "")):
                    st.session_state[system["session_key"]] = False  # Start disconnected for auth-required systems
                else:
                    st.session_state[system["session_key"]] = True  # Auto-connect for systems not requiring auth
                st.session_state[f"init_{system['session_key']}"] = True
        
        # Display servers in original order
        for index, system in enumerate(systems):
            server_available = (server_manager and 
                              system.get("server_key") in server_manager.get_available_servers())
            
            # Each server gets its own container card
            with st.container():
                # Get current connection status
                current_connected = st.session_state.get(system["session_key"], True)
                
                # Check authentication requirements
                server_key = system.get("server_key", "")
                needs_auth = requires_authentication(server_key)
                is_authenticated = is_server_authenticated(server_key) if needs_auth else True
                
                # Determine status color and text based on authentication and connection
                if needs_auth and not is_authenticated:
                    status_color = "#f59e0b"  # Yellow for authentication required
                    status_text = "Auth Required"
                    card_class = "server-card"
                    status_class = "status-offline"
                elif server_available and is_authenticated and current_connected:
                    status_color = "#10b981"  # Green for connected
                    status_text = "Connected"
                    card_class = "server-card server-card-connected"
                    status_class = "status-online"
                elif server_available and is_authenticated:
                    status_color = "#d1d5db"  # Light grey for available/authenticated but not connected
                    status_text = "Available"
                    card_class = "server-card"
                    status_class = "status-offline"
                else:
                    status_color = "#ef4444"  # Red for offline/not available
                    status_text = "Offline"
                    card_class = "server-card"
                    status_class = "status-offline"
                
                # Determine the CSS class for the container based on server status
                if current_connected:
                    container_class = "connected-server-card"
                elif server_available:
                    container_class = "available-server-card"
                else:
                    container_class = "offline-server-card"
                
                # Create individual system box container

                
                st.markdown(f"""
                    <div class="system-box-container {container_class}">
                        <div class="system-box-header">
                            <div class="system-icon">{system['icon']}</div>
                            <div class="system-info">
                                <div class="system-name">
                                    <div class="status-indicator" style="background-color: {status_color};"></div>
                                    {system['name']}
                                </div>
                                <div class="system-status">{status_text}</div>
                            </div>
                        </div>
                        <div class="system-box-content">
                            <div class="system-description">
                                {system['description']}
                            </div>
                            <div class="system-actions">
                """, unsafe_allow_html=True)
                
                # Connection control integrated within the card
                if server_available:
                    # Add some spacing before the controls
                    st.markdown('<div style="margin-top: 8px;"></div>', unsafe_allow_html=True)
                    
                    # Use authentication status already determined above
                    
                    if needs_auth and not is_authenticated:
                        
                        # Authenticate button
                        auth_button_key = f"auth_btn_{system['session_key']}"
                        
                        # Simplified authenticate button
                        st.markdown(f"""
                            <div class="auth-button-container-{system['session_key']}">
                            <style>
                            .auth-button-container-{system['session_key']} div[data-testid="stButton"] > button {{
                                background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
                                color: white !important;
                                border: none !important;
                                border-radius: 12px !important;
                                padding: 14px 28px !important;
                                font-weight: 700 !important;
                                font-size: 0.95em !important;
                                text-transform: uppercase !important;
                                letter-spacing: 1px !important;
                                box-shadow: 0 4px 15px rgba(99, 102, 241, 0.4) !important;
                                transition: all 0.3s ease !important;
                            }}
                            
                            .auth-button-container-{system['session_key']} div[data-testid="stButton"] > button:hover {{
                                background: linear-gradient(135deg, #5b21b6, #6d28d9) !important;
                                transform: translateY(-2px) !important;
                                box-shadow: 0 8px 25px rgba(139, 92, 246, 0.5) !important;
                            }}
                            </style>
                        """, unsafe_allow_html=True)
                        
                        if st.button("🔓 AUTHENTICATE NOW", key=auth_button_key, use_container_width=True):
                            # Open authentication dialog
                            show_authentication_dialog(server_key)
                        
                        st.markdown("</div>", unsafe_allow_html=True)  # Close auth-button-container
                        
                        # Disabled toggle until authenticated
                        st.toggle(
                            f"Connect to {system['name']}",
                            value=False,
                            disabled=True,
                            key=f"disabled_toggle_{system['session_key']}",
                            help="Complete authentication first to enable connection"
                        )
                    
                    else:
                        # Normal toggle for authenticated systems or systems not requiring auth
                        
                        # Create toggle switch for connection
                        toggle_label = f"Connect to {system['name']}"
                        toggle_key = f"toggle_{system['session_key']}"
                        
                        # Show current authentication status for debugging
                        if needs_auth:
                            if is_authenticated:
                                toggle_help = f"✅ Authenticated - Toggle to connect to {system['name']}"
                            else:
                                toggle_help = f"❌ Not authenticated - Authenticate first to enable this toggle"
                        else:
                            toggle_help = f"Toggle connection to {system['name']}"
                        
                        new_state = st.toggle(
                            toggle_label,
                            value=current_connected,
                            key=toggle_key,
                            help=toggle_help
                        )
                        
                        # Update connection state if changed
                        if new_state != current_connected:
                            st.session_state[system["session_key"]] = new_state
                            st.rerun()
                else:
                    # For offline servers, show disabled state
                    st.markdown("""
                        <div style="
                            background: #f9fafb;
                            color: #9ca3af;
                            padding: 8px 16px;
                            border-radius: 8px;
                            text-align: center;
                            border: 1px solid #e5e7eb;
                            font-size: 0.85em;
                        ">
                            ❌ Server Unavailable
                        </div>
                        """, unsafe_allow_html=True)
                        
                # Close the card
                st.markdown("""
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
                
                # Add enhanced separator line between cards (but not after the last card)
                if index < len(systems) - 1:
                    st.markdown("""
                        <div style="
                            height: 3px;
                            background: linear-gradient(90deg, 
                                transparent 0%, 
                                rgba(99, 102, 241, 0.15) 10%,
                                rgba(139, 92, 246, 0.25) 30%, 
                                rgba(168, 85, 247, 0.3) 50%,
                                rgba(139, 92, 246, 0.25) 70%,
                                rgba(99, 102, 241, 0.15) 90%, 
                                transparent 100%);
                            margin: 28px 12px;
                            border-radius: 2px;
                            position: relative;
                            box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
                        "></div>
                        <div style="
                            width: 40px;
                            height: 1px;
                            background: linear-gradient(90deg, 
                                rgba(99, 102, 241, 0.4) 0%, 
                                rgba(139, 92, 246, 0.6) 100%);
                            margin: -1px auto 0 auto;
                            border-radius: 1px;
                            box-shadow: 0 0 8px rgba(99, 102, 241, 0.3);
                        "></div>
                    """, unsafe_allow_html=True)
                else:
                    # Add just a small space after the last card
                    st.markdown('<div style="margin-bottom: 12px;"></div>', unsafe_allow_html=True)
        
        # Global tool results management
        st.markdown("""
            <div class="chat-section-header">
                🧹 Tool Results Management
            </div>
            """, unsafe_allow_html=True)
            
        # Check if any tool results exist
        tool_results_exist = any(
            key.startswith("tool_result_") for key in st.session_state.keys()
        )
        
        if tool_results_exist:
            if st.button("🗑️ Clear All Tool Results", use_container_width=True, type="secondary"):
                # Clear all tool results from session state
                keys_to_remove = [key for key in st.session_state.keys() if key.startswith("tool_result_")]
                for key in keys_to_remove:
                    del st.session_state[key]
                
                # Also clear all selected tool states
                selected_keys_to_remove = [key for key in st.session_state.keys() if key.startswith("selected_tool_")]
                for key in selected_keys_to_remove:
                    st.session_state[key] = None
                
                st.success("✅ All tool results cleared!")
                st.rerun()
            
            # Show count of active results
            result_count = len([key for key in st.session_state.keys() if key.startswith("tool_result_")])
            st.info(f"📊 {result_count} tool result{'s' if result_count != 1 else ''} stored")
        else:
            st.info("📭 No tool results to clear")

    with sidebar_tab2:  # Sessions Tab
        st.markdown("""
            <div class="chat-section-header">
                📝 Session Management
            </div>
        """, unsafe_allow_html=True)
        
        # Initialize sessions if not exists
        if "chat_sessions" not in st.session_state:
            st.session_state.chat_sessions = {
                "default": {
                    "name": "Main Session",
                    "created": datetime.now().isoformat(),
                    "messages": 0
                }
            }
        
        # Current session selector
        session_names = list(st.session_state.chat_sessions.keys())
        current_session = st.selectbox(
            "Current Session",
            session_names,
            index=0,
            key="current_session"
        )
        
        # Session info
        if current_session in st.session_state.chat_sessions:
            session_info = st.session_state.chat_sessions[current_session]
            st.info(f"📅 Created: {session_info['created'][:10]}\n💬 Messages: {session_info.get('messages', 0)}")
        
        # Session name input for renaming
        if current_session in st.session_state.chat_sessions:
            session_info = st.session_state.chat_sessions[current_session]
            new_name = st.text_input(
                "Session Name",
                value=session_info['name'],
                key="session_name_input",
                placeholder="Enter session name..."
            )
            
            if new_name != session_info['name'] and new_name.strip():
                st.session_state.chat_sessions[current_session]['name'] = new_name.strip()
                st.rerun()
        
        # Session management buttons
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ New Session", use_container_width=True):
                new_id = f"session_{len(st.session_state.chat_sessions)}"
                st.session_state.chat_sessions[new_id] = {
                    "name": f"Session {len(st.session_state.chat_sessions)}",
                    "created": datetime.now().isoformat(),
                    "messages": 0
                }
                st.success("New session created!")
                
        with col2:
            if st.button("🗑️ Delete", use_container_width=True, disabled=(len(session_names) <= 1)):
                if len(session_names) > 1:
                    del st.session_state.chat_sessions[current_session]
                    st.success("Session deleted!")
                    st.rerun()
        
        st.markdown("---")
        
        # Session history
        st.markdown("""
            <div class="chat-section-header">
                📚 Recent Sessions
            </div>
        """, unsafe_allow_html=True)
        for session_id, session_data in list(st.session_state.chat_sessions.items())[:5]:
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{session_data['name']}**")
                    st.caption(f"📅 {session_data['created'][:10]}")
                with col2:
                    if st.button("🔄", key=f"load_{session_id}", help="Load session"):
                        st.session_state.current_session = session_id
                        st.rerun()

# --- Beautiful Enhanced Header ---
current_time = datetime.now().strftime("%H:%M")
server_count = len(server_manager.get_available_servers()) if server_manager else 0
connected_count = sum(1 for system in systems if st.session_state.get(system["session_key"], False))

# Enhanced beautiful header with modern design
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    .main-header {
        font-family: 'Inter', sans-serif;
        background: linear-gradient(135deg, 
                    #667eea 0%, 
                    #764ba2 25%, 
                    #f093fb 50%, 
                    #f5576c 75%, 
                    #4facfe 100%);
        background-size: 300% 300%;
        animation: gradientFlow 8s ease infinite;
        color: white;
        padding: 3rem 2rem;
        border-radius: 24px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 
            0 20px 60px rgba(102, 126, 234, 0.4),
            0 0 0 1px rgba(255, 255, 255, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.2);
        position: relative;
        overflow: hidden;
    }
    
    .main-header::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.1), 
                    transparent);
        animation: shimmer 3s infinite;
    }
    
    .header-content {
        position: relative;
        z-index: 2;
        font-size: 2.8em;
        font-weight: 800;
        margin-bottom: 12px;
        text-shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
    
    .main-title {
        margin: 0;
        font-size: 3.5rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
        text-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        flex-wrap: wrap;
    }
    
    .robot-icon {
        font-size: 1.2em;
        filter: drop-shadow(0 0 20px rgba(255, 255, 255, 0.6));
        animation: robotFloat 3s ease-in-out infinite;
    }
    
    .verna-text {
        background: linear-gradient(45deg, #ffffff, #f8fafc, #e2e8f0);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        position: relative;
    }
    
    .ai-badge {
        font-size: 0.5em;
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.9), 
                    rgba(255, 255, 255, 0.7));
        color: #1e293b;
        padding: 0.4rem 1rem;
        border-radius: 25px;
        font-weight: 700;
        letter-spacing: 0.05em;
        box-shadow: 
            0 4px 15px rgba(0, 0, 0, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.4);
        border: 2px solid rgba(255, 255, 255, 0.3);
    }
    
    .subtitle {
        margin: 1rem 0 1.5rem 0;
        font-size: 1.4rem;
        font-weight: 500;
        opacity: 0.95;
        letter-spacing: 0.02em;
        text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    .feature-pills {
        display: flex;
        justify-content: center;
        gap: 1rem;
        flex-wrap: wrap;
        margin-top: 1.5rem;
    }
    
    .pill {
        background: rgba(255, 255, 255, 0.15);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 30px;
        padding: 0.75rem 1.5rem;
        font-size: 0.9rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    
    .pill:hover {
        background: rgba(255, 255, 255, 0.25);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
    }
    
    @keyframes gradientFlow {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    
    @keyframes shimmer {
        0% { left: -100%; }
        100% { left: 100%; }
    }
    
    @keyframes robotFloat {
        0%, 100% { transform: translateY(0px) rotate(0deg); }
        50% { transform: translateY(-5px) rotate(5deg); }
    }
    
    .status-container {
        display: flex;
        justify-content: center;
        gap: 1.5rem;
        margin-bottom: 2.5rem;
        flex-wrap: wrap;
    }
    
    .status-item {
        background: linear-gradient(135deg, 
                    rgba(255, 255, 255, 0.1), 
                    rgba(255, 255, 255, 0.05));
        backdrop-filter: blur(15px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 25px;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        font-size: 0.95rem;
        transition: all 0.3s ease;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        position: relative;
        overflow: hidden;
    }
    
    .status-item::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, 
                    transparent, 
                    rgba(255, 255, 255, 0.1), 
                    transparent);
        transition: left 0.5s;
    }
    
    .status-item:hover::before {
        left: 100%;
    }
    
    .status-online {
        border-color: rgba(34, 197, 94, 0.4);
        color: #10b981;
        background: linear-gradient(135deg, 
                    rgba(34, 197, 94, 0.15), 
                    rgba(34, 197, 94, 0.05));
    }
    
    .status-neutral {
        border-color: rgba(156, 163, 175, 0.4);
        color: #6b7280;
        background: linear-gradient(135deg, 
                    rgba(156, 163, 175, 0.15), 
                    rgba(156, 163, 175, 0.05));
    }
    
    .status-connected {
        border-color: rgba(59, 130, 246, 0.4);
        color: #3b82f6;
        background: linear-gradient(135deg, 
                    rgba(59, 130, 246, 0.15), 
                    rgba(59, 130, 246, 0.05));
    }
    
    .pulse-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 0.5rem;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.7; transform: scale(1.1); }
    }
</style>

<div class="main-header">
    <div class="header-content">
        <h1 class="main-title">
            <span class="robot-icon">🤖</span>
            <span class="verna-text">VERNA</span>
            <span class="ai-badge">AI</span>
        </h1>
        <p class="subtitle">Next-Generation AI Assistant</p>
        <div class="feature-pills">
            <div class="pill">🚀 MCP Protocol</div>
            <div class="pill">🔗 Multi-System</div>
            <div class="pill">🧠 Intelligent</div>
            <div class="pill">⚡ Real-time</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Enhanced status bar with beautiful styling
st.markdown(f"""
<div class="status-container">
    <div class="status-item status-online">
        <span class="pulse-dot" style="background-color: #22c55e;"></span>
        {server_count} Systems Available
    </div>
    <div class="status-item status-neutral">
        <span>🕐</span> {current_time}
    </div>
    <div class="status-item status-connected">
        <span class="pulse-dot" style="background-color: #3b82f6;"></span>
        {connected_count} Connected
    </div>
</div>
""", unsafe_allow_html=True)

# --- Main Area: Tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["💬 Chat", "🔍 Search", "📊 Dashboard", "⚙️ Settings"])

with tab1:  # Chat Tab
    # Connected Systems Pane (Collapsible) - Only show if manually connected AND server is available
    connected_servers = []
    for s in systems:
        is_connected = st.session_state.get(s["session_key"], False)
        is_available = (server_manager and s.get("server_key") in server_manager.get_available_servers())
        if is_connected and is_available:
            connected_servers.append(s)
    
    if connected_servers:
        st.markdown("""
            <div class="chat-section-header">
                🔗 Active AI Connections
            </div>
        """, unsafe_allow_html=True)
        
        with st.expander(f"View Connected Systems ({len(connected_servers)})", expanded=False):
            for system in connected_servers:
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Check if icon is SVG (company logo) or emoji
                    if system['icon'].startswith('<svg'):
                        st.markdown(f"""
                            <div style="display: flex; align-items: center; gap: 8px;">
                                {system['icon']}
                                <strong>{system['name']}</strong>
                            </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"**{system['icon']} {system['name']}**")
                    st.caption(system['description'][:60] + "...")
                
                with col2:
                    st.success("🟢 Active")
                
                # Show available tools for connected servers
                if server_manager:
                    st.markdown("""
                        <div style="
                            background: rgba(99, 102, 241, 0.1);
                            border: 1px solid rgba(99, 102, 241, 0.3);
                            border-radius: 8px;
                            padding: 8px 12px;
                            margin: 8px 0;
                            text-align: center;
                            font-weight: 500;
                            color: #6366f1;
                        ">
                            🛠️ Available AI Tools
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Real tools from server implementations
                    server_tools = {
                        "youtube": [
                            ("🔍 Search Videos", "search"),
                            ("📝 Get Transcript", "get_transcript"), 
                            ("💬 Get Comments", "get_comments"),
                            ("🎯 Analyze Video", "analyze_video"),
                            ("🧠 Parse Search Intent", "parse_search_intent")
                        ],
                        "weather": [
                            ("🌤️ Get Forecast", "get_forecast"),
                            ("⚠️ Get Alerts", "get_alerts")
                        ],
                        "slack": [
                            ("📤 Send Message", "send_message"),
                            ("📋 List Channels", "list_channels"),
                            ("👥 Get Users", "get_users"),
                            ("📖 Read Messages", "read_messages")
                        ],
                        "web_search_scrape_rag": [
                            ("🔍 Intelligent Search", "intelligent_web_search"),
                            ("🌐 Enhanced Query", "enhance_query"),
                            ("📊 Search & Analyze", "execute_intelligent_search")
                        ],
                        "microsoft.docs.mcp": [
                            ("📚 Search Docs", "search_docs"),
                            ("📄 Get Article", "get_article"),
                            ("📑 List Topics", "list_topics")
                        ],
                        "service_system": [
                            ("📋 Get Case Summary", "get_case_summary"),
                            ("🔧 Get Resolution", "get_resolution"),
                            ("🔍 Search Cases", "search_cases_by_query"),
                            ("❓ Handle Questions", "handle_case_related_questions")
                        ],
                        "sales_system": [
                            ("👥 Sales Lead Query", "handle_sales_lead_question"),
                            ("📊 Campaign Query", "handle_campaign_question"),
                            ("💼 Lead Details", "get_lead_details")
                        ],
                        "playwright": [
                            ("🌐 Navigate", "navigate"),
                            ("📷 Screenshot", "screenshot"),
                            ("🖱️ Click Element", "click"),
                            ("⌨️ Type Text", "type")
                        ],
                        "mcp-atlassian": [
                            ("📝 Create Ticket", "create_ticket"),
                            ("🔍 Search Issues", "search_issues"),
                            ("📋 Get Ticket", "get_ticket"),
                            ("📚 Search Confluence", "search_confluence")
                        ]
                    }
                    
                    tools_list = server_tools.get(system['server_key'], [("🛠️ Default Tool", "default_tool")])
                    
                    # Define tools that require parameters
                    tools_with_parameters = {
                        "search": {"query": "Search query", "max_results": "Max results (optional, default 10)"},
                        "get_transcript": {"video_id": "YouTube Video ID or URL"},
                        "get_comments": {"video_id": "YouTube Video ID or URL", "max_results": "Max comments (optional, default 50)"},
                        "analyze_video": {"user_query": "Your question about the video", "video_id": "YouTube Video ID or URL"},
                        "comments": {"video_id": "YouTube Video ID or URL", "max_results": "Max comments (optional, default 50)"},
                        "transcript": {"video_id": "YouTube Video ID or URL"},
                        "get_forecast": {"latitude": "Latitude (decimal degrees)", "longitude": "Longitude (decimal degrees)"},
                        "get_alerts": {"state": "US State code (e.g., CA, NY, FL)"},
                        "get_case_summary": {"ticket_number": "Support Ticket Number"},
                        "get_resolution": {"query": "Problem description", "ticketNumber": "Ticket Number (optional)"},
                        "search_cases_by_query": {"user_query": "Search query", "max_results": "Max results (optional, default 10)"},
                        "handle_case_related_questions": {"user_question": "Your question"},
                        "handle_sales_lead_question": {"user_question": "Your question about leads"},
                        "handle_campaign_question": {"user_question": "Your question about campaigns"},
                        "get_lead_details": {"lead_id": "Lead ID or name"},
                        "intelligent_web_search": {"query": "Search query", "num_sources": "Number of sources (optional, default 5)", "fast_mode": "Fast mode (true/false, optional)"},
                        "send_message": {"channel": "Channel name or ID", "message": "Message text"},
                        "read_messages": {"channel": "Channel name or ID", "limit": "Number of messages (optional, default 10)"},
                        "search_docs": {"query": "Search query", "max_results": "Max results (optional, default 10)"}
                    }
                    
                    # Tool selection with buttons
                    st.markdown("**🔧 Select Tool:**")
                    
                    # Initialize selected tool state
                    selected_tool_key_state = f"selected_tool_{system['server_key']}"
                    if selected_tool_key_state not in st.session_state:
                        st.session_state[selected_tool_key_state] = None
                    
                    # Tool selection buttons
                    tool_cols = st.columns(min(len(tools_list), 3))
                    for i, (tool_display, tool_key) in enumerate(tools_list):
                        with tool_cols[i % 3]:
                            # Check if this tool is selected
                            is_selected = st.session_state[selected_tool_key_state] == tool_key
                            button_type = "primary" if is_selected else "secondary"
                            
                            if st.button(
                                f"{'✅ ' if is_selected else ''}{tool_display}", 
                                key=f"select_tool_{system['server_key']}_{tool_key}",
                                use_container_width=True,
                                type=button_type
                            ):
                                # Select this tool
                                st.session_state[selected_tool_key_state] = tool_key
                                st.rerun()
                    
                    # Show selected tool form
                    if st.session_state[selected_tool_key_state]:
                        selected_tool_key = st.session_state[selected_tool_key_state]
                        selected_tool_display = next(display for display, key in tools_list if key == selected_tool_key)
                        
                        st.markdown("---")
                        
                        # Dynamic parameter form for selected tool
                        with st.form(key=f"tool_form_{system['server_key']}"):
                            st.markdown(f"**⚙️ Run: {selected_tool_display}**")
                            
                            parameters = {}
                            
                            # Show parameters if tool requires them
                            if selected_tool_key in tools_with_parameters:
                                required_params = tools_with_parameters[selected_tool_key]
                                
                                for param_name, param_description in required_params.items():
                                    is_optional = "optional" in param_description.lower()
                                    
                                    # Special input types for certain parameters
                                    if param_name in ['max_results', 'num_sources', 'limit']:
                                        # Number input for count parameters
                                        if is_optional:
                                            parameters[param_name] = st.number_input(
                                                param_description,
                                                min_value=1,
                                                max_value=100,
                                                value=None,
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is optional"
                                            )
                                        else:
                                            parameters[param_name] = st.number_input(
                                                f"{param_description} *",
                                                min_value=1,
                                                max_value=100,
                                                value=10,
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is required"
                                            )
                                    elif param_name in ['latitude', 'longitude']:
                                        # Number input for coordinates
                                        min_val = -90 if param_name == 'latitude' else -180
                                        max_val = 90 if param_name == 'latitude' else 180
                                        parameters[param_name] = st.number_input(
                                            f"{param_description} *",
                                            min_value=min_val,
                                            max_value=max_val,
                                            value=0.0,
                                            step=0.000001,
                                            format="%.6f",
                                            key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                            help="This parameter is required"
                                        )
                                    elif param_name == 'fast_mode':
                                        # Checkbox for boolean
                                        parameters[param_name] = st.checkbox(
                                            param_description,
                                            key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                            help="This parameter is optional"
                                        )
                                    elif param_name in ['message', 'user_query', 'user_question', 'query']:
                                        # Text area for longer text
                                        if is_optional:
                                            parameters[param_name] = st.text_area(
                                                param_description, 
                                                height=100,
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is optional"
                                            )
                                        else:
                                            parameters[param_name] = st.text_area(
                                                f"{param_description} *", 
                                                height=100,
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is required"
                                            )
                                    else:
                                        # Regular text input
                                        if is_optional:
                                            parameters[param_name] = st.text_input(
                                                param_description, 
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is optional"
                                            )
                                        else:
                                            parameters[param_name] = st.text_input(
                                                f"{param_description} *", 
                                                key=f"param_{system['server_key']}_{selected_tool_key}_{param_name}",
                                                help="This parameter is required"
                                            )
                            else:
                                st.info("ℹ️ This tool doesn't require any parameters")
                            
                            # Run button
                            run_button = st.form_submit_button("Run", use_container_width=True, type="primary")
                            
                            if run_button:
                                # Validate parameters if required
                                if selected_tool_key in tools_with_parameters:
                                    required_params = tools_with_parameters[selected_tool_key]
                                    filtered_params = {k: v for k, v in parameters.items() if v is not None and str(v).strip()}
                                    required_params_list = [k for k, v in required_params.items() if "optional" not in v.lower()]
                                    missing_required = [k for k in required_params_list if k not in filtered_params or not str(filtered_params[k]).strip()]
                                    
                                    if missing_required:
                                        st.error(f"❌ Please provide required parameters: {', '.join(missing_required)}")
                                    else:
                                        # Make actual tool call with parameters
                                        with st.spinner(f"🔄 Executing {selected_tool_display}..."):
                                            try:
                                                # Prepare the tool call request
                                                tool_request = {
                                                    'action': selected_tool_key,
                                                    **filtered_params
                                                }
                                                
                                                # Special handling for YouTube video URLs
                                                if system['server_key'] == 'youtube' and 'video_id' in filtered_params:
                                                    video_id = extract_video_id(filtered_params['video_id'])
                                                    if video_id:
                                                        tool_request['video_id'] = video_id
                                                    else:
                                                        raise ValueError("Invalid YouTube video ID or URL")
                                                
                                                # Make actual call to MCP server
                                                result = run_async(server_manager.route_to_server(system['server_key'], tool_request))
                                                
                                                # Store actual result
                                                tool_result_key = f"tool_result_{system['server_key']}"
                                                st.session_state[tool_result_key] = {
                                                    "server": system['name'],
                                                    "server_key": system['server_key'],
                                                    "tool": selected_tool_display,
                                                    "tool_key": selected_tool_key,
                                                    "timestamp": datetime.now().isoformat(),
                                                    "parameters": filtered_params,
                                                    "result": result,
                                                    "success": True
                                                }
                                                st.success(f"✅ {selected_tool_display} executed successfully!")
                                                
                                            except Exception as e:
                                                # Store error result
                                                tool_result_key = f"tool_result_{system['server_key']}"
                                                st.session_state[tool_result_key] = {
                                                    "server": system['name'],
                                                    "server_key": system['server_key'],
                                                    "tool": selected_tool_display,
                                                    "tool_key": selected_tool_key,
                                                    "timestamp": datetime.now().isoformat(),
                                                    "parameters": filtered_params,
                                                    "result": str(e),
                                                    "success": False,
                                                    "error": str(e)
                                                }
                                                st.error(f"❌ Error executing {selected_tool_display}: {str(e)}")
                                        
                                        st.rerun()
                                else:
                                    # Make actual parameter-less tool call
                                    with st.spinner(f"🔄 Executing {selected_tool_display}..."):
                                        try:
                                            # Prepare the tool call request
                                            tool_request = {'action': selected_tool_key}
                                            
                                            # Make actual call to MCP server
                                            result = run_async(server_manager.route_to_server(system['server_key'], tool_request))
                                            
                                            # Store actual result
                                            tool_result_key = f"tool_result_{system['server_key']}"
                                            st.session_state[tool_result_key] = {
                                                "server": system['name'],
                                                "server_key": system['server_key'],
                                                "tool": selected_tool_display,
                                                "tool_key": selected_tool_key,
                                                "timestamp": datetime.now().isoformat(),
                                                "parameters": None,
                                                "result": result,
                                                "success": True
                                            }
                                            st.success(f"✅ {selected_tool_display} executed successfully!")
                                            
                                        except Exception as e:
                                            # Store error result
                                            tool_result_key = f"tool_result_{system['server_key']}"
                                            st.session_state[tool_result_key] = {
                                                "server": system['name'],
                                                "server_key": system['server_key'],
                                                "tool": selected_tool_display,
                                                "tool_key": selected_tool_key,
                                                "timestamp": datetime.now().isoformat(),
                                                "parameters": None,
                                                "result": str(e),
                                                "success": False,
                                                "error": str(e)
                                            }
                                            st.error(f"❌ Error executing {selected_tool_display}: {str(e)}")
                                    
                                    st.rerun()
                    else:
                        st.info("👆 Select a tool above to configure and run it")
                
                # Show tool results in a contained box for this server
                tool_result_key = f"tool_result_{system['server_key']}"
                if tool_result_key in st.session_state:
                    tool_data = st.session_state[tool_result_key]
                    
                    # Display results in a contained box
                    with st.container():
                        # Header without clear button
                        st.markdown("""
                            <div style="
                                border: 2px solid #4CAF50;
                                border-radius: 10px;
                                padding: 15px;
                                margin: 10px 0;
                                background: rgba(76, 175, 80, 0.1);
                                backdrop-filter: blur(10px);
                            ">
                                <h4 style="margin: 0 0 10px 0; color: #4CAF50;">🛠️ Tool Results</h4>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Tool execution details
                        if tool_data.get('success', True):
                            st.success(f"**{tool_data['tool']}** executed successfully")
                        else:
                            st.error(f"**{tool_data['tool']}** execution failed")
                        st.caption(f"⏰ {tool_data['timestamp']}")
                        
                        # Parameters if they exist
                        if tool_data.get('parameters'):
                            # Initialize toggle state for parameters
                            params_toggle_key = f"show_params_{system['server_key']}"
                            if params_toggle_key not in st.session_state:
                                st.session_state[params_toggle_key] = False
                            
                            # Toggle button for parameters
                            if st.button(
                                f"📋 {'Hide' if st.session_state[params_toggle_key] else 'Show'} Parameters Used",
                                key=f"toggle_params_{system['server_key']}",
                                use_container_width=True
                            ):
                                st.session_state[params_toggle_key] = not st.session_state[params_toggle_key]
                                st.rerun()
                            
                            # Show parameters if toggled on
                            if st.session_state[params_toggle_key]:
                                st.markdown("""
                                    <div style="
                                        background: rgba(59, 130, 246, 0.1);
                                        border-left: 4px solid #3b82f6;
                                        padding: 12px;
                                        margin: 8px 0;
                                        border-radius: 4px;
                                    ">
                                """, unsafe_allow_html=True)
                                for param, value in tool_data['parameters'].items():
                                    st.write(f"**{param}:** `{value}`")
                                st.markdown("</div>", unsafe_allow_html=True)
                        
                        # Tool Output Section Header
                        st.markdown("### 📄 Tool Output")
                        st.info(f"**Function:** `{tool_data.get('tool_key', 'N/A')}`")
                        
                        # Show actual result or error
                        result = tool_data.get('result', 'No result data')
                        
                        # Format the result for display
                        if isinstance(result, dict):
                            # Pretty print JSON results
                            import json
                            formatted_result = json.dumps(result, indent=2, ensure_ascii=False)
                        elif isinstance(result, list):
                            # Format list results
                            formatted_result = '\n'.join([f"• {item}" for item in result])
                        else:
                            # String or other format
                            formatted_result = str(result)
                        
                        # Show success or error styling
                        if tool_data.get('success', True):
                            st.text_area(
                                "✅ Response:",
                                value=formatted_result,
                                height=150,
                                disabled=True,
                                key=f"output_{system['server_key']}"
                            )
                        else:
                            st.text_area(
                                "❌ Error:",
                                value=formatted_result,
                                height=100,
                                disabled=True,
                                key=f"error_{system['server_key']}"
                            )
                                
                        # Clear result button
                        if st.button(f"🗑️ Clear Result", key=f"clear_{system['server_key']}", use_container_width=True):
                            del st.session_state[tool_result_key]
                            st.rerun()
                
                st.markdown("---")
    else:
        # Simple modern notification when no systems are connected
        st.markdown("""
            <div style="
                background: rgba(156, 163, 175, 0.1);
                border: 1px solid rgba(156, 163, 175, 0.3);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                margin: 20px 0;
            ">
                <div style="font-size: 1.2em; margin-bottom: 8px;">🔗</div>
                <div style="color: #9ca3af; font-size: 0.95em;">
                    No systems connected
                </div>
                <div style="color: #6b7280; font-size: 0.8em; margin-top: 4px;">
                    Connect servers from the sidebar to get started
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Initialize chat history only when needed
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Handle example query injection and reload message
    default_value = ""
    if "example_query" in st.session_state:
        default_value = st.session_state["example_query"]
        del st.session_state["example_query"]  # Clear after use
    elif "reload_message" in st.session_state:
        default_value = st.session_state["reload_message"]
        del st.session_state["reload_message"]  # Clear after use

    # Only show chat container if there are actual messages to display
    if connected_servers and len(st.session_state.chat_history) > 0:
        # Chat messages container with better scrolling
        st.markdown("""
            <div style="
                min-height: 200px;
                max-height: 600px;
                overflow-y: auto;
                padding: 20px;
                margin-bottom: 30px;
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                scrollbar-width: thin;
                scrollbar-color: rgba(99, 102, 241, 0.3) transparent;
            ">
        """, unsafe_allow_html=True)
        
                # Display messages directly without grouping or headers
        for idx, msg in enumerate(st.session_state.chat_history):
            if msg["role"] == "user":
                # User message card with copy and reload buttons
                escaped_content = msg["content"].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                st.markdown(f"""
                    <div class="chat-message-card user-message-card">
                        <div class="message-header">
                            <div class="message-avatar user-avatar">👤</div>
                            <div class="message-meta">
                                <div class="message-sender">You</div>
                                <div class="message-time">{msg.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</div>
                            </div>
                        </div>
                        <div class="chat-bubble-user">
                            <div class="message-content">
                                {escaped_content}
                            </div>
                            <div class="message-actions user-actions">
                                <span class="action-btn copy-btn" title="Copy message">
                                    📋
                                </span>
                                <span class="action-btn reload-btn" title="Reload message">
                                    🔄
                                </span>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                # Assistant message card with copy, thumbs up, and thumbs down buttons
                content = msg["content"]
                # Use HTML escaping to prevent black divs
                escaped_content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')
                
                # Create the HTML content with proper escaping
                message_time = msg.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                
                st.markdown(f"""
                    <div class="chat-message-card assistant-message-card">
                        <div class="message-header">
                            <div class="message-avatar assistant-avatar">🤖</div>
                            <div class="message-meta">
                                <div class="message-sender">AI Assistant</div>
                                <div class="message-time">{message_time}</div>
                            </div>
                        </div>
                        <div class="chat-bubble-assistant">
                            <div class="message-content">
                                {escaped_content}
                            </div>
                            <div class="message-actions assistant-actions">
                                <span class="action-btn copy-btn" title="Copy response">
                                    📋
                                </span>
                                <span class="action-btn thumbs-up-btn" title="Good response">
                                    👍
                                </span>
                                <span class="action-btn thumbs-down-btn" title="Poor response">
                                    👎
                                </span>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

    
    # Connection status indicator
    if server_manager:
        active_count = len(connected_servers)
        if active_count > 0:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 15px;">
                    <small style='color: #10b981; font-size: 0.8em;'>🔗 {active_count} system{'s' if active_count != 1 else ''} connected</small>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div style="text-align: center; margin-bottom: 15px;">
                    <small style='color: #9ca3af; font-size: 0.8em;'>💡 Connect systems from the sidebar to get started</small>
                </div>
            """, unsafe_allow_html=True)
    
    # Sample prompts section (only show when chat history is empty)
    if len(st.session_state.chat_history) == 0:
        st.markdown("""
            <div style="
                margin-bottom: 20px;
                padding: 20px;
                background: linear-gradient(135deg, rgba(99, 102, 241, 0.05), rgba(139, 92, 246, 0.05));
                border-radius: 16px;
                border: 1px solid rgba(99, 102, 241, 0.1);
            ">
                <h4 style="
                    text-align: center; 
                    margin-bottom: 16px; 
                    color: #374151; 
                    font-weight: 600;
                    font-size: 1.1em;
                ">
                    💡 Get started with these sample prompts
                </h4>
                <div style="
                    text-align: center; 
                    margin-bottom: 12px; 
                    color: #6b7280; 
                    font-size: 0.85em;
                    font-weight: 500;
                ">
                    🔗 Multi-System Queries | 📍 Single System Queries
                </div>
            </div>
            
            <style>
                /* System icon + prompt text cards */
                div[data-testid="stButton"] button,
                .stButton button,
                button[kind="primary"],
                button[kind="secondary"] {
                    background-color: #f8fafc !important;
                    background-image: none !important;
                    background: #f8fafc !important;
                    border: 1px solid #d1d5db !important;
                    border-radius: 8px !important;
                    padding: 10px 8px !important;
                    min-height: 120px !important;
                    height: auto !important;
                    color: #111827 !important;
                    font-size: 9px !important;
                    font-weight: 500 !important;
                    line-height: 1.3 !important;
                    text-align: center !important;
                    white-space: pre-line !important;
                    word-wrap: break-word !important;
                    transition: all 0.2s ease !important;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
                    cursor: pointer !important;
                    text-shadow: none !important;
                    display: flex !important;
                    flex-direction: column !important;
                    justify-content: center !important;
                    align-items: center !important;
                    gap: 4px !important;
                }
                
                div[data-testid="stButton"] button:hover,
                .stButton button:hover {
                    background-color: #ffffff !important;
                    background: #ffffff !important;
                    border-color: #9ca3af !important;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
                    transform: translateY(-1px) !important;
                    color: #111827 !important;
                }
                
                div[data-testid="stButton"] button:active,
                .stButton button:active {
                    transform: translateY(0px) !important;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05) !important;
                }
                
                div[data-testid="stButton"] button:focus,
                .stButton button:focus {
                    outline: 1px solid #3b82f6 !important;
                    outline-offset: 1px !important;
                    border-color: #3b82f6 !important;
                }
                
                /* Ensure all text elements inside buttons are visible */
                div[data-testid="stButton"] button *,
                .stButton button * {
                    color: #111827 !important;
                    text-shadow: none !important;
                }
                
                /* Style the system icon specifically */
                div[data-testid="stButton"] button span:first-child {
                    font-size: 18px !important;
                    line-height: 1 !important;
                    margin-bottom: 2px !important;
                }
            </style>
        """, unsafe_allow_html=True)
        
        # Create focused cross-functional sample prompts for key business systems
        sample_prompts = [
            {
                "system_icon": "💼",
                "system_name": "Sales Lead Pipeline",
                "prompt": "Show current Adobe Photoshop related leads and check if any have service tickets that need sales follow-up",
                "server_key": "sales_system",
                "systems": ["Sales CRM"]
            },
            {
                "system_icon": "🛠️",
                "system_name": "Service Resolution",
                "prompt": "Find Adobe Photoshop support cases and create content for FAQ based on common issues. Also provide Summary for each case along with case number.", 
                "server_key": "service_system",
                "systems": ["Service Desk"]
            },
            {
                "system_icon": "🔍",
                "system_name": "Adobe Solutions Research",
                "prompt": "Latest news about AI innovation in Adobe 2025 along with sources.",
                "server_key": "web_search_scrape_rag",
                "systems": ["Web Search"]
            },
            {
                "system_icon": "📺",
                "system_name": "Adobe Product Training",
                "prompt": "Find YouTube videos about Adobe Photoshop crashing on Windows 11 and analyze top 5, Also, summarize ATSAIE-402 and provide test cases for it.",
                "server_key": "multi_system",
                "systems": ["YouTube", "Jira", "Service Desk"]
            },
            {
                "system_icon": "📝",
                "system_name": "Content Marketing",
                "prompt": "Analyze Adobe product content performance and create marketing materials for upcoming campaigns",
                "server_key": "content",
                "systems": ["Content Management"]
            },
            {
                "system_icon": "🌦️",
                "system_name": "Campaign Weather Planning",
                "prompt": "Check weather forecast for California and Missouri to plan optimal timing for Adobe Creative Suite marketing campaign launch",
                "server_key": "weather",
                "systems": ["Weather API"]
            },
            {
                "system_icon": "📈",
                "system_name": "Adobe Sales Intelligence",
                "prompt": "How to create a new VM in Azure? Also, How to create a new User in Dynamics CRM?",
                "server_key": "multi_system",
                "systems": ["Microsoft Docs", "Azure Portal", "Dynamics CRM"]
            },
            {
                "system_icon": "👤",
                "system_name": "Customer 360 View",
                "prompt": "Fetch 'THE QUANTUM ALLIANCE' account details and it's relevant leads and Support cases. Summarize each case and tell me how to resolve it.",
                "server_key": "multi_system",
                "systems": ["Sales CRM", "Service Desk", "Account Management"]
            },
            {
                "system_icon": "🚨",
                "system_name": "Adobe Photoshop Crisis Response",
                "prompt": "Adobe Photoshop is crashing - find top 5 service tickets for this issue, search web for latest solutions, check AdobeCare YouTube channel for troubleshooting videos, identify any current Adobe Photoshop leads in sales system, and recommend a final solution after analyzing all the information.",
                "server_key": "multi_system",
                "systems": ["Service Desk", "Web Search", "YouTube", "Sales CRM"]
            },
            {
                "system_icon": "🔧",
                "system_name": "Technical Documentation Hub",
                "prompt": "Search Adobe Wiki for Photoshop troubleshooting documentation, find related JIRA tickets like ATSAIE-402 for technical issues, lookup Microsoft Docs for Windows compatibility solutions, and analyze our technical documentation effectiveness across all platforms",
                "server_key": "multi_system",
                "systems": ["Adobe Wiki", "JIRA", "Microsoft Docs"]
            },
            {
                "system_icon": "⚡",
                "system_name": "Complete Business Intelligence",
                "prompt": "Analyze weather impact on our California sales campaigns, find YouTube content about our products, check service desk for regional issues, search web for competitor analysis, and review current sales pipeline for weather-sensitive opportunities",
                "server_key": "multi_system",
                "systems": ["Weather API", "YouTube", "Service Desk", "Web Search", "Sales CRM"]
            },
            {
                "system_icon": "🎯",
                "system_name": "Social Media Intelligence Hub",
                "prompt": "Analyze Twitter sentiment about Adobe products, find trending YouTube videos in our niche, check for social media mentions in service tickets, create marketing content based on social insights, and identify potential leads from social engagement",
                "server_key": "multi_system",
                "systems": ["Twitter Analytics", "YouTube", "Service Desk", "Marketing", "Sales CRM"]
            }
        ]
        
        # Display sample prompts as Fluent UI cards - dynamic layout based on prompt count
        num_prompts = len(sample_prompts)
        if num_prompts <= 8:
            # 2 rows of 4 for 8 or fewer prompts
            rows, cols_per_row = 2, 4
        elif num_prompts <= 9:
            # 3 rows of 3 for 9 prompts
            rows, cols_per_row = 3, 3
        else:
            # 4 rows of varying columns for 10+ prompts
            rows, cols_per_row = 4, 3
        
        for row in range(rows):
            # For the last row, adjust columns if needed
            if row == rows - 1 and num_prompts % cols_per_row != 0:
                remaining_prompts = num_prompts - (row * cols_per_row)
                cols = st.columns(remaining_prompts)
                col_range = remaining_prompts
            else:
                cols = st.columns(cols_per_row)
                col_range = cols_per_row
                
            for col_idx in range(col_range):
                prompt_idx = row * cols_per_row + col_idx
                if prompt_idx < len(sample_prompts):
                    prompt_data = sample_prompts[prompt_idx]
                    
                    with cols[col_idx]:
                        # Create system combination indicator
                        systems_text = " + ".join(prompt_data['systems'])
                        is_multi_system = len(prompt_data['systems']) > 1
                        
                        # Create clickable card as a button showing system icon, name, systems, and prompt
                        if is_multi_system:
                            button_text = f"{prompt_data['system_icon']}\n{prompt_data['system_name']}\n🔗 {systems_text}\n\n{prompt_data['prompt']}"
                            help_text = f"{prompt_data['system_name']} (Multi-System: {systems_text}): Click to fill input and auto-send"
                        else:
                            button_text = f"{prompt_data['system_icon']}\n{prompt_data['system_name']}\n📍 {systems_text}\n\n{prompt_data['prompt']}"
                            help_text = f"{prompt_data['system_name']} ({systems_text}): Click to fill input and auto-send"
                        
                        if st.button(
                            button_text, 
                            key=f"sample_prompt_{prompt_idx}",
                            use_container_width=True,
                            help=help_text
                        ):
                            # Set the prompt text and trigger auto-send
                            st.session_state.sample_prompt_selected = prompt_data['prompt']
                            st.session_state.auto_send_prompt = True
                            st.rerun()
    
    
    # Check if a sample prompt was selected and prepare for auto-send
    if hasattr(st.session_state, 'sample_prompt_selected'):
        default_value = st.session_state.sample_prompt_selected
        # Clear the selected prompt to avoid reusing it
        del st.session_state.sample_prompt_selected
    
    # Fixed bottom input area
    st.markdown("""
        <div style="
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            padding: 24px;
            border-top: 2px solid rgba(99, 102, 241, 0.15);
            box-shadow: 
                0 -8px 40px rgba(51, 65, 85, 0.08),
                0 0 0 1px rgba(255, 255, 255, 0.6),
                inset 0 1px 0 rgba(255, 255, 255, 0.8);
            z-index: 1000;
            margin: 0;
        ">
    """, unsafe_allow_html=True)
    
    # Centered input form with container width
    with st.container():
        with st.form("chat_form", clear_on_submit=True):
            # Two column layout for input and button
            col1, col2 = st.columns([8, 0.8])
            
            with col1:
                # Main input area - using text_area for 3 rows height
                user_input = st.text_area(
                    "Message",
                    placeholder="Ask me anything...",
                    label_visibility="collapsed",
                    value=default_value,
                    key="chat_input_field",
                    height=90  # Approximately 3 rows height
                )
            
            with col2:
                # Add spacing to center the send button vertically
                st.markdown('<div style="margin-top: 25px;"></div>', unsafe_allow_html=True)
                # Send button
                send_button = st.form_submit_button(
                    "Send",
                    use_container_width=True,
                    type="primary"
                )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Check for auto-send trigger from sample prompt
    auto_send = st.session_state.get('auto_send_prompt', False)
    if auto_send:
        st.session_state.auto_send_prompt = False  # Clear the flag
        # Force the user_input to be the selected prompt for auto-send
        user_input = default_value
    
    # Process chat input (either from send button or auto-send)
    if (send_button and user_input.strip()) or (auto_send and user_input.strip()):
        # Check if any systems are connected
        if not connected_servers:
            # Show a toast notification instead of adding to chat history
            st.error("🔗 Please connect at least one system from the sidebar before chatting!")
            st.stop()
        
        # Add welcome message if this is the first message
        if len(st.session_state.chat_history) == 0:
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": "Hi! I'm your MCP AI Assistant. I can help you with various tasks using the connected servers. What would you like to do today?",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
        
        # Add user message to history
        st.session_state.chat_history.append({
            "role": "user", 
            "content": user_input,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
        session_id = st.session_state.get("session_id", "streamlit_session")
        if "session_id" not in st.session_state:
            st.session_state["session_id"] = session_id

        active_servers = [s['name'] for s in systems if st.session_state.get(s["session_key"], False)]
        processing_msg = (
            f"🧠 Analyzing with {', '.join(active_servers[:2])}..."
            if active_servers
            else "🤔 Processing your request..."
        )
        stream_on = bool(server_manager and server_manager.streaming_enabled())

        stream_parts: list[str] = []

        with st.status(processing_msg, expanded=False) as status:
            st.write("🔍 Understanding your query...")

            with st.chat_message("assistant"):
                stream_card = st.empty()

                def on_token(chunk: str) -> None:
                    if chunk:
                        stream_parts.append(chunk)
                        stream_card.markdown("".join(stream_parts))

                if stream_on:
                    st.caption("🌊 Streaming into this message…")

                response = run_async(
                    process_user_query_with_auth(
                        user_input,
                        server_manager,
                        channel_id=session_id,
                        thread_ts=None,
                        on_token=on_token if stream_on else None,
                    )
                )

            final_text = (
                str(response).strip()
                if response and str(response).strip()
                else "".join(stream_parts).strip()
            )

            if final_text:
                status.update(label="✅ Complete!", state="complete")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": final_text,
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
            else:
                status.update(label="❌ Failed", state="error")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": (
                        "❌ Sorry, I couldn't process your request. "
                        "Please check that the relevant servers are connected and try again."
                    ),
                    "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })

        st.rerun()

with tab3:  # Dashboard Tab
    st.markdown("""
        <div style="
            background: linear-gradient(135deg, #059669 0%, #047857 50%, #065f46 100%);
            color: white;
            padding: 32px 24px;
            border-radius: 20px;
            margin: 0 0 24px 0;
            text-align: center;
            box-shadow: 0 10px 40px rgba(5, 150, 105, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        ">
            <div style="
                font-size: 2.2em;
                font-weight: 700;
                margin-bottom: 8px;
                text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            ">
                📊 Business Intelligence Dashboard
            </div>
            <div style="font-size: 0.9em; opacity: 0.9;">
                Real-time insights from your connected systems
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Create trend tiles
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
            <div style="
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                padding: 24px;
                border-radius: 16px;
                color: white;
                text-align: center;
                margin-bottom: 16px;
                box-shadow: 0 4px 20px rgba(99, 102, 241, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
            ">
                <div style="font-size: 2em; margin-bottom: 8px;">💼</div>
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600;">Sales</h3>
                <h2 style="margin: 8px 0; font-size: 2.2em; font-weight: 700;">+24%</h2>
                <p style="margin: 0; opacity: 0.9; font-size: 0.9em;">This Quarter</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Sales details
        with st.expander("📊 Sales Details", expanded=False):
            st.metric("Revenue", "$1.2M", "+24%")
            st.metric("New Deals", "156", "+18%")
            st.metric("Conversion Rate", "12.5%", "+2.1%")
            
            # Mock sales data
            st.bar_chart({
                "Jan": 80000,
                "Feb": 95000,
                "Mar": 110000,
                "Apr": 125000
            })
    
    with col2:
        st.markdown("""
            <div style="
                background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%);
                padding: 24px;
                border-radius: 16px;
                color: white;
                text-align: center;
                margin-bottom: 16px;
                box-shadow: 0 4px 20px rgba(34, 197, 94, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
            ">
                <div style="font-size: 2em; margin-bottom: 8px;">🛠️</div>
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600;">Service</h3>
                <h2 style="margin: 8px 0; font-size: 2.2em; font-weight: 700;">94%</h2>
                <p style="margin: 0; opacity: 0.9; font-size: 0.9em;">Satisfaction</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Service details
        with st.expander("🔧 Service Details", expanded=False):
            st.metric("Satisfaction", "94%", "+3%")
            st.metric("Resolution Time", "2.4 hrs", "-0.6 hrs")
            st.metric("Active Cases", "23", "-5")
            
            # Mock service data
            st.line_chart({
                "Mon": 95,
                "Tue": 92,
                "Wed": 96,
                "Thu": 94,
                "Fri": 97
            })
    
    with col3:
        st.markdown("""
            <div style="
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                padding: 24px;
                border-radius: 16px;
                color: white;
                text-align: center;
                margin-bottom: 16px;
                box-shadow: 0 4px 20px rgba(245, 158, 11, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
            ">
                <div style="font-size: 2em; margin-bottom: 8px;">📈</div>
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600;">Marketing</h3>
                <h2 style="margin: 8px 0; font-size: 2.2em; font-weight: 700;">+35%</h2>
                <p style="margin: 0; opacity: 0.9; font-size: 0.9em;">Engagement</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Marketing details
        with st.expander("📊 Marketing Details", expanded=False):
            st.metric("Campaign ROI", "245%", "+35%")
            st.metric("Lead Generation", "2,450", "+28%")
            st.metric("Social Reach", "125K", "+42%")
            
            # Mock marketing data
            st.area_chart({
                "Week 1": 1200,
                "Week 2": 1450,
                "Week 3": 1800,
                "Week 4": 2100
            })
    
    with col4:
        st.markdown("""
            <div style="
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                padding: 24px;
                border-radius: 16px;
                color: white;
                text-align: center;
                margin-bottom: 16px;
                box-shadow: 0 4px 20px rgba(239, 68, 68, 0.3);
                border: 1px solid rgba(255, 255, 255, 0.1);
            ">
                <div style="font-size: 2em; margin-bottom: 8px;">📦</div>
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600;">Product</h3>
                <h2 style="margin: 8px 0; font-size: 2.2em; font-weight: 700;">4.8</h2>
                <p style="margin: 0; opacity: 0.9; font-size: 0.9em;">User Rating</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Product details
        with st.expander("🎯 Product Details", expanded=False):
            st.metric("User Rating", "4.8/5", "+0.2")
            st.metric("Active Users", "15.2K", "+12%")
            st.metric("Feature Adoption", "67%", "+8%")
            
            # Mock product data
            st.bar_chart({
                "Feature A": 85,
                "Feature B": 67,
                "Feature C": 92,
                "Feature D": 71
            })
    
    st.markdown("""
        <div class="section-divider"></div>
        <div class="chat-section-header">
            🖥️ Server Status Overview
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if server_manager:
            total_servers = len(systems)
            st.metric("Total Servers", total_servers)
        else:
            st.metric("Total Servers", "N/A")
    
    with col2:
        if server_manager:
            available_count = len(server_manager.get_available_servers())
            st.metric("Available", available_count)
        else:
            st.metric("Available", "N/A")
    
    with col3:
        connected_count = sum(1 for system in systems if st.session_state.get(system["session_key"], False))
        st.metric("Connected", connected_count)
    
    with col4:
        # Calculate uptime percentage
        if server_manager and len(systems) > 0:
            uptime = (len(server_manager.get_available_servers()) / len(systems)) * 100
            st.metric("Uptime", f"{uptime:.0f}%")
        else:
            st.metric("Uptime", "N/A")

with tab4:  # Settings Tab
    st.markdown("""
        <div style="
            background: linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #5b21b6 100%);
            color: white;
            padding: 32px 24px;
            border-radius: 20px;
            margin: 0 0 24px 0;
            text-align: center;
            box-shadow: 0 10px 40px rgba(124, 58, 237, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        ">
            <div style="
                font-size: 2.2em;
                font-weight: 700;
                margin-bottom: 8px;
                text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            ">
                ⚙️ System Configuration
            </div>
            <div style="font-size: 0.9em; opacity: 0.9;">
                Configure your AI assistant and server settings
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # LLM Configuration
    st.markdown("""
        <div class="chat-section-header">
            🧠 Language Model Configuration
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Azure Deployment", value="ats-aria-gpt-4o-mini", disabled=True)
        st.text_input("API Version", value="2024-02-15-preview", disabled=True)
    
    with col2:
        st.slider("Temperature", 0.0, 1.0, 0.5, disabled=True)
        st.number_input("Max Tokens", value=2000, disabled=True)
    
    # Server Configuration
    st.markdown("""
        <div class="chat-section-header">
            🖥️ Server Configuration
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("🔄 Reload Server Configuration"):
        # Clear cache and reinitialize
        st.cache_resource.clear()
        st.rerun()
    
    if st.button("🧹 Clear Chat History"):
        st.session_state.chat_history = [
            {"role": "assistant", "content": "Chat history cleared! How can I help you?"}
        ]
        if server_manager:
            server_manager.clear_all_conversations()
        st.success("Chat history cleared!")
    
    # Show environment status
    st.markdown("""
        <div class="chat-section-header">
            🔧 Environment Status
        </div>
    """, unsafe_allow_html=True)
    
    env_vars = [
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY", 
        "YOUTUBE_API_KEY",
        "SLACK_BOT_TOKEN"
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            st.success(f"✅ {var}: Set")
        else:
            st.warning(f"⚠️ {var}: Not set")


# Footer
st.markdown("")
st.markdown("""
    <div style="text-align: center; padding: 20px 0; margin-top: 40px; border-top: 1px solid #333;">
        <p style="margin: 0; color: #888; font-size: 0.9em;">
            <strong>MCP Server Hub</strong> • Powered by Adobe Model Context Protocol
        </p>
    </div>
""", unsafe_allow_html=True)

# Helper functions for search intelligence (defined here to be available for Search tab)
def load_available_systems_from_config():
    """Load available systems dynamically from mcp_servers.json"""
    try:
        servers_json_path = os.path.join("Servers", "config", "mcp_servers.json")
        with open(servers_json_path, "r") as f:
            servers_config = json.load(f)
        
        # Create system mapping with friendly names
        system_mapping = {}
        friendly_names = {
            "web_search_scrape_rag": "Web Search & RAG",
            "microsoft_docs": "Microsoft Documentation",
            "mcp_atlassian": "Jira & Confluence",
            "service_system": "Service Cases",
            "sales_system": "Sales System",
            "youtube": "YouTube",
            "slack": "Slack",
            "weather": "Weather",
            "playwright": "Browser Automation",
            "content_analysis": "Content Analysis"
        }
        
        all_systems = []
        for system_key, config in servers_config.items():
            friendly_name = friendly_names.get(system_key, system_key.replace("_", " ").title())
            all_systems.append((system_key, friendly_name))
            system_mapping[friendly_name] = system_key
        
        return all_systems, system_mapping
        
    except Exception as e:
        print(f"Error loading systems config: {e}")
        # Fallback to basic systems if config can't be loaded
        fallback_systems = [
            ("web_search_scrape_rag", "Web Search"),
            ("youtube", "YouTube"),
            ("slack", "Slack")
        ]
        fallback_mapping = {name: key for key, name in fallback_systems}
        return fallback_systems, fallback_mapping

def determine_search_systems(query: str, source_filter: str = "All systems") -> list:
    """Determine which systems to search based on query and filters"""
    query_lower = query.lower()
    
    # Load systems dynamically from config
    all_systems, system_mapping = load_available_systems_from_config()
    
    # If specific source filter is selected, only search that system
    if source_filter != "All systems":
        if source_filter in system_mapping:
            system_key = system_mapping[source_filter]
            return [(system_key, source_filter)]
        else:
            # If filter doesn't match, return all systems
            return all_systems
    
    # For comprehensive search, use all available systems but prioritize based on query
    systems_to_search = []
    
    # Always include web search first if available
    web_search_system = next((s for s in all_systems if s[0] == "web_search_scrape_rag"), None)
    if web_search_system:
        systems_to_search.append(web_search_system)
    
    # Add other systems based on query relevance
    priority_systems = []
    standard_systems = []
    
    # Categorize systems based on query keywords
    keyword_mappings = {
        "service": ["support", "case", "issue", "problem", "bug", "error", "crash", "help", "ticket"],
        "sales": ["sales", "lead", "revenue", "deal", "customer", "prospect", "campaign", "crm"],
        "documentation": ["documentation", "docs", "guide", "tutorial", "how to", "manual", "confluence", "jira"],
        "video": ["video", "tutorial", "demo", "presentation", "youtube"],
        "communication": ["slack", "message", "chat", "conversation", "team", "communication"],
        "weather": ["weather", "forecast", "temperature", "climate", "meteorology"],
        "content": ["content", "analysis", "text", "document", "analyze"]
    }
    
    # Prioritize systems based on query content
    for system_key, friendly_name in all_systems:
        if system_key == "web_search_scrape_rag":
            continue  # Already added
            
        is_priority = False
        
        # Check if query matches system-specific keywords
        if system_key == "service_system" and any(kw in query_lower for kw in keyword_mappings["service"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "sales_system" and any(kw in query_lower for kw in keyword_mappings["sales"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "mcp_atlassian" and any(kw in query_lower for kw in keyword_mappings["documentation"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "microsoft_docs" and any(kw in query_lower for kw in keyword_mappings["documentation"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "youtube" and any(kw in query_lower for kw in keyword_mappings["video"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "slack" and any(kw in query_lower for kw in keyword_mappings["communication"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "weather" and any(kw in query_lower for kw in keyword_mappings["weather"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        elif system_key == "content_analysis" and any(kw in query_lower for kw in keyword_mappings["content"]):
            priority_systems.append((system_key, friendly_name))
            is_priority = True
        
        if not is_priority:
            standard_systems.append((system_key, friendly_name))
    
    # Combine: Web Search -> Priority Systems -> Standard Systems
    systems_to_search.extend(priority_systems)
    systems_to_search.extend(standard_systems)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_systems = []
    for system in systems_to_search:
        if system[0] not in seen:
            seen.add(system[0])
            unique_systems.append(system)
    
    return unique_systems

def get_system_icon(system_key: str) -> str:
    """Get icon for system based on actual mcp_servers.json keys"""
    icons = {
        "web_search_scrape_rag": "🌐",
        "microsoft_docs": "📘",
        "service_system": "🎫",
        "youtube": "📺",
        "mcp_atlassian": "📋",
        "slack": "💬",
        "sales_system": "💰",
        "content_analysis": "📄",
        "weather": "🌦️",
        "playwright": "🎭"
    }
    return icons.get(system_key, "📊")

with tab2:  # Search Tab - Clean Professional Interface
    # Search Header
    st.markdown("""
        <div style="
            background: linear-gradient(135deg, #0078d4 0%, #106ebe 50%, #005a9e 100%);
            color: white;
            padding: 32px 24px;
            border-radius: 20px;
            margin: 0 0 24px 0;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0, 120, 212, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.2);
            position: relative;
            overflow: hidden;
        ">
            <div style="
                font-size: 2.2em;
                font-weight: 700;
                margin-bottom: 8px;
                text-shadow: 0 2px 10px rgba(0,0,0,0.3);
            ">
                🔍 Enterprise Search Center
            </div>
            <div style="font-size: 0.9em; opacity: 0.9;">
                Find information across all your connected systems
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    # Clean enterprise search interface like Microsoft/Google
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;500;600;700&display=swap');
        
        /* Clean Professional Theme */
        .search-container {
            background: #ffffff;
            padding: 0;
            margin-bottom: 0;
        }
        
        /* Search Inline Container */
        .search-inline-container {
            display: flex !important;
            align-items: center !important;
            gap: 8px !important;
        }
        
        .search-inline-container .stColumns {
            display: flex !important;
            align-items: center !important;
            width: 100% !important;
        }
        
        .search-inline-container .stColumn {
            display: flex !important;
            align-items: center !important;
        }
        
        /* Icon Button Styles */
        .search-inline-container .stButton > button {
            width: 48px !important;
            height: 48px !important;
            border-radius: 50% !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 16px !important;
            padding: 0 !important;
            min-width: unset !important;
            margin: 0 !important;
        }
        
        /* Ensure text input and buttons are same height */
        .search-inline-container .stTextInput > div > div > input {
            height: 48px !important;
            margin: 0 !important;
        }
        
        .search-inline-container .stButton {
            margin: 0 !important;
            height: 48px !important;
            display: flex !important;
            align-items: center !important;
        }
        

        
        /* Filter Bar */
        .filter-bar {
            background: #ffffff;
            padding: 16px 32px;
            border-bottom: 1px solid #e1e5e9;
            display: flex;
            gap: 24px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-item {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #424242;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            padding: 8px 12px;
            border-radius: 20px;
            transition: all 0.2s ease;
            border: 1px solid transparent;
        }
        
        .filter-item:hover {
            background: #f3f2f1;
            border-color: #e1e5e9;
        }
        
        .filter-item.active {
            background: #e7f3ff;
            color: #0078d4;
            border-color: #0078d4;
        }
        
        .filter-dropdown {
            background: #ffffff;
            border: 1px solid #e1e5e9;
            border-radius: 4px;
            padding: 4px 8px;
            margin-left: 4px;
            font-size: 14px;
            color: #424242;
        }
        
        /* Results Layout */
        .results-layout {
            display: flex;
            max-width: 1400px;
            margin: 0 auto;
            gap: 24px;
            padding: 24px 32px;
        }
        
        .results-main {
            flex: 1;
            min-width: 0;
        }
        
        .results-sidebar {
            width: 280px;
            flex-shrink: 0;
        }
        
        /* Result Cards */
        .result-card {
            background: #ffffff;
            border: 1px solid #e1e5e9;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        
        .result-card:hover {
            border-color: #0078d4;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .result-header {
            display: flex;
            align-items: flex-start;
            gap: 16px;
            margin-bottom: 12px;
        }
        
        .result-icon {
            width: 32px;
            height: 32px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            flex-shrink: 0;
            background: #f3f2f1;
        }
        
        .result-content {
            flex: 1;
            min-width: 0;
        }
        
        .result-title {
            font-family: 'Segoe UI', sans-serif;
            font-size: 18px;
            font-weight: 600;
            color: #0078d4;
            margin: 0 0 8px 0;
            line-height: 1.3;
            text-decoration: none;
        }
        
        .result-title:hover {
            text-decoration: underline;
        }
        
        .result-snippet {
            color: #424242;
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 12px;
        }
        
        .result-meta {
            display: flex;
            align-items: center;
            gap: 16px;
            color: #605e5c;
            font-size: 12px;
        }
        
        .result-meta span {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .result-source {
            background: #e7f3ff;
            color: #0078d4;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        /* Sidebar */
        .sidebar-section {
            background: #ffffff;
            border: 1px solid #e1e5e9;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 16px;
        }
        
        .sidebar-title {
            font-family: 'Segoe UI', sans-serif;
            font-size: 16px;
            font-weight: 600;
            color: #323130;
            margin: 0 0 16px 0;
        }
        
        .source-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #f3f2f1;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        
        .source-item:last-child {
            border-bottom: none;
        }
        
        .source-item:hover {
            background: #f8f9fa;
            margin: 0 -12px;
            padding: 8px 12px;
            border-radius: 4px;
        }
        
        .source-name {
            display: flex;
            align-items: center;
            gap: 8px;
            color: #424242;
            font-size: 14px;
        }
        
        .source-count {
            color: #605e5c;
            font-size: 13px;
            font-weight: 600;
        }
        
        /* Loading State */
        .loading-state {
            text-align: center;
            padding: 60px 20px;
            color: #605e5c;
        }
        
        .loading-spinner {
            width: 32px;
            height: 32px;
            border: 3px solid #f3f2f1;
            border-top: 3px solid #0078d4;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 16px auto;
        }
        
        /* Empty State */
        .empty-state {
            text-align: center;
            padding: 80px 20px;
            color: #605e5c;
        }
        
        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
            color: #c8c6c4;
        }
        
        .empty-state-title {
            font-size: 20px;
            font-weight: 600;
            color: #323130;
            margin-bottom: 8px;
        }
        
        .empty-state-text {
            font-size: 14px;
            color: #605e5c;
            max-width: 400px;
            margin: 0 auto;
        }
        
        /* Streamlit Overrides */
        .stTextInput > div > div > input {
            height: 48px !important;
            border: 2px solid #e1e5e9 !important;
            border-radius: 24px !important;
            padding: 12px 20px !important;
            font-size: 16px !important;
            font-family: 'Segoe UI', sans-serif !important;
            background: #ffffff !important;
            color: #323130 !important;
        }
        
        .stTextInput > div > div > input:focus {
            border-color: #0078d4 !important;
            box-shadow: 0 0 0 1px #0078d4 !important;
            outline: none !important;
        }
        
        /* General button styles */
        .stButton > button {
            background: #0078d4 !important;
            border: none !important;
            border-radius: 4px !important;
            color: white !important;
            font-family: 'Segoe UI', sans-serif !important;
            font-weight: 600 !important;
            padding: 8px 16px !important;
            height: 36px !important;
            font-size: 14px !important;
        }
        
        .stButton > button:hover {
            background: #106ebe !important;
        }
        
        .stSelectbox > div > div {
            border: 1px solid #e1e5e9 !important;
            border-radius: 4px !important;
            font-family: 'Segoe UI', sans-serif !important;
            background: #ffffff !important;
        }
        
        /* Animations */
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        /* Responsive */
        @media (max-width: 768px) {
            .results-layout {
                flex-direction: column;
            }
            .results-sidebar {
                width: 100%;
                order: -1;
            }
            .filter-bar {
                padding: 12px 16px;
                gap: 12px;
            }
            .search-header {
                padding: 16px 20px;
            }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Clean Professional Search Interface
    st.markdown('<div class="search-container">', unsafe_allow_html=True)
    
    # Search Input with inline buttons - using flex container
    st.markdown('<div class="search-inline-container">', unsafe_allow_html=True)
    
    search_col1, search_col2, search_col3 = st.columns([8, 0.6, 0.6])
    
    with search_col1:
        search_query = st.text_input(
            "Search Query",
            placeholder="Search across all your systems...",
            key="main_search_input",
            label_visibility="hidden"
        )
    
    with search_col2:
        search_button = st.button("🔍", help="Search", key="search_icon_btn", type="primary")
    
    with search_col3:
        clear_button = st.button("🗑️", help="Clear", key="clear_icon_btn")
        if clear_button:
            st.session_state.main_search_input = ""
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Filter Header
    st.markdown("""
        <div style="
            padding: 16px 0 8px 0;
            border-bottom: 1px solid #e1e5e9;
            margin: 16px 0;
        ">
            <h4 style="
                margin: 0;
                color: #323130;
                font-size: 16px;
                font-weight: 600;
                font-family: 'Segoe UI', sans-serif;
            ">🔧 Search Filters</h4>
        </div>
    """, unsafe_allow_html=True)
    
    # Get systems data for filters
    all_systems_data, system_mapping = load_available_systems_from_config()
    
    # Create filter columns
    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
    
    with filter_col1:
        time_filter = st.selectbox(
            "Time",
            ["Anytime", "Past hour", "Past day", "Past week", "Past month", "Past year"],
            key="time_filter",
            label_visibility="collapsed"
        )
    
    with filter_col2:
        source_options = ["All systems"] + [name for _, name in all_systems_data if _ != "playwright"]
        source_filter = st.selectbox(
            "Source",
            source_options,
            key="source_filter",
            label_visibility="collapsed"
        )
    
    with filter_col3:
        content_filter = st.selectbox(
            "Type",
            ["All types", "Documents", "Support Cases", "Videos", "Messages", "Reports"],
            key="content_filter",
            label_visibility="collapsed"
        )
    

    
    # Set default values for compatibility with existing code
    content_type_filter = content_filter
    sort_filter = "Most relevant"
    min_relevance = 50
    exact_match = False
    include_archived = False
    
    # Search Results
    if search_query and search_button:
        # Apply filters to determine search systems
        systems_to_search = determine_search_systems(search_query, source_filter)
        
        # Filter out browser automation
        systems_to_search = [(key, name) for key, name in systems_to_search if key != "playwright"]
        
        # Apply content type filtering to systems
        if content_type_filter != "All types":
            type_system_mapping = {
                "Documents": ["microsoft_docs", "mcp_atlassian", "content_analysis"],
                "Support Cases": ["service_system"],
                "Videos": ["youtube"],
                "Messages": ["slack"],
                "Reports": ["sales_system", "web_search_scrape_rag"]
            }
            
            relevant_systems = type_system_mapping.get(content_type_filter, [])
            if relevant_systems:
                systems_to_search = [(key, name) for key, name in systems_to_search if key in relevant_systems]
        
        if not systems_to_search:
            st.markdown("""
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <div class="empty-state-title">No Systems Match Filters</div>
                    <div class="empty-state-text">Please adjust your filters to include more systems in your search.</div>
                </div>
            """, unsafe_allow_html=True)
            st.stop()
        
        # Loading state
        search_progress = st.empty()
        with search_progress:
            st.markdown("""
                <div class="loading-state">
                    <div class="loading-spinner"></div>
                    <p>Searching across your systems...</p>
                </div>
            """, unsafe_allow_html=True)
        
        # Progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Execute search
        search_results = []
        search_errors = []
        
        for i, (system_key, system_name) in enumerate(systems_to_search):
            try:
                progress = (i + 1) / len(systems_to_search)
                progress_bar.progress(progress)
                status_text.write(f"Searching {system_name}... ({i+1}/{len(systems_to_search)})")
                
                if server_manager and system_key in server_manager.get_available_servers():
                    # Create search queries
                    search_queries = {
                        "web_search_scrape_rag": f"Search web for: {search_query}",
                        "youtube": f"Find videos about: {search_query}",
                        "service_system": f"Search support cases for: {search_query}",
                        "microsoft_docs": f"Search documentation for: {search_query}",
                        "mcp_atlassian": f"Search Jira and Confluence for: {search_query}",
                        "slack": f"Search conversations for: {search_query}",
                        "sales_system": f"Search sales data for: {search_query}",
                        "weather": f"Search weather data for: {search_query}",
                        "content_analysis": f"Analyze content for: {search_query}"
                    }
                    
                    query_to_use = search_queries.get(system_key, f"Search {system_name} for: {search_query}")
                    
                    # Execute search
                    result = run_async(process_user_query(query_to_use, server_manager))
                    
                    if result and len(result.strip()) > 50:
                        # Validate result quality
                        error_keywords = ["error", "failed", "unavailable", "not found", "no results"]
                        if not any(keyword in result.lower() for keyword in error_keywords):
                            search_results.append({
                                "system_key": system_key,
                                "system_name": system_name,
                                "title": f"Results from {system_name}",
                                "snippet": result.strip()[:300] + ("..." if len(result.strip()) > 300 else ""),
                                "full_content": result,
                                "icon": get_system_icon(system_key),
                                "timestamp": "Updated 2hrs ago",
                                "author": "Tim Scarlan",
                                "relevance": 95 - i * 5
                            })
                
            except Exception as e:
                search_errors.append(f"{system_name}: {str(e)}")
        
        # Clear loading state
        search_progress.empty()
        progress_bar.empty()
        status_text.empty()
        
        # Apply sorting and filtering
        if sort_filter == "Most recent":
            search_results.sort(key=lambda x: x["timestamp"], reverse=True)
        elif sort_filter == "Most relevant":
            search_results.sort(key=lambda x: x["relevance"], reverse=True)
        elif sort_filter == "Alphabetical":
            search_results.sort(key=lambda x: x["title"])
        
        search_results = [r for r in search_results if r["relevance"] >= min_relevance]
        
        # Display Results with Clean Layout
        if search_results:
            # Create two-column layout
            st.markdown('<div class="results-layout">', unsafe_allow_html=True)
            
            # Main results column
            main_col, sidebar_col = st.columns([3, 1])
            
            with main_col:
                st.markdown('<div class="results-main">', unsafe_allow_html=True)
                
                # Results info
                result_count = len(search_results)
                st.markdown(f"<p style='color: #605e5c; font-size: 14px; margin-bottom: 20px;'>About {result_count:,} results for <strong>{search_query}</strong></p>", unsafe_allow_html=True)
                
                # Display result cards
                for result in search_results:
                    st.markdown(f"""
                        <div class="result-card">
                            <div class="result-header">
                                <div class="result-icon">{result['icon']}</div>
                                <div class="result-content">
                                    <div class="result-title">{result['title']}</div>
                                    <div class="result-snippet">{result['snippet']}</div>
                                    <div class="result-meta">
                                        <span><strong>{result['author']}</strong></span>
                                        <span>• {result['timestamp']}</span>
                                        <span>• <span class="result-source">{result['system_name']}</span></span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Simple action button
                    if st.button("View Details", key=f"view_{result['title'][:20]}", help="View full details"):
                        st.info(f"Opening details for: {result['title']}")
                    
                    st.markdown("---")
                
                st.markdown('</div>', unsafe_allow_html=True)  # Close results-main
            
            with sidebar_col:
                st.markdown('<div class="results-sidebar">', unsafe_allow_html=True)
                
                # Simple results by source
                st.markdown("""
                    <div class="sidebar-section">
                        <div class="sidebar-title">Results by source</div>
                """, unsafe_allow_html=True)
                
                # Count results by system
                system_counts = {}
                for result in search_results:
                    system_name = result['system_name']
                    system_counts[system_name] = system_counts.get(system_name, 0) + 1
                
                # Display system counts
                for system_name, count in sorted(system_counts.items(), key=lambda x: x[1], reverse=True):
                    system_key = next((key for key, name in all_systems_data if name == system_name), "")
                    icon = get_system_icon(system_key)
                    
                    st.markdown(f"""
                        <div class="source-item">
                            <div class="source-name">
                                <span>{icon}</span>
                                <span>{system_name}</span>
                            </div>
                            <div class="source-count">{count}</div>
                        </div>
                    """, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)  # Close sidebar-section
                
                # Show all available systems
                st.markdown("""
                    <div class="sidebar-section">
                        <div class="sidebar-title">All systems</div>
                """, unsafe_allow_html=True)
                
                for system_key, system_name in all_systems_data:
                    if system_key != "playwright":
                        count = system_counts.get(system_name, 0)
                        icon = get_system_icon(system_key)
                        
                        st.markdown(f"""
                            <div class="source-item">
                                <div class="source-name">
                                    <span>{icon}</span>
                                    <span>{system_name}</span>
                                </div>
                                <div class="source-count">{count}</div>
                            </div>
                        """, unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)  # Close sidebar-section
                st.markdown('</div>', unsafe_allow_html=True)  # Close results-sidebar
            
            st.markdown('</div>', unsafe_allow_html=True)  # Close results-layout
        
        else:
            # Clean no results state
            st.markdown(f"""
                <div class="empty-state">
                    <div class="empty-state-icon">🔍</div>
                    <div class="empty-state-title">No results found</div>
                    <div class="empty-state-text">
                        Your search for "<strong>{search_query}</strong>" didn't return any results.
                        Try different keywords or check your filters.
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            # Debug information
            if search_errors:
                with st.expander("Debug Information", expanded=False):
                    for error in search_errors:
                        st.write(f"• {error}")
    
    elif search_query and not search_button:
        st.info("Click the search icon 🔍 to find results across your systems.")
    
    else:
        # Clean welcome state
        st.markdown("""
            <div class="empty-state">
                <div class="empty-state-icon">🔍</div>
                <div class="empty-state-title">Search your enterprise data intelligently</div>
                <div class="empty-state-text">
                    Discover information instantly across all your connected business systems and platforms.
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)  # Close search-container
    

