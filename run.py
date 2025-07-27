#!/usr/bin/env python3
"""
JAV Scraper - Startup Script
A simple script to run the JAV scraper application
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed."""
    try:
        import flask
        import requests
        import yaml
        import aiohttp
        import bs4
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def install_dependencies():
    """Install required dependencies."""
    print("Installing dependencies...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False

def main():
    """Main startup function."""
    print("🚀 JAV Scraper - Professional Metadata Tool")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not Path("app.py").exists():
        print("❌ Error: app.py not found. Please run this script from the project directory.")
        return
    
    # Check dependencies
    if not check_dependencies():
        print("\nInstalling missing dependencies...")
        if not install_dependencies():
            return
    
    print("\n🎯 Starting JAV Scraper...")
    print("📱 Web interface will open automatically")
    print("🌐 Access the application at: http://localhost:5000")
    print("⏹️  Press Ctrl+C to stop the server")
    print("-" * 50)
    
    # Start the Flask application
    try:
        # Open browser after a short delay
        def open_browser():
            time.sleep(2)
            try:
                webbrowser.open('http://localhost:5000')
            except:
                # If port 5000 fails, try 5001
                webbrowser.open('http://localhost:5001')
        
        import threading
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.daemon = True
        browser_thread.start()
        
        # Run the Flask app
        from app import app
        try:
            app.run(debug=False, host='0.0.0.0', port=5000)
        except OSError as e:
            if "Address already in use" in str(e):
                print("⚠️  Port 5000 is in use. Trying port 5001...")
                app.run(debug=False, host='0.0.0.0', port=5001)
            else:
                raise e
        
    except KeyboardInterrupt:
        print("\n👋 JAV Scraper stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting application: {e}")
        print("Please check the logs for more details")

if __name__ == "__main__":
    main() 