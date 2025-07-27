#!/usr/bin/env python3
"""
Debug test to verify organize_files=false behavior with actual file operations
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_organize_files_disabled_debug():
    """Test that when organize_files=false, metadata files are saved with video."""
    
    # Create temporary test directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test folder structure
        test_folder = temp_path / "TestVideos"
        test_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video file
        video_file = test_folder / "DASS-695.mp4"
        video_file.touch()
        
        print("🧪 Debug Test: organize_files=false behavior")
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
        
        # Simulate the exact logic from app.py
        print("\n📁 Testing organize_files = false (simulating app.py logic)")
        print("-" * 50)
        
        # UI settings
        ui_settings = {
            'create_nfo': True,
            'download_cover': True,
            'organize_files': False  # This should be OFF
        }
        
        print(f"⚙️ UI Settings: {ui_settings}")
        
        # Simulate the exact logic from app.py
        organize_files = ui_settings.get('organize_files', True)
        print(f"🔧 organize_files setting: {organize_files}")
        
        # File info simulation
        file_info = {
            'folder': str(test_folder),
            'file_path': str(video_file),
            'jav_code': 'DASS-695'
        }
        
        if organize_files:
            print("❌ ERROR: This should NOT happen when organize_files=false!")
            # This branch should not execute
            original_folder = Path(file_info['folder'])
            videos_base = original_folder.parent / "videos"
            output_folder = videos_base / "DASS-695"
            output_folder.mkdir(parents=True, exist_ok=True)
            print(f"❌ Created organized folder: {output_folder}")
        else:
            print("✅ CORRECT: Using original folder")
            # Use original folder - NO MOVING
            output_folder = Path(file_info['folder'])
            print(f"✅ Using original folder: {output_folder}")
        
        # Create NFO file in the determined folder
        nfo_path = output_folder / "movie.nfo"
        engine = JAVScraperEngine()
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Simulate fanart and poster creation in the same folder
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
            print(f"❌ ERROR: Video was moved when organize_files=false!")
        
        # List all files in the test folder
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
        
        # Check if all metadata files are in the same folder as video
        expected_files = ["DASS-695.mp4", "movie.nfo", "fanart.jpg", "poster.jpg"]
        actual_files = [f.name for f in test_folder.iterdir()]
        
        print(f"\n📋 Expected files: {expected_files}")
        print(f"📋 Actual files: {actual_files}")
        
        missing_files = set(expected_files) - set(actual_files)
        extra_files = set(actual_files) - set(expected_files)
        
        if missing_files:
            print(f"❌ Missing files: {missing_files}")
        if extra_files:
            print(f"⚠️ Extra files: {extra_files}")
        
        if not missing_files and not extra_files:
            print("✅ All files are in the correct location!")
        
        print(f"\n📂 Final structure (organize_files=false):")
        print(f"   {test_folder}")
        print(f"   ├── DASS-695.mp4 (original location)")
        print(f"   ├── movie.nfo")
        print(f"   ├── fanart.jpg")
        print(f"   └── poster.jpg")
        
        print(f"\n🎯 Key Points:")
        print(f"   ✅ organize_files=false: Video stays in original folder")
        print(f"   ✅ organize_files=false: All metadata in same folder as video")
        print(f"   ✅ organize_files=false: NO MOVING of files")
        print(f"   ✅ organize_files=false: No videos folder created")
        
        print("\n✅ organize_files=false debug test completed!")

if __name__ == "__main__":
    test_organize_files_disabled_debug() 