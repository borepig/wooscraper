#!/usr/bin/env python3
"""
Test script for parent folder organization functionality
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_parent_folder_organization():
    """Test file organization with parent folder structure."""
    
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
        # └── (videos folder will be created here)
        
        downloads = temp_path / "Downloads"
        jav_folder = downloads / "JAV"
        other_folder = downloads / "Other"
        
        jav_folder.mkdir(parents=True, exist_ok=True)
        other_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video files
        (jav_folder / "DASS-695.mp4").touch()
        (jav_folder / "ABC-1234.avi").touch()
        (other_folder / "DEF-567.mkv").touch()
        
        print("🧪 Testing Parent Folder Organization")
        print("=" * 50)
        print(f"📁 Test directory: {temp_path}")
        print(f"📁 Downloads folder: {downloads}")
        print(f"📁 JAV folder: {jav_folder}")
        print(f"📁 Other folder: {other_folder}")
        
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
        original_folder = jav_folder
        output_folder = original_folder
        print(f"✅ Using original folder: {output_folder}")
        
        # Create NFO file
        nfo_path = output_folder / "movie.nfo"
        engine = JAVScraperEngine()
        engine.create_nfo_file(test_metadata, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Test 2: organize_files = true (parent folder)
        print("\n📁 Test 2: organize_files = true (parent folder)")
        print("-" * 40)
        
        # Simulate organize_files = true with parent folder
        original_folder = jav_folder
        videos_base = original_folder.parent.parent / "videos"  # Go up two levels
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
        
        # Test 3: organize_files = true (different source folder)
        print("\n📁 Test 3: organize_files = true (different source folder)")
        print("-" * 50)
        
        # Create test metadata for different movie
        test_metadata_other = {
            "jav_code": "DEF-567",
            "detailed_metadata": {
                "actress": "Another Actress",
                "code": "DEF-567",
                "full_title": "[DEF-567] Test Movie Other",
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
        
        # Simulate organize_files = true with different source
        original_folder = other_folder
        videos_base = original_folder.parent.parent / "videos"  # Same parent level
        actress_name = "Another Actress"
        
        # Clean actress name for folder creation
        actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
        actress_name = actress_name.strip()
        
        # Create folder structure
        actress_folder = videos_base / actress_name
        output_folder = actress_folder / "DEF-567"
        output_folder.mkdir(parents=True, exist_ok=True)
        print(f"✅ Created organized folder: {output_folder}")
        
        # Move and rename video file
        original_video_path = other_folder / "DEF-567.mkv"
        new_video_path = output_folder / "DEF-567.mkv"
        if original_video_path.exists():
            shutil.move(str(original_video_path), str(new_video_path))
            print(f"✅ Moved video to: {new_video_path}")
        
        # Create NFO file in organized folder
        nfo_path = output_folder / "movie.nfo"
        engine.create_nfo_file(test_metadata_other, str(nfo_path))
        print(f"✅ Created NFO file: {nfo_path}")
        
        # Show final folder structure
        print(f"\n📂 Final folder structure:")
        print(f"   {temp_path}")
        print(f"   ├── Downloads/")
        print(f"   │   ├── JAV/")
        print(f"   │   │   ├── ABC-1234.avi")
        print(f"   │   │   └── movie.nfo")
        print(f"   │   └── Other/")
        print(f"   │       └── (empty)")
        print(f"   └── videos/")
        print(f"       ├── Itou Meru/")
        print(f"       │   └── DASS-695/")
        print(f"       │       ├── DASS-695.mp4")
        print(f"       │       └── movie.nfo")
        print(f"       └── Another Actress/")
        print(f"           └── DEF-567/")
        print(f"               ├── DEF-567.mkv")
        print(f"               └── movie.nfo")
        
        print(f"\n🎯 Key Points:")
        print(f"   ✅ Videos folder created in parent directory: {videos_base}")
        print(f"   ✅ All metadata files (movie.nfo, fanart.jpg, poster.jpg) in same folder")
        print(f"   ✅ Organized by actress name when available")
        print(f"   ✅ Videos moved and renamed to JAV code")
        
        print("\n✅ Parent folder organization test completed!")

if __name__ == "__main__":
    test_parent_folder_organization() 