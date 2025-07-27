#!/usr/bin/env python3
"""
Test script for file organization functionality
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_file_organization():
    """Test file organization with both settings."""
    
    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test video files
        test_videos = [
            "DASS-695.mp4",
            "ABC-1234.avi", 
            "DEF-567.mkv"
        ]
        
        for video in test_videos:
            (temp_path / video).touch()
        
        print("🧪 Testing File Organization")
        print("=" * 50)
        
        # Test 1: organize_files = false
        print("\n📁 Test 1: organize_files = false")
        print("-" * 30)
        
        # Create test metadata
        test_metadata = {
            "jav_code": "DASS-695",
            "detailed_metadata": {
                "actress": "Itou Meru",
                "code": "DASS-695",
                "full_title": "[DASS-695] Test Movie",
                "plot": "Test plot description",
                "release_date": "2025-07-08",
                "director": "Test Director",
                "studio": "Test Studio",
                "label": "TEST",
                "category": "Test Category",
                "actor": "Test Actor",
                "tags": "Test, Tags",
                "fanart_url": "https://example.com/fanart.jpg"
            }
        }
        
        # Simulate organize_files = false
        original_folder = temp_path
        output_folder = original_folder
        print(f"✅ Using original folder: {output_folder}")
        
        # Create NFO file
        nfo_path = output_folder / "movie.nfo"
        engine = JAVScraperEngine()
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Test 2: organize_files = true (with actress)
        print("\n📁 Test 2: organize_files = true (with actress)")
        print("-" * 40)
        
        # Simulate organize_files = true
        videos_base = original_folder / "videos"
        actress_name = "Itou Meru"
        
        # Clean actress name for folder creation
        import re
        actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
        actress_name = actress_name.strip()
        
        # Create folder structure
        actress_folder = videos_base / actress_name
        output_folder = actress_folder / "DASS-695"
        output_folder.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created organized folder: {output_folder}")
        
        # Move and rename video file
        original_video_path = temp_path / "DASS-695.mp4"
        new_video_path = output_folder / "DASS-695.mp4"
        if original_video_path.exists():
            shutil.move(str(original_video_path), str(new_video_path))
            print(f"✅ Moved video to: {new_video_path}")
        
        # Create NFO file in organized folder
        nfo_path = output_folder / "movie.nfo"
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Test 3: organize_files = true (no actress)
        print("\n📁 Test 3: organize_files = true (no actress)")
        print("-" * 40)
        
        # Create test metadata without actress
        test_metadata_no_actress = {
            "jav_code": "ABC-1234",
            "detailed_metadata": {
                "code": "ABC-1234",
                "full_title": "[ABC-1234] Test Movie No Actress",
                "plot": "Test plot description",
                "release_date": "2025-07-08",
                "director": "Test Director",
                "studio": "Test Studio",
                "label": "TEST",
                "category": "Test Category",
                "actor": "Test Actor",
                "tags": "Test, Tags",
                "fanart_url": "https://example.com/fanart.jpg"
            }
        }
        
        # Simulate organize_files = true with no actress
        videos_base = original_folder / "videos"
        actress_name = ""
        
        # Create folder structure (fallback to JAV code only)
        if actress_name:
            actress_folder = videos_base / actress_name
            output_folder = actress_folder / "ABC-1234"
        else:
            # Fallback if no actress name
            output_folder = videos_base / "ABC-1234"
        
        output_folder.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created organized folder (no actress): {output_folder}")
        
        # Move and rename video file
        original_video_path = temp_path / "ABC-1234.avi"
        new_video_path = output_folder / "ABC-1234.avi"
        if original_video_path.exists():
            shutil.move(str(original_video_path), str(new_video_path))
            print(f"✅ Moved video to: {new_video_path}")
        
        # Create NFO file in organized folder
        nfo_path = output_folder / "movie.nfo"
        engine.create_nfo_file(test_metadata_no_actress, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Show final folder structure
        print(f"\n📂 Final folder structure:")
        print(f"   {temp_path}")
        print(f"   └── videos/")
        print(f"       ├── Itou Meru/")
        print(f"       │   └── DASS-695/")
        print(f"       │       ├── DASS-695.mp4")
        print(f"       │       └── movie.nfo")
        print(f"       └── ABC-1234/")
        print(f"           ├── ABC-1234.avi")
        print(f"           └── movie.nfo")
        
        print("\n✅ File organization test completed!")

if __name__ == "__main__":
    test_file_organization() 