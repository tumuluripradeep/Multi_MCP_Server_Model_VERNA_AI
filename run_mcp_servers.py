#!/usr/bin/env python3
"""
Script to manually start and manage individual MCP servers for development and testing.
This script allows you to start servers individually or all at once.
"""

import asyncio
import json
import os
import subprocess
import sys
import signal
import time
from typing import Dict, List, Optional
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fix Windows console encoding issues
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        # Fallback: use ASCII-safe symbols
        pass

# Define symbols that work across platforms
SYMBOLS = {
    'success': '[OK]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[OK]',
    'error': '[X]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[X]',
    'warning': '[!]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[!]',
    'info': '[i]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else 'ℹ️',
    'rocket': '[*]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[*]',
    'stop': '[!]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[STOP]',
    'clean': '[~]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[CLEAN]',
    'monitor': '[M]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[VIEW]',
    'list': '[L]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[LIST]',
    'chart': '[#]' if sys.platform == "win32" and not sys.stdout.encoding.lower().startswith('utf') else '[STATS]'
}

# Load server configuration
CONFIG_PATH = os.path.join("Servers", "config", "mcp_servers.json")

class MCPServerRunner:
    def __init__(self):
        self.processes: Dict[str, subprocess.Popen] = {}
        self.server_configs = {}
        self._load_configs()
    
    def _load_configs(self):
        """Load server configurations from JSON file"""
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Handle both flat structure and nested mcpServers structure
                if 'mcpServers' in config_data:
                    self.server_configs = config_data['mcpServers']
                else:
                    self.server_configs = config_data
            print(f"{SYMBOLS['success']} Loaded {len(self.server_configs)} server configurations")
        except Exception as e:
            print(f"{SYMBOLS['error']} Failed to load server configs: {e}")
            sys.exit(1)
    
    def list_servers(self):
        """List all available servers"""
        print(f"\n{SYMBOLS['list']} Available MCP Servers:")
        print("-" * 60)
        for name, config in self.server_configs.items():
            port = config.get('env', {}).get('MCP_PORT', 'N/A')
            desc = config.get('description', 'No description')
            print(f"  {name:15} | Port: {port:5} | {desc}")
        print("-" * 60)
    
    def start_server(self, server_name: str) -> bool:
        """Start a single MCP server"""
        if server_name not in self.server_configs:
            print(f"{SYMBOLS['error']} Server '{server_name}' not found in configuration")
            return False
        
        if server_name in self.processes:
            print(f"{SYMBOLS['warning']}  Server '{server_name}' is already running")
            return True
        
        config = self.server_configs[server_name]
        
        try:
            # Prepare environment variables
            env = os.environ.copy()
            if 'env' in config:
                for key, value in config['env'].items():
                    # Handle environment variable substitution
                    if value.startswith('${') and value.endswith('}'):
                        env_var = value[2:-1]
                        env[key] = os.getenv(env_var, '')
                        if not env[key]:
                            print(f"[!]  Warning: Environment variable {env_var} is not set")
                    else:
                        env[key] = value
            
            # Prepare command
            command = [config['command']] + config.get('args', [])
            
            print(f"[*] Starting {server_name} server...")
            print(f"   Command: {' '.join(command[:3])}... (truncated)")
            print(f"   Port: {config.get('env', {}).get('MCP_PORT', 'N/A')}")
            
            # Start process
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=True if sys.platform == "win32" else False  # Enable shell on Windows for npx/cmd files
            )
            
            self.processes[server_name] = process
            print(f"[OK] Started {server_name} server (PID: {process.pid})")
            
            # Give server a moment to start
            time.sleep(2)
            
            # Check if process is still running
            if process.poll() is None:
                print(f"[OK] {server_name} server is running")
                return True
            else:
                stderr_output = process.stderr.read() if process.stderr else "No error output"
                print(f"[X] {server_name} server failed to start")
                print(f"   Error: {stderr_output}")
                del self.processes[server_name]
                return False
                
        except Exception as e:
            print(f"[X] Failed to start {server_name} server: {e}")
            return False
    
    def stop_server(self, server_name: str) -> bool:
        """Stop a single MCP server"""
        if server_name not in self.processes:
            print(f"[!]  Server '{server_name}' is not running")
            return True
        
        process = self.processes[server_name]
        
        try:
            print(f"[STOP] Stopping {server_name} server (PID: {process.pid})")
            process.terminate()
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=5)
                print(f"[OK] {server_name} server stopped gracefully")
            except subprocess.TimeoutExpired:
                print(f"[!]  Force killing {server_name} server")
                process.kill()
                process.wait()
                print(f"[OK] {server_name} server force stopped")
            
            del self.processes[server_name]
            return True
            
        except Exception as e:
            print(f"[X] Error stopping {server_name} server: {e}")
            return False
    
    def start_all_servers(self):
        """Start all configured servers"""
        print("[*] Starting all MCP servers...")
        success_count = 0
        
        for server_name in self.server_configs.keys():
            if self.start_server(server_name):
                success_count += 1
            print()  # Add spacing between servers
        
        print(f"[STATS] Started {success_count}/{len(self.server_configs)} servers successfully")
        self.status()
    
    def stop_all_servers(self):
        """Stop all running servers"""
        print("[STOP] Stopping all MCP servers...")
        
        server_names = list(self.processes.keys())
        for server_name in server_names:
            self.stop_server(server_name)
        
        print("[OK] All servers stopped")
    
    def status(self):
        """Show status of all servers"""
        print("\n[STATS] MCP Server Status:")
        print("-" * 70)
        
        for name, config in self.server_configs.items():
            port = config.get('env', {}).get('MCP_PORT', 'N/A')
            
            if name in self.processes:
                process = self.processes[name]
                if process.poll() is None:
                    status = "[OK] RUNNING"
                    pid = f"PID: {process.pid}"
                else:
                    status = "[X] STOPPED"
                    pid = "PID: N/A"
                    # Remove dead process from tracking
                    del self.processes[name]
            else:
                status = "[X] STOPPED"
                pid = "PID: N/A"
            
            print(f"  {name:18} | Port: {port:5} | {status:12} | {pid}")
        
        print("-" * 70)
        print(f"Running: {len(self.processes)}/{len(self.server_configs)} servers")
    
    def monitor(self):
        """Monitor running servers"""
        print("[VIEW]  Monitoring MCP servers (Press Ctrl+C to stop)")
        
        try:
            while True:
                self.status()
                time.sleep(10)
        except KeyboardInterrupt:
            print("\n[STOP] Monitoring stopped")
    
    def cleanup(self):
        """Cleanup all processes"""
        if self.processes:
            print("\n[CLEAN] Cleaning up processes...")
            self.stop_all_servers()

def signal_handler(signum, frame, runner: MCPServerRunner):
    """Handle shutdown signals gracefully"""
    print(f"\n[STOP] Received signal {signum}. Shutting down...")
    runner.cleanup()
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(
        description="MCP Server Runner - Start, stop, and manage MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_mcp_servers.py list                    # List all available servers
  python run_mcp_servers.py start youtube           # Start YouTube server
  python run_mcp_servers.py start-all               # Start all servers
  python run_mcp_servers.py stop youtube            # Stop YouTube server
  python run_mcp_servers.py stop-all                # Stop all servers
  python run_mcp_servers.py status                  # Show server status
  python run_mcp_servers.py monitor                 # Monitor servers continuously
        """
    )
    
    parser.add_argument('command', 
                       choices=['list', 'start', 'stop', 'start-all', 'stop-all', 'status', 'monitor'],
                       help='Command to execute')
    parser.add_argument('server_name', nargs='?', 
                       help='Server name (required for start/stop commands)')
    
    args = parser.parse_args()
    
    runner = MCPServerRunner()
    
    # Register signal handlers
    signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, runner))
    signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, runner))
    
    try:
        if args.command == 'list':
            runner.list_servers()
        
        elif args.command == 'start':
            if not args.server_name:
                print("[X] Server name is required for start command")
                parser.print_help()
                sys.exit(1)
            runner.start_server(args.server_name)
        
        elif args.command == 'stop':
            if not args.server_name:
                print("[X] Server name is required for stop command")
                parser.print_help()
                sys.exit(1)
            runner.stop_server(args.server_name)
        
        elif args.command == 'start-all':
            runner.start_all_servers()
        
        elif args.command == 'stop-all':
            runner.stop_all_servers()
        
        elif args.command == 'status':
            runner.status()
        
        elif args.command == 'monitor':
            runner.monitor()
    
    except Exception as e:
        print(f"[X] Error: {e}")
        sys.exit(1)
    
    finally:
        runner.cleanup()

if __name__ == "__main__":
    main() 