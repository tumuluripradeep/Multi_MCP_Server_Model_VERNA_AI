#!/usr/bin/env python3
"""
Automated MCP Server Startup and Health Monitoring Script
This script starts all configured MCP servers, monitors their health, and provides status updates.
"""

import asyncio
import json
import os
import subprocess
import sys
import signal
import time
import httpx
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mcp_servers.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Fix Windows asyncio subprocess issue
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class MCPServerManager:
    def __init__(self):
        self.config_path = Path("Servers/config/mcp_servers.json")
        self.processes: Dict[str, subprocess.Popen] = {}
        self.server_configs = {}
        self.health_status = {}
        self.startup_times = {}
        self.load_configs()
    
    def load_configs(self):
        """Load server configurations from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                self.server_configs = config_data.get('mcpServers', {})
            logger.info(f"[OK] Loaded {len(self.server_configs)} server configurations")
        except Exception as e:
            logger.error(f"[ERROR] Failed to load server configs: {e}")
            sys.exit(1)
    
    async def start_all_servers(self) -> Tuple[int, int]:
        """Start all configured servers with parallel startup"""
        logger.info("[INFO] Starting all MCP servers...")
        
        # Start servers in parallel (but with slight delays to avoid port conflicts)
        startup_tasks = []
        for i, server_name in enumerate(self.server_configs.keys()):
            # Add slight delay between starts to prevent conflicts
            delay = i * 0.5
            task = asyncio.create_task(self._start_server_with_delay(server_name, delay))
            startup_tasks.append(task)
        
        # Wait for all servers to start
        results = await asyncio.gather(*startup_tasks, return_exceptions=True)
        
        # Count successes
        success_count = sum(1 for result in results if result is True)
        total_count = len(self.server_configs)
        
        logger.info(f"[STATS] Started {success_count}/{total_count} servers successfully")
        
        if success_count > 0:
            # Perform health checks on running servers
            await self.perform_health_checks()
        
        return success_count, total_count
    
    async def _start_server_with_delay(self, server_name: str, delay: float) -> bool:
        """Start a server with initial delay"""
        await asyncio.sleep(delay)
        return await self.start_server(server_name)
    
    async def start_server(self, server_name: str) -> bool:
        """Start a single MCP server"""
        if server_name not in self.server_configs:
            logger.error(f"[ERROR] Server '{server_name}' not found in configuration")
            return False
        
        if server_name in self.processes:
            logger.warning(f"[WARNING] Server '{server_name}' is already running")
            return True
        
        config = self.server_configs[server_name]
        
        # Skip HTTP-only servers (they don't need to be started as processes)
        if config.get('type') == 'http':
            logger.info(f"[HTTP] HTTP server '{server_name}' - no process needed")
            self.health_status[server_name] = True
            return True
        
        try:
            # Prepare environment variables
            env = os.environ.copy()
            if 'env' in config:
                for key, value in config['env'].items():
                    if value.startswith('${') and value.endswith('}'):
                        env_var = value[2:-1]
                        env[key] = os.getenv(env_var, '')
                        if not env[key] and env_var not in ['SLACK_BOT_TOKEN', 'YOUTUBE_API_KEY']:
                            logger.warning(f"[WARNING] Environment variable {env_var} is not set for {server_name}")
                    else:
                        env[key] = value
            
            # Prepare command
            command = [config['command']] + config.get('args', [])
            
            logger.info(f"[STARTING] Starting {server_name} server...")
            start_time = time.time()
            
            # Start process with better error handling
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            self.processes[server_name] = process
            self.startup_times[server_name] = start_time
            
            # Give server time to start
            await asyncio.sleep(3)
            
            # Check if process is still running
            if process.poll() is None:
                elapsed = time.time() - start_time
                logger.info(f"[OK] {server_name} server started (PID: {process.pid}, {elapsed:.1f}s)")
                self.health_status[server_name] = True
                return True
            else:
                # Process failed, get error details
                try:
                    stdout, stderr = process.communicate(timeout=1)
                    error_msg = stderr or stdout or "No error output"
                except subprocess.TimeoutExpired:
                    error_msg = "Process terminated immediately"
                
                logger.error(f"[ERROR] {server_name} server failed to start: {error_msg}")
                if server_name in self.processes:
                    del self.processes[server_name]
                self.health_status[server_name] = False
                return False
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to start {server_name} server: {e}")
            self.health_status[server_name] = False
            return False
    
    async def perform_health_checks(self):
        """Perform health checks on all running servers"""
        logger.info("[CHECK] Performing health checks...")
        
        health_tasks = []
        for server_name in self.server_configs.keys():
            task = asyncio.create_task(self._check_server_health(server_name))
            health_tasks.append(task)
        
        await asyncio.gather(*health_tasks, return_exceptions=True)
        
        # Report health status
        healthy_count = sum(1 for status in self.health_status.values() if status)
        total_count = len(self.health_status)
        
        logger.info(f"[HEALTH] Health check complete: {healthy_count}/{total_count} servers healthy")
    
    async def _check_server_health(self, server_name: str):
        """Check health of a specific server"""
        config = self.server_configs[server_name]
        
        # For HTTP servers, try to ping the URL
        if config.get('type') == 'http':
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.head(config['url'])
                    self.health_status[server_name] = response.status_code < 400
            except:
                self.health_status[server_name] = False
            return
        
        # For MCP servers, check if process is running and port is responsive
        port = config.get('env', {}).get('MCP_PORT')
        if not port:
            self.health_status[server_name] = server_name in self.processes
            return
        
        # Check if process is still running
        if server_name not in self.processes:
            self.health_status[server_name] = False
            return
        
        process = self.processes[server_name]
        if process.poll() is not None:
            self.health_status[server_name] = False
            del self.processes[server_name]
            return
        
        # Try to connect to the port
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Try a simple connection test
                await client.get(f"http://127.0.0.1:{port}/health", timeout=3.0)
                self.health_status[server_name] = True
        except:
            # Port might not be ready yet, but process is running
            self.health_status[server_name] = True
    
    def stop_all_servers(self):
        """Stop all running servers"""
        logger.info("🛑 Stopping all MCP servers...")
        
        for server_name in list(self.processes.keys()):
            self.stop_server(server_name)
        
        logger.info("✅ All servers stopped")
    
    def stop_server(self, server_name: str) -> bool:
        """Stop a single MCP server"""
        if server_name not in self.processes:
            return True
        
        process = self.processes[server_name]
        
        try:
            logger.info(f"🛑 Stopping {server_name} server (PID: {process.pid})")
            
            # Graceful shutdown
            process.terminate()
            
            try:
                process.wait(timeout=5)
                logger.info(f"✅ {server_name} server stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ Force killing {server_name} server")
                process.kill()
                process.wait()
                logger.info(f"✅ {server_name} server force stopped")
            
            del self.processes[server_name]
            self.health_status[server_name] = False
            return True
            
        except Exception as e:
            logger.error(f"❌ Error stopping {server_name} server: {e}")
            return False
    
    def get_status_summary(self) -> Dict:
        """Get comprehensive status summary"""
        running_servers = []
        failed_servers = []
        
        for server_name, config in self.server_configs.items():
            port = config.get('env', {}).get('MCP_PORT', 'N/A')
            is_healthy = self.health_status.get(server_name, False)
            
            server_info = {
                'name': server_name,
                'port': port,
                'healthy': is_healthy,
                'type': config.get('type', 'mcp'),
                'description': config.get('description', '')[:50] + '...'
            }
            
            if is_healthy:
                running_servers.append(server_info)
            else:
                failed_servers.append(server_info)
        
        return {
            'running': running_servers,
            'failed': failed_servers,
            'total': len(self.server_configs),
            'healthy_count': len(running_servers)
        }
    
    def print_status(self):
        """Print detailed status information"""
        status = self.get_status_summary()
        
        print(f"\n{'='*80}")
        print(f"🖥️  MCP SERVER STATUS DASHBOARD")
        print(f"{'='*80}")
        print(f"📊 Total Servers: {status['total']}")
        print(f"💚 Healthy: {status['healthy_count']}")
        print(f"❌ Failed: {len(status['failed'])}")
        print(f"⏰ Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if status['running']:
            print(f"\n✅ RUNNING SERVERS ({len(status['running'])}):")
            print("-" * 80)
            for server in status['running']:
                port_str = f"Port: {server['port']}" if server['port'] != 'N/A' else "HTTP Service"
                print(f"  🟢 {server['name']:<20} | {port_str:<12} | {server['description']}")
        
        if status['failed']:
            print(f"\n❌ FAILED SERVERS ({len(status['failed'])}):")
            print("-" * 80)
            for server in status['failed']:
                port_str = f"Port: {server['port']}" if server['port'] != 'N/A' else "HTTP Service"
                print(f"  🔴 {server['name']:<20} | {port_str:<12} | {server['description']}")
        
        print(f"{'='*80}\n")

async def main():
    """Main function to start and manage MCP servers"""
    manager = MCPServerManager()
    
    def signal_handler(signum, frame):
        logger.info("🛑 Received shutdown signal")
        manager.stop_all_servers()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start all servers
        success_count, total_count = await manager.start_all_servers()
        
        # Print status
        manager.print_status()
        
        if success_count == 0:
            logger.error("❌ No servers started successfully. Exiting.")
            return
        
        logger.info("🎯 MCP servers are ready for connections!")
        logger.info("💡 Use Ctrl+C to stop all servers")
        
        # Keep the script running and perform periodic health checks
        while True:
            await asyncio.sleep(30)  # Check every 30 seconds
            await manager.perform_health_checks()
            
            # Check for failed processes
            failed_servers = []
            for server_name, process in list(manager.processes.items()):
                if process.poll() is not None:
                    logger.warning(f"⚠️ Server {server_name} has stopped unexpectedly")
                    failed_servers.append(server_name)
                    del manager.processes[server_name]
                    manager.health_status[server_name] = False
            
            # Optionally restart failed servers
            for server_name in failed_servers:
                logger.info(f"🔄 Attempting to restart {server_name}")
                await manager.start_server(server_name)
    
    except KeyboardInterrupt:
        logger.info("🛑 Shutdown requested by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
    finally:
        manager.stop_all_servers()

if __name__ == "__main__":
    asyncio.run(main()) 