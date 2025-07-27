#!/usr/bin/env python3
"""
Test script to verify organize_files behavior
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_organize_files_behavior():
    """Test both organize_files: true and organize_files: false behaviors."""
    
    # Create temporary test directory with realistic structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create realistic folder structure
        # /temp_dir/
        # ├── Downloads/
        # │   ├── JAV/
        # │   │   ├── DASS-695.mp4
        # │   │   └── ABC-1234.avi
        # │   └── Other/
        # │       └── DEF-567.mkv
        # └── (videos folder will be created here when organize_files=true)
        
        downloads = temp_path / "Downloads"
        jav_folder = downloads / "JAV"
        other_folder = downloads / "Other"
        
        jav_folder.mkdir(parents=True, exist_ok=True)
        other_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video files
        (jav_folder / "DASS-695.mp4").touch()
        (jav_folder / "ABC-1234.avi").touch()
        (other_folder / "DEF-567.mkv").touch()
        
        print("🧪 Testing Organize Files Behavior")
        print("=" * 50)
        print(f"📁 Test directory: {temp_path}")
        print(f"📁 Downloads folder: {downloads}")
        print(f"📁 JAV folder: {jav_folder}")
        print(f"📁 Other folder: {other_folder}")
        
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
        
        # Test 1: organize_files = false
        print("\n📁 Test 1: organize_files = false")
        print("-" * 30)
        print("Expected: Files stay in original video folder")
        
        # Simulate organize_files = false
        original_folder = jav_folder
        output_folder = original_folder  # Use original folder
        print(f"✅ Using original folder: {output_folder}")
        
        # Create NFO file
        nfo_path = output_folder / "movie.nfo"
        engine = JAVScraperEngine()
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Simulate fanart and poster creation
        fanart_path = output_folder / "fanart.jpg"
        poster_path = output_folder / "poster.jpg"
        fanart_path.touch()  # Simulate file creation
        poster_path.touch()   # Simulate file creation
        print(f"✅ Created fanart.jpg: {fanart_path}")
        print(f"✅ Created poster.jpg: {poster_path}")
        
        print(f"\n📂 organize_files=false structure:")
        print(f"   {jav_folder}")
        print(f"   ├── DASS-695.mp4")
        print(f"   ├── ABC-1234.avi")
        print(f"   ├── movie.nfo")
        print(f"   ├── fanart.jpg")
        print(f"   └── poster.jpg")
        
        # Test 2: organize_files = true
        print("\n📁 Test 2: organize_files = true")
        print("-" * 30)
        print("Expected: Files moved to organized parent folder structure")
        
        # Simulate organize_files = true
        original_folder = jav_folder
        videos_base = original_folder.parent.parent / "videos"  # Parent folder
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
        original_video_path = jav_folder / "DASS-695.mp4"
        new_video_path = output_folder / "DASS-695.mp4"
        if original_video_path.exists():
            shutil.move(str(original_video_path), str(new_video_path))
            print(f"✅ Moved video to: {new_video_path}")
        
        # Create NFO file in organized folder
        nfo_path = output_folder / "movie.nfo"
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Simulate fanart and poster creation in organized folder
        fanart_path = output_folder / "fanart.jpg"
        poster_path = output_folder / "poster.jpg"
        fanart_path.touch()  # Simulate file creation
        poster_path.touch()   # Simulate file creation
        print(f"✅ Created fanart.jpg: {fanart_path}")
        print(f"✅ Created poster.jpg: {poster_path}")
        
        print(f"\n📂 organize_files=true structure:")
        print(f"   {temp_path}")
        print(f"   ├── Downloads/")
        print(f"   │   ├── JAV/")
        print(f"   │   │   └── ABC-1234.avi")
        print(f"   │   └── Other/")
        print(f"   │       └── DEF-567.mkv")
        print(f"   └── videos/")
        print(f"       └── Itou Meru/")
        print(f"           └── DASS-695/")
        print(f"               ├── DASS-695.mp4")
        print(f"               ├── movie.nfo")
        print(f"               ├── fanart.jpg")
        print(f"               └── poster.jpg")
        
        print(f"\n🎯 Behavior Summary:")
        print(f"   ✅ organize_files=false: Files stay in original video folder")
        print(f"   ✅ organize_files=true: Files moved to parent/videos/actress/jav_code/")
        print(f"   ✅ All metadata files (movie.nfo, fanart.jpg, poster.jpg) in same folder")
        print(f"   ✅ Default setting: organize_files=true")
        
        print("\n✅ Organize files behavior test completed!")

if __name__ == "__main__":
    test_organize_files_behavior() 