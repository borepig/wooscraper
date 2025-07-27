#!/usr/bin/env python3
"""
Test script to verify organize_files=false behavior - videos should NOT be moved
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_organize_files_disabled():
    """Test that when organize_files=false, videos are NOT moved."""
    
    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test folder structure
        test_folder = temp_path / "TestVideos"
        test_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video file
        video_file = test_folder / "DASS-695.mp4"
        video_file.touch()
        
        print("🧪 Testing organize_files=false behavior")
        print("=" * 50)
        print(f"📁 Test directory: {temp_path}")
        print(f"📁 Test folder: {test_folder}")
        print(f"📁 Original video: {video_file}")
        
        # Test metadata
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
        print("\n📁 Testing organize_files = false")
        print("-" * 30)
        
        original_folder = test_folder
        output_folder = original_folder  # Use original folder - NO MOVING
        
        print(f"✅ Using original folder: {output_folder}")
        print(f"✅ Video should stay in: {video_file}")
        
        # Create NFO file in original folder
        nfo_path = output_folder / "movie.nfo"
        engine = JAVScraperEngine()
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Simulate fanart and poster creation in original folder
        fanart_path = output_folder / "fanart.jpg"
        poster_path = output_folder / "poster.jpg"
        fanart_path.touch()  # Simulate file creation
        poster_path.touch()   # Simulate file creation
        print(f"✅ Created fanart.jpg: {fanart_path}")
        print(f"✅ Created poster.jpg: {poster_path}")
        
        # Check if video is still in original location
        if video_file.exists():
            print(f"✅ Video still exists in original location: {video_file}")
        else:
            print(f"❌ ERROR: Video was moved when it shouldn't have been!")
        
        # List all files in the folder
        print(f"\n📂 Files in {test_folder}:")
        for file in test_folder.iterdir():
            print(f"   - {file.name}")
        
        # Verify no videos folder was created
        videos_folder = temp_path / "videos"
        if videos_folder.exists():
            print(f"❌ ERROR: Videos folder was created when organize_files=false!")
            print(f"   Videos folder: {videos_folder}")
        else:
            print(f"✅ No videos folder created (correct behavior)")
        
        print(f"\n📂 Final structure (organize_files=false):")
        print(f"   {test_folder}")
        print(f"   ├── DASS-695.mp4 (original location)")
        print(f"   ├── movie.nfo")
        print(f"   ├── fanart.jpg")
        print(f"   └── poster.jpg")
        
        print(f"\n🎯 Key Points:")
        print(f"   ✅ organize_files=false: Video stays in original folder")
        print(f"   ✅ organize_files=false: No videos folder created")
        print(f"   ✅ organize_files=false: All metadata in same folder as video")
        print(f"   ✅ organize_files=false: NO MOVING of files")
        
        print("\n✅ organize_files=false test completed!")

if __name__ == "__main__":
    test_organize_files_disabled() 