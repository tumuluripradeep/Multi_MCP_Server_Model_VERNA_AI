#!/usr/bin/env python3
"""
Startup script for the Verna AI Chrome Extension
This script starts the backend server and optionally generates icons.
"""

import os
import sys
import subprocess
import time
import webbrowser
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import fastapi
        import uvicorn
        import pydantic
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        return False

def generate_icons():
    """Generate placeholder icons if they don't exist"""
    icons_dir = Path(__file__).parent / 'icons'
    required_icons = ['icon16.png', 'icon32.png', 'icon48.png', 'icon128.png']
    
    missing_icons = [icon for icon in required_icons 
                    if not (icons_dir / icon).exists()]
    
    if missing_icons:
        print(f"Missing icons: {missing_icons}")
        print("Generating placeholder icons...")
        
        try:
            # Try to run the icon generation script
            icon_script = Path(__file__).parent / 'generate_icons.py'
            if icon_script.exists():
                subprocess.run([sys.executable, str(icon_script)], check=True)
                print("✅ Icons generated successfully!")
            else:
                print("❌ Icon generation script not found")
                create_simple_icons(icons_dir, missing_icons)
        except Exception as e:
            print(f"❌ Error generating icons: {e}")
            create_simple_icons(icons_dir, missing_icons)
    else:
        print("✅ All required icons are present")

def create_simple_icons(icons_dir, missing_icons):
    """Create very simple placeholder icons without PIL"""
    icons_dir.mkdir(exist_ok=True)
    
    # Create simple SVG icons and note for manual creation
    print("\n📝 Please create the following icon files manually:")
    for icon in missing_icons:
        size = int(icon.replace('icon', '').replace('.png', ''))
        print(f"   - {icons_dir / icon} ({size}x{size} pixels)")
    
    print("\nYou can use any image editor to create PNG files with:")
    print("   - Purple/blue gradient background")
    print("   - White robot emoji (🤖) or 'AI' text")
    print("   - Appropriate size for each icon")

def start_backend_server():
    """Start the FastAPI backend server"""
    print("🚀 Starting Verna AI Chrome Extension Backend...")
    
    # Change to the Clients directory
    clients_dir = Path(__file__).parent.parent
    os.chdir(clients_dir)
    
    try:
        # Start the Chrome extension client
        subprocess.run([
            sys.executable, 
            'chrome_extension_client.py'
        ], check=True)
    except KeyboardInterrupt:
        print("\n⏹️  Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        return False
    
    return True

def show_instructions():
    """Show installation and usage instructions"""
    print("\n" + "="*60)
    print("🤖 Verna AI Chrome Extension Setup")
    print("="*60)
    
    print("\n📋 NEXT STEPS:")
    print("\n1. 🌐 Load the Extension in Chrome:")
    print("   - Open Chrome and go to chrome://extensions/")
    print("   - Enable 'Developer mode' (toggle in top right)")
    print("   - Click 'Load unpacked'")
    print("   - Select this folder: Clients/chrome_extension/")
    
    print("\n2. 📌 Pin the Extension:")
    print("   - Click the Extensions icon in Chrome toolbar")
    print("   - Pin the Verna AI extension")
    
    print("\n3. 🎯 Usage:")
    print("   - Click the extension icon to open the popup")
    print("   - Right-click on any webpage for context menu")
    print("   - Use Ctrl+Shift+M for quick access")
    
    print("\n4. ⚙️  Settings:")
    print("   - Click the settings button in the popup")
    print("   - Verify API URL is: http://localhost:8001")
    
    print("\n🔧 TROUBLESHOOTING:")
    print("   - Ensure the backend server is running")
    print("   - Check Chrome extension console for errors")
    print("   - Reload the extension after making changes")
    
    print("\n📚 More info: See README.md in this directory")
    print("="*60)

def main():
    """Main function to set up and start the extension"""
    print("🤖 Verna AI Chrome Extension Startup")
    print("-"*50)
    
    # Check dependencies
    print("🔍 Checking dependencies...")
    if not check_dependencies():
        print("❌ Please install required dependencies:")
        print("   pip install fastapi uvicorn pydantic")
        return 1
    
    print("✅ Dependencies OK")
    
    # Generate icons if needed
    print("🎨 Checking icons...")
    generate_icons()
    
    # Show instructions first
    show_instructions()
    
    # Ask user if they want to start the server
    print("\n" + "-"*50)
    response = input("Start the backend server now? (y/n): ").lower().strip()
    
    if response in ['y', 'yes', '']:
        # Start the backend server
        success = start_backend_server()
        return 0 if success else 1
    else:
        print("\n💡 To start the server later, run:")
        print("   python Clients/chrome_extension_client.py")
        return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️  Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1) 