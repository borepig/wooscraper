#!/usr/bin/env python3
"""
Helper script to find and test folder paths
"""

import os
import sys
from pathlib import Path

def find_video_folders():
    """Find potential video folders in common locations."""
    print("🔍 Searching for video folders...")
    print("=" * 50)
    
    common_paths = [
        os.path.expanduser("~/Videos"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Desktop"),
        "/mnt",
        "/media",
        "./test_videos",  # Our test folder
    ]
    
    found_folders = []
    
    for base_path in common_paths:
        if os.path.exists(base_path):
            print(f"📁 Checking: {base_path}")
            
            try:
                for item in os.listdir(base_path):
                    item_path = os.path.join(base_path, item)
                    if os.path.isdir(item_path):
                        # Check if it might contain videos
                        video_count = 0
                        for file in os.listdir(item_path):
                            if file.lower().endswith(('.mp4', '.avi', '.mkv', '.wmv', '.mov')):
                                video_count += 1
                        
                        if video_count > 0:
                            print(f"  ✅ {item_path} ({video_count} video files)")
                            found_folders.append(item_path)
                        else:
                            print(f"  ⚪ {item_path} (no video files)")
                            
            except PermissionError:
                print(f"  ❌ {base_path} (permission denied)")
            except Exception as e:
                print(f"  ❌ {base_path} (error: {e})")
        else:
            print(f"❌ {base_path} (does not exist)")
    
    return found_folders

def interactive_folder_test():
    """Interactive folder testing."""
    print("\n🎯 Interactive Folder Testing")
    print("=" * 50)
    
    while True:
        print("\nEnter a folder path to test (or 'quit' to exit):")
        user_input = input("> ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        if not user_input:
            print("❌ Please enter a folder path")
            continue
        
        # Test the folder
        from test_folder import test_folder_path
        success = test_folder_path(user_input)
        
        if success:
            print(f"\n✅ Use this path in the web interface: {user_input}")
            break
        else:
            print("\n❌ Try a different path or check the error message above")

def main():
    """Main function."""
    print("🚀 JAV Scraper - Folder Finder")
    print("=" * 50)
    
    # Find existing video folders
    found_folders = find_video_folders()
    
    if found_folders:
        print(f"\n🎉 Found {len(found_folders)} folders with videos!")
        print("\nYou can use any of these paths in the web interface:")
        for folder in found_folders:
            print(f"  📁 {folder}")
    else:
        print("\n⚠️  No video folders found in common locations.")
        print("You'll need to provide the full path to your video folder.")
    
    # Interactive testing
    interactive_folder_test()

if __name__ == "__main__":
    main() 