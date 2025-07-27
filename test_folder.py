#!/usr/bin/env python3
"""
Test script to debug folder path issues
"""

import os
import sys
from pathlib import Path

def test_folder_path(folder_path):
    """Test if a folder path is valid and accessible."""
    print(f"🔍 Testing folder path: '{folder_path}'")
    print("=" * 50)
    
    # Check if path is provided
    if not folder_path:
        print("❌ No folder path provided")
        return False
    
    # Check if path exists
    if not os.path.exists(folder_path):
        print(f"❌ Path does not exist: {folder_path}")
        return False
    
    # Check if it's a directory
    if not os.path.isdir(folder_path):
        print(f"❌ Path is not a directory: {folder_path}")
        return False
    
    # Check if directory is readable
    if not os.access(folder_path, os.R_OK):
        print(f"❌ Directory is not readable: {folder_path}")
        return False
    
    print("✅ Folder path is valid and accessible")
    
    # List some files in the directory
    try:
        files = list(Path(folder_path).iterdir())
        print(f"📁 Found {len(files)} items in directory")
        
        # Show first 10 files
        for i, file_path in enumerate(files[:10]):
            file_type = "📁" if file_path.is_dir() else "📄"
            print(f"  {file_type} {file_path.name}")
        
        if len(files) > 10:
            print(f"  ... and {len(files) - 10} more items")
            
    except Exception as e:
        print(f"❌ Error listing directory contents: {e}")
        return False
    
    return True

def main():
    """Main function."""
    if len(sys.argv) != 2:
        print("Usage: python test_folder.py <folder_path>")
        print("Example: python test_folder.py /path/to/your/videos")
        return
    
    folder_path = sys.argv[1]
    success = test_folder_path(folder_path)
    
    if success:
        print("\n🎉 Folder is ready for scanning!")
        print("You can now use this path in the JAV Scraper web interface.")
    else:
        print("\n⚠️  Please fix the folder path issues before using the scraper.")

if __name__ == "__main__":
    main() 