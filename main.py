"""
Verna AI — single orchestrator entry for the full stack (MCP + Streamlit + API clients).

Run locally:  python main.py
Docker/Azure: supervisord runs this file (see deploy/azure/supervisord.conf).
Do not use `streamlit run ...` as the primary production entry; main.py starts Streamlit as a child process.
"""
import asyncio
import sys
import os
import subprocess
import signal
import logging
import time
import json
from pathlib import Path
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Add parent directory to path for ServerManager import
sys.path.append(os.path.dirname(__file__))

# Fix Windows asyncio subprocess issue
if sys.platform == "win32":
    # Set Windows-specific event loop policy
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Load environment variables
load_dotenv()

# Configure logging with UTF-8 encoding to handle emojis on Windows
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('clients_startup.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class VernaMasterManager:
    """Manages the startup and coordination of both MCP servers and client applications"""
    
    def __init__(self):
        self.mcp_processes: Dict[str, subprocess.Popen] = {}
        self.client_processes: Dict[str, subprocess.Popen] = {}
        streamlit_host = os.environ.get("STREAMLIT_SERVER_ADDRESS", "localhost")

        # Load MCP server configurations
        self.mcp_configs = self._load_mcp_configs()
        # Client configurations
        self.client_configs = {
            # Chrome Extension Client - FastAPI server with Chrome extension support
            "chrome_extension_client": {
                "script": "Clients/chrome_extension_client.py", 
                "description": "Chrome Extension Client",
                "port": 8001,
                "startup_delay": 5  # Start after MCP servers
            },
            # Slack Listener - Slack bot integration
            "slack_listener": {
                "script": "Clients/slack_listener.py",
                "description": "Slack Bot Integration",
                "port": None,
                "startup_delay": 6,  # Start after MCP servers
                "optional": True,
                "required_env_vars": [
                    "SLACK_BOT_TOKEN",
                    "SLACK_APP_TOKEN",
                    "SLACK_TEAM_ID",
                    "SLACK_CHANNEL_IDS",
                ],
            },
            # Streamlit App - Web UI
            "streamlit_app": {
                "script": "Clients/streamlit_app_ui.py",
                "description": "Streamlit Web UI",
                "port": 8501,
                "startup_delay": 7,  # Start after MCP servers
                "command_prefix": [sys.executable, "-m", "streamlit", "run"],
                "extra_args": [
                    "--server.port=8501",
                    f"--server.address={streamlit_host}",
                    "--browser.gatherUsageStats=false",
                ],
            }
            # Note: terminal_chat_client and ms_teams_listener are excluded as requested
        }
    
    def _load_mcp_configs(self) -> dict:
        """Load MCP server configurations"""
        config_path = os.path.join("Servers", "config", "mcp_servers.json")
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Handle both flat structure and nested mcpServers structure
                if 'mcpServers' in config_data:
                    return config_data['mcpServers']
                else:
                    return config_data
        except Exception as e:
            logger.error(f"Failed to load MCP server configs: {e}")
            return {}
    
    async def start_mcp_servers(self) -> tuple[int, int]:
        """Start all MCP servers first"""
        logger.info("="*80)
        logger.info("🚀 PHASE 1: Starting MCP Servers")
        logger.info("="*80)
        
        success_count = 0
        total_count = len(self.mcp_configs)
        
        logger.info(f"📋 Found {total_count} MCP server configurations")
        
        for server_name, config in self.mcp_configs.items():
            logger.info(f"\n🔄 [{success_count+1}/{total_count}] Processing: {server_name}")
            if await self._start_mcp_server(server_name, config):
                success_count += 1
                logger.info(f"   ✅ {server_name} started successfully")
            else:
                logger.error(f"   ❌ {server_name} failed to start")
            await asyncio.sleep(1)  # Small delay between server starts
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 MCP SERVER STARTUP SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"✅ Successful: {success_count}/{total_count}")
        logger.info(f"❌ Failed: {total_count - success_count}/{total_count}")
        
        # Give servers time to fully initialize
        if success_count > 0:
            logger.info(f"\n⏳ Waiting 5 seconds for MCP servers to fully initialize...")
            await asyncio.sleep(5)
            
            # Test ServerManager to verify tool loading
            logger.info("\n🧪 Testing ServerManager tool loading...")
            await self._test_server_manager()
        
        return success_count, total_count
    
    async def _test_server_manager(self):
        """Test ServerManager to verify tools are loading correctly"""
        try:
            logger.info("   Initializing ServerManager...")
            from ServerManager import ServerManager
            
            server_manager = ServerManager()
            server_manager.initialize()
            
            # Get available servers
            available_servers = server_manager.get_available_servers()
            logger.info(f"   ✅ ServerManager initialized")
            logger.info(f"   📡 Available servers: {len(available_servers)}")
            for server in available_servers:
                logger.info(f"      - {server}")
            
            # Try to get tools
            logger.info(f"\n   ⏳ Loading tools from all servers (timeout: 10s)...")
            try:
                tools = await asyncio.wait_for(
                    server_manager.get_available_tools(), 
                    timeout=10.0
                )
                
                logger.info(f"   ✅ Successfully loaded {len(tools)} tools")
                
                # Group tools by server
                tool_groups = {}
                for tool in tools:
                    server_prefix = tool.name.split('_')[0] if '_' in tool.name else 'unknown'
                    if server_prefix not in tool_groups:
                        tool_groups[server_prefix] = []
                    tool_groups[server_prefix].append(tool.name)
                
                logger.info(f"\n   📊 Tools by Server:")
                for server, tools_list in sorted(tool_groups.items()):
                    logger.info(f"      {server}: {len(tools_list)} tools")
                    for tool in tools_list[:3]:  # Show first 3 tools from each server
                        logger.info(f"         - {tool}")
                    if len(tools_list) > 3:
                        logger.info(f"         ... and {len(tools_list) - 3} more")
                
                # Test a simple query
                logger.info(f"\n   🧪 Testing simple query: 'test'")
                response = await asyncio.wait_for(
                    server_manager.process_request("test"),
                    timeout=15.0
                )
                if response:
                    logger.info(f"   ✅ Query test successful (response: {len(response)} chars)")
                else:
                    logger.warning(f"   ⚠️  Query returned no response")
                
            except asyncio.TimeoutError:
                logger.error(f"   ❌ Tool loading timed out after 10 seconds")
                logger.error(f"      This usually means one or more servers failed to start properly")
            except Exception as e:
                logger.error(f"   ❌ Tool loading failed: {str(e)}")
            
        except Exception as e:
            logger.error(f"   ❌ ServerManager test failed: {str(e)}")
            import traceback
            logger.error(f"      {traceback.format_exc()}")
    
    async def _start_mcp_server(self, server_name: str, config: dict) -> bool:
        """Start a single MCP server with detailed logging"""
        try:
            # Skip HTTP servers (they don't need to be started separately)
            if config.get('transport') == 'streamable_http':
                logger.info(f"   ⏭️  HTTP server (no process needed): {config.get('url', 'N/A')}")
                return True
            
            # Log configuration details
            port = config.get('env', {}).get('MCP_PORT', 'N/A')
            command_str = config['command']
            logger.info(f"   📝 Configuration:")
            logger.info(f"      Command: {command_str}")
            logger.info(f"      Port: {port}")
            logger.info(f"      Transport: {config.get('transport', 'stdio')}")
            
            # Prepare environment variables
            env = os.environ.copy()
            missing_vars = []
            if 'env' in config:
                logger.info(f"      Environment variables:")
                for key, value in config['env'].items():
                    # Handle environment variable substitution
                    if value.startswith('${') and value.endswith('}'):
                        env_var = value[2:-1]
                        env_value = os.getenv(env_var, '')
                        if not env_value:
                            missing_vars.append(env_var)
                            logger.warning(f"         ⚠️  {key}: ${env_var} not set")
                        else:
                            logger.info(f"         ✓ {key}: set")
                        env[key] = env_value
                    else:
                        env[key] = value
                        logger.info(f"         ✓ {key}: {value}")
            
            if missing_vars:
                logger.warning(f"   ⚠️  Missing environment variables: {', '.join(missing_vars)}")
                logger.warning(f"      Server may fail if these are required")
            
            # Prepare command
            command = [config['command']] + config.get('args', [])
            logger.info(f"   🚀 Launching process...")
            logger.info(f"      Full command: {' '.join(command[:3])}...")
            
            start_time = time.time()
            
            # Start process
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr with stdout
                text=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self.mcp_processes[server_name] = process
            logger.info(f"   ⏳ Process started (PID: {process.pid}), waiting 3s for initialization...")
            
            # Give server time to start and check status
            await asyncio.sleep(3)
            
            elapsed = time.time() - start_time
            
            if process.poll() is None:
                logger.info(f"   ✅ Server is running (startup time: {elapsed:.1f}s)")
                return True
            else:
                # Get error output
                try:
                    output, _ = process.communicate(timeout=1)
                    error_msg = (output or "No output available").strip()
                    if len(error_msg) > 200:
                        error_msg = error_msg[:200] + "..."
                except subprocess.TimeoutExpired:
                    error_msg = "Process terminated immediately"
                
                logger.error(f"   ❌ Server failed to start:")
                logger.error(f"      {error_msg}")
                if server_name in self.mcp_processes:
                    del self.mcp_processes[server_name]
                return False
                
        except FileNotFoundError as e:
            logger.error(f"   ❌ Command not found: {config['command']}")
            logger.error(f"      Make sure {config['command']} is installed and in PATH")
            return False
        except Exception as e:
            logger.error(f"   ❌ Unexpected error: {e}")
            import traceback
            logger.error(f"      {traceback.format_exc()}")
            return False
    
    async def start_all_clients(self) -> tuple[int, int]:
        """Start all configured clients"""
        logger.info("\n" + "="*80)
        logger.info("🚀 PHASE 2: Starting Client Applications")
        logger.info("="*80)
        
        total_count = len(self.client_configs)
        logger.info(f"📋 Found {total_count} client configurations\n")
        
        # Start clients with delays to avoid port conflicts
        startup_tasks = []
        for client_name, config in self.client_configs.items():
            delay = config.get("startup_delay", 0) - 5  # Subtract the 5s we already waited
            task = asyncio.create_task(self._start_client_with_delay(client_name, max(delay, 0)))
            startup_tasks.append(task)
        
        # Wait for all clients to start
        results = await asyncio.gather(*startup_tasks, return_exceptions=True)
        
        # Count successes
        success_count = sum(1 for result in results if result is True)
        
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 CLIENT STARTUP SUMMARY")
        logger.info(f"{'='*80}")
        logger.info(f"✅ Successful: {success_count}/{total_count}")
        logger.info(f"❌ Failed: {total_count - success_count}/{total_count}\n")
        
        return success_count, total_count
    
    async def _start_client_with_delay(self, client_name: str, delay: float) -> bool:
        """Start a client with initial delay"""
        await asyncio.sleep(delay)
        return await self.start_client(client_name)
    
    async def start_client(self, client_name: str) -> bool:
        """Start a single client with detailed logging"""
        if client_name not in self.client_configs:
            logger.error(f"❌ Client '{client_name}' not found in configuration")
            return False
        
        if client_name in self.client_processes:
            logger.warning(f"⚠️  Client '{client_name}' is already running")
            return True
        
        config = self.client_configs[client_name]

        req = config.get("required_env_vars")
        if config.get("optional") and req:
            missing = [k for k in req if not os.getenv(k)]
            if missing:
                logger.info(
                    f"⏭️  Skipping optional client '{client_name}' "
                    f"(unset: {', '.join(missing)})"
                )
                return True
        
        logger.info(f"🔄 Starting: {config['description']}")
        
        try:
            # Prepare command
            if "command_prefix" in config:
                # Special case for streamlit
                command = config["command_prefix"] + [config["script"]] + config.get("extra_args", [])
                logger.info(f"   📝 Type: Streamlit application")
            else:
                # Standard python script execution
                command = [sys.executable, config["script"]]
                logger.info(f"   📝 Type: Python script")
            
            logger.info(f"   📝 Script: {config['script']}")
            if config.get('port'):
                logger.info(f"   📝 Port: {config['port']}")
                logger.info(f"   🌐 URL: http://localhost:{config['port']}")
            
            # Prepare environment
            env = os.environ.copy()
            
            logger.info(f"   🚀 Launching process...")
            start_time = time.time()

            repo_root = os.path.dirname(os.path.abspath(__file__))
            ready_sec = float(os.environ.get("VERNA_CLIENT_READY_SEC", "4"))
            
            # Start process - Don't capture output to allow direct logging to console
            process = subprocess.Popen(
                command,
                env=env,
                cwd=repo_root,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self.client_processes[client_name] = process
            logger.info(
                f"   ⏳ Process started (PID: {process.pid}), "
                f"waiting {ready_sec:.0f}s for initialization..."
            )
            
            # Give client time to start (cold containers need more than 4s)
            await asyncio.sleep(ready_sec)
            
            elapsed = time.time() - start_time
            
            # Check if process is still running
            if process.poll() is None:
                logger.info(f"   ✅ Client is running (startup time: {elapsed:.1f}s)")
                if config.get('port'):
                    logger.info(f"   🌐 Access at: http://localhost:{config['port']}\n")
                return True
            else:
                code = process.poll()
                logger.error(
                    f"   ❌ Client failed to start (exit code: {code})"
                )
                if client_name in self.client_processes:
                    del self.client_processes[client_name]
                return False
                
        except FileNotFoundError as e:
            logger.error(f"   ❌ Command not found: {e}")
            return False
        except Exception as e:
            logger.error(f"   ❌ Unexpected error: {e}")
            import traceback
            logger.error(f"      {traceback.format_exc()}")
            return False
    
    def stop_all(self):
        """Stop all processes - both MCP servers and clients"""
        logger.info("🛑 Stopping all processes...")
        
        # Stop clients first
        logger.info("🛑 Stopping clients...")
        for client_name in list(self.client_processes.keys()):
            self._stop_process(client_name, self.client_processes, "client")
        
        # Then stop MCP servers
        logger.info("🛑 Stopping MCP servers...")
        for server_name in list(self.mcp_processes.keys()):
            self._stop_process(server_name, self.mcp_processes, "MCP server")
        
        logger.info("✅ All processes stopped")
    
    def _stop_process(self, name: str, process_dict: dict, process_type: str = "process"):
        """Stop a single process gracefully"""
        if name not in process_dict:
            return True
        
        process = process_dict[name]
        
        try:
            logger.info(f"🛑 Stopping {process_type} {name} (PID: {process.pid})")
            
            # Graceful shutdown
            process.terminate()
            
            try:
                process.wait(timeout=5)
                logger.info(f"✅ {name} stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️  Force killing {name}")
                process.kill()
                process.wait()
                logger.info(f"✅ {name} force stopped")
            
            del process_dict[name]
            return True
            
        except Exception as e:
            logger.error(f"❌ Error stopping {name}: {e}")
            return False
    
    def print_status(self):
        """Print comprehensive status of both MCP servers and clients"""
        print(f"\n{'='*80}")
        print(f"🤖 VERNA AI ECOSYSTEM STATUS")
        print(f"{'='*80}")
        print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # MCP Servers Status
        print(f"\n📊 MCP SERVERS STATUS:")
        print("-" * 60)
        print(f"  ℹ️  MCP servers are managed by ServerManager's MultiServerMCPClient")
        print(f"  ℹ️  They are spawned on-demand when clients request tools")
        print(f"  ℹ️  Total configured servers: {len(self.mcp_configs)}")
        if self.mcp_configs:
            print(f"\n  Configured servers:")
            for name in list(self.mcp_configs.keys())[:5]:  # Show first 5
                print(f"    - {name}")
            if len(self.mcp_configs) > 5:
                print(f"    ... and {len(self.mcp_configs) - 5} more")
        
        # Client Applications Status
        print(f"\n📱 CLIENT APPLICATIONS STATUS:")
        print("-" * 60)
        if self.client_configs:
            for name, config in self.client_configs.items():
                port = config.get('port')
                port_str = str(port) if port is not None else 'N/A'
                if name in self.client_processes:
                    process = self.client_processes[name]
                    if process.poll() is None:
                        status = "🟢 RUNNING"
                        pid = f"PID: {process.pid}"
                    else:
                        status = "🔴 STOPPED"
                        pid = "PID: N/A"
                        # Remove dead process from tracking
                        del self.client_processes[name]
                else:
                    status = "🔴 NOT STARTED"
                    pid = "PID: N/A"
                print(f"  {name:20} | Port: {port_str:5} | {status:12} | {pid}")
        
        # Access URLs
        print(f"\n🌐 ACCESS URLS:")
        print("-" * 60)
        for client_name, config in self.client_configs.items():
            if config.get('port') and client_name in self.client_processes:
                process = self.client_processes[client_name]
                if process.poll() is None:  # Only show URLs for running processes
                    print(f"  {config['description']:25} | http://localhost:{config['port']}")
        
        # Summary
        running_clients = len([p for p in self.client_processes.values() if p.poll() is None])
        total_clients = len(self.client_configs)
        
        print(f"\n📈 SUMMARY:")
        print("-" * 60)
        print(f"  MCP Servers:    Managed by ServerManager ({len(self.mcp_configs)} configured)")
        print(f"  Client Apps:    {running_clients}/{total_clients} running")
        print(f"  System Status:  {'🟢 READY' if running_clients > 0 else '🔴 ISSUES DETECTED'}")
        
        if running_clients == 0:
            print(f"\n⚠️  WARNING: No client applications running - no access interfaces available!")
        
        print(f"{'='*80}\n")

async def main():
    """Main function to start the complete Verna AI ecosystem"""
    logger.info(
        "ENTRY: main.py — Verna ecosystem orchestrator (%s)",
        os.path.abspath(__file__),
    )
    manager = VernaMasterManager()
    
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal")
        manager.stop_all()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("="*80)
        logger.info("🚀 STARTING VERNA AI COMPLETE ECOSYSTEM")
        logger.info("="*80)
        logger.info("")
        logger.info("This script will:")
        logger.info("   1. Check for port conflicts and clean up if needed")
        logger.info("   2. Initialize ServerManager with MCP client")
        logger.info("   3. Test connection to all configured MCP servers")
        logger.info("   4. Load and verify all available tools")
        logger.info("   5. Start client applications (Chrome, Slack, Streamlit)")
        logger.info("   6. Monitor the ecosystem health")
        logger.info("")
        
        # Pre-flight check: Kill any processes on our ports
        logger.info("="*80)
        logger.info("🔍 PRE-FLIGHT CHECK: Checking for port conflicts")
        logger.info("="*80)
        
        import socket
        import subprocess
        
        def check_and_kill_port(port, description):
            """Check if port is in use and offer to kill it"""
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", port))
                    logger.info(f"   ✅ Port {port} ({description}): Available")
                    return True
                except OSError:
                    logger.warning(f"   ⚠️  Port {port} ({description}): Already in use")

                    if sys.platform != "win32":
                        logger.warning(
                            "      ⚠️  Non-Windows: not attempting to kill the owning process "
                            "(use a clean container or free the port manually)."
                        )
                        return False

                    # Try to kill the process (Windows)
                    try:
                        result = subprocess.run(
                            ["netstat", "-ano"],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )

                        for line in result.stdout.split("\n"):
                            if f":{port}" in line and "LISTENING" in line:
                                parts = line.split()
                                if parts:
                                    pid = parts[-1]
                                    logger.info(f"      🔪 Killing process {pid} on port {port}...")
                                    subprocess.run(
                                        ["taskkill", "/F", "/PID", pid],
                                        capture_output=True,
                                        timeout=3,
                                    )
                                    logger.info(f"      ✅ Port {port} freed")
                                    return True
                    except Exception as e:
                        logger.warning(f"      ⚠️  Could not kill process: {e}")

                    return False
        
        ports_to_check = [
            (8001, "Chrome Extension Client"),
            (8501, "Streamlit UI"),
        ]
        
        for port, desc in ports_to_check:
            check_and_kill_port(port, desc)
        
        logger.info("")
        
        # ============================================================================
        # IMPORTANT: MCP servers are now managed by MultiServerMCPClient
        # ============================================================================
        # The ServerManager's MultiServerMCPClient will spawn and manage MCP server
        # processes automatically. We don't need to pre-start them here.
        # This fixes the "Connection closed" errors caused by duplicate process spawning.
        # ============================================================================
        
        logger.info("="*80)
        logger.info("ℹ️  MCP SERVER ARCHITECTURE")
        logger.info("="*80)
        logger.info("   MCP servers are managed by ServerManager's MultiServerMCPClient")
        logger.info("   Servers spawn on-demand when clients request tools")
        logger.info("   No pre-starting needed - prevents duplicate process issues")
        logger.info("="*80)
        
        # Wait a moment for initialization
        await asyncio.sleep(2)
        
        # Test ServerManager initialization
        logger.info("\n🧪 Testing ServerManager initialization...")
        try:
            from ServerManager import ServerManager
            
            logger.info("   📦 Initializing ServerManager...")
            server_manager = ServerManager()
            server_manager.initialize()
            
            # Get available servers
            available_servers = server_manager.get_available_servers()
            logger.info(f"   ✅ ServerManager initialized successfully")
            logger.info(f"   📡 Available servers: {len(available_servers)}")
            logger.info("")
            for i, server in enumerate(available_servers, 1):
                logger.info(f"      {i}. {server}")
            
            # Try to get tools
            logger.info(f"\n   ⏳ Loading tools from all servers (timeout: 30s)...")
            logger.info(f"   💡 This may take a while as servers start up...")
            logger.info("")
            
            try:
                tools = await asyncio.wait_for(
                    server_manager.get_available_tools(), 
                    timeout=30.0  # Increased timeout
                )
                
                logger.info(f"   ✅ Successfully loaded {len(tools)} tools!")
                logger.info("")
                
                # Group tools by server
                tool_groups = {}
                for tool in tools:
                    # Extract server prefix from tool name
                    parts = tool.name.split('_')
                    server_prefix = parts[0] if parts else 'unknown'
                    
                    if server_prefix not in tool_groups:
                        tool_groups[server_prefix] = []
                    tool_groups[server_prefix].append(tool.name)
                
                logger.info(f"   📊 Tools grouped by server:")
                logger.info("   " + "=" * 76)
                for server, tools_list in sorted(tool_groups.items()):
                    logger.info(f"   📦 {server.upper()} ({len(tools_list)} tools)")
                    logger.info("   " + "-" * 76)
                    for tool in tools_list[:5]:  # Show first 5 tools from each server
                        logger.info(f"      • {tool}")
                    if len(tools_list) > 5:
                        logger.info(f"      ... and {len(tools_list) - 5} more")
                    logger.info("")
                
                logger.info("   " + "=" * 76)
                logger.info("   🎉 All servers and tools loaded successfully!")
                logger.info("")
                
            except asyncio.TimeoutError:
                logger.error(f"   ❌ Tool loading timed out after 30 seconds")
                logger.error(f"   💡 This usually means one or more servers failed to start")
                logger.error("")
                logger.error(f"   Possible causes:")
                logger.error(f"      • Missing system dependencies (uv, npx, docker)")
                logger.error(f"      • Missing environment variables (API keys)")
                logger.error(f"      • Server code has syntax errors or bugs")
                logger.error(f"      • Port conflicts")
                logger.error(f"      • Network connectivity issues")
                logger.error("")
                
                # Try to get HTTP tools only
                logger.info("   🔄 Attempting to load HTTP tools only...")
                try:
                    http_tools = await server_manager._get_http_agent_tools()
                    if http_tools:
                        logger.info(f"   ✅ HTTP tools available: {len(http_tools)}")
                        for tool in http_tools:
                            logger.info(f"      • {tool.name}")
                except Exception as e2:
                    logger.error(f"   ❌ Failed to get HTTP tools: {e2}")
                    
            except Exception as e:
                logger.error(f"   ❌ Tool loading failed: {str(e)}")
                logger.error(f"   Error type: {type(e).__name__}")
                logger.error("")
                
                # Check for specific error types
                if "Connection closed" in str(e):
                    logger.error("   💡 'Connection closed' error detected!")
                    logger.error("   This usually means:")
                    logger.error("      • The server process started but crashed immediately")
                    logger.error("      • Missing dependencies in the server code")
                    logger.error("      • Environment variables not set correctly")
                    logger.error("      • Syntax errors in server code")
                    logger.error("")
                
                if "TaskGroup" in str(e) or "unhandled errors" in str(e):
                    logger.error("   🚨 TaskGroup error - multiple servers failed!")
                    logger.error("")
                
                # Show partial traceback
                import traceback
                logger.error("   📋 Error details:")
                error_lines = traceback.format_exc().split('\n')
                for line in error_lines[-10:]:  # Show last 10 lines
                    if line.strip():
                        logger.error(f"      {line}")
            
        except Exception as e:
            logger.error(f"   ❌ ServerManager test failed: {str(e)}")
            import traceback
            logger.error("")
            logger.error("   📋 Full traceback:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    logger.error(f"      {line}")
        
        # Test individual server if tool loading failed
        if 'tools' not in locals() or (isinstance(tools, list) and len(tools) < 5):
            logger.info("\n" + "="*80)
            logger.info("🔍 TESTING INDIVIDUAL SERVER STARTUP")
            logger.info("="*80)
            logger.info("💡 Since tool loading had issues, testing a simple server directly...")
            logger.info("")
            
            try:
                import subprocess
                # Test the weather server as it's simple and has minimal dependencies
                cmd = [
                    "mcp",
                    "run",
                    "Servers/weather/weather_analysis_mcp.py",
                ]
                
                logger.info(f"   Testing: weather server")
                logger.info(f"   Command: {' '.join(cmd[:5])}...")
                logger.info("   ⏳ Starting server (will test for 5 seconds)...")
                
                env = os.environ.copy()
                env.update({
                    "AZURE_OPENAI_API_KEY": os.getenv("AZURE_OPENAI_API_KEY", ""),
                    "AZURE_OPENAI_ENDPOINT": os.getenv("AZURE_OPENAI_ENDPOINT", ""),
                    "AZURE_OPENAI_DEPLOYMENT": os.getenv("AZURE_OPENAI_DEPLOYMENT", ""),
                    "MCP_HOST": "127.0.0.1",
                    "MCP_PORT": "8001"
                })
                
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                )
                
                # Wait a bit for server to start
                await asyncio.sleep(5)
                
                # Check if still running
                if process.poll() is None:
                    logger.info("   ✅ Weather server is running!")
                    logger.info("   💡 This means uv and server code work - issue is likely with MCP client connection")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                else:
                    # Get error output
                    try:
                        stdout, stderr = process.communicate(timeout=1)
                        logger.error("   ❌ Weather server exited immediately")
                        if stderr and len(stderr.strip()) > 0:
                            logger.error("   Error output:")
                            for line in stderr.split('\n')[:20]:  # Show first 20 lines
                                if line.strip():
                                    logger.error(f"      {line}")
                        elif stdout and len(stdout.strip()) > 0:
                            logger.error("   Output:")
                            for line in stdout.split('\n')[:20]:
                                if line.strip():
                                    logger.error(f"      {line}")
                    except subprocess.TimeoutExpired:
                        logger.error("   ❌ Server exited and no output captured")
                        
            except Exception as e:
                logger.error(f"   ❌ Failed to test individual server: {e}")
            
            logger.info("")
        
        # Set mcp_success for compatibility with display logic
        mcp_success = len(available_servers) if 'available_servers' in locals() else 0
        mcp_total = len(manager.mcp_configs)
        
        # Phase 2: Start client applications
        client_success, client_total = await manager.start_all_clients()
        
        # Print comprehensive status
        manager.print_status()
        
        # Print final summary
        logger.info("\n" + "="*80)
        logger.info("📊 STARTUP SUMMARY")
        logger.info("="*80)
        
        # Count loaded tools
        tool_count = len(tools) if 'tools' in locals() and tools else 0
        server_count = len(available_servers) if 'available_servers' in locals() else 0
        
        logger.info(f"\n   MCP Infrastructure:")
        logger.info(f"      • Configured servers: {mcp_total}")
        logger.info(f"      • Available servers: {server_count}")
        logger.info(f"      • Loaded tools: {tool_count}")
        
        if tool_count > 5:
            logger.info(f"      Status: ✅ MCP servers working correctly")
        elif tool_count > 0:
            logger.info(f"      Status: ⚠️  Limited functionality (few tools or HTTP-only)")
        else:
            logger.info(f"      Status: ❌ MCP servers failed to load")
            
        logger.info(f"\n   Client Applications:")
        logger.info(f"      • Total clients: {client_total}")
        logger.info(f"      • Running clients: {client_success}")
        logger.info(f"      • Failed clients: {client_total - client_success}")
        
        if client_success == client_total:
            logger.info(f"      Status: ✅ All clients running")
        elif client_success > 0:
            logger.info(f"      Status: ⚠️  Some clients running")
        else:
            logger.info(f"      Status: ❌ No clients running")
        
        logger.info("")
        
        # Overall status
        if client_success == 0:
            logger.error("="*80)
            logger.error("❌ STARTUP FAILED - NO CLIENTS RUNNING")
            logger.error("="*80)
            logger.error("\nThe system cannot start without client applications.")
            logger.error("Please check the error messages above and fix the issues.")
            logger.error("")
            return
        
        if tool_count > 5 and client_success == client_total:
            logger.info("="*80)
            logger.info("🎉 STARTUP SUCCESSFUL - SYSTEM READY!")
            logger.info("="*80)
            logger.info("")
            logger.info("✅ All servers and clients are running correctly")
        elif tool_count > 0 or client_success > 0:
            logger.info("="*80)
            logger.info("⚠️  STARTUP PARTIAL - SYSTEM RUNNING WITH LIMITATIONS")
            logger.info("="*80)
            logger.info("")
            logger.info("Some components failed to start. Check logs above for details.")
        
        logger.info("")
        logger.info("🌐 Access your applications using the URLs shown above")
        logger.info("ℹ️  MCP servers spawn automatically when clients request tools")
        logger.info("🛑 Use Ctrl+C to stop all processes")
        logger.info("")
        logger.info("="*80)
        
        # Keep the script running and monitor processes
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            # Check for failed clients
            failed_clients = []
            for client_name, process in list(manager.client_processes.items()):
                if process.poll() is not None:
                    logger.warning(f"⚠️  Client {client_name} has stopped unexpectedly")
                    failed_clients.append(client_name)
                    del manager.client_processes[client_name]
            
            # Log status if any failures detected
            if failed_clients:
                logger.info("📊 System status update:")
                running_clients = len([p for p in manager.client_processes.values() if p.poll() is None])
                logger.info(f"   Clients: {running_clients}/{client_total} running")
                logger.info(f"   MCP Servers: Managed by ServerManager")
    
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
    finally:
        manager.stop_all()

if __name__ == "__main__":
    asyncio.run(main())
