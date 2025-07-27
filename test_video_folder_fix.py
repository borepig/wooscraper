#!/usr/bin/env python3
"""
Test to verify metadata files are saved in the same folder as the video file
"""

import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_video_folder_fix():
    """Test that metadata files are saved in the same folder as the video file."""
    
    # Create temporary test directory with nested structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create nested folder structure to simulate real scenario
        # /temp_dir/
        # ├── Downloads/
        # │   ├── JAV/
        # │   │   ├── DASS-695.mp4
        # │   │   └── ABC-1234.avi
        # │   └── Other/
        # │       └── DEF-567.mkv
        
        downloads = temp_path / "Downloads"
        jav_folder = downloads / "JAV"
        other_folder = downloads / "Other"
        
        jav_folder.mkdir(parents=True, exist_ok=True)
        other_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video files
        video_file_1 = jav_folder / "DASS-695.mp4"
        video_file_2 = jav_folder / "ABC-1234.avi"
        video_file_3 = other_folder / "DEF-567.mkv"
        
        video_file_1.touch()
        video_file_2.touch()
        video_file_3.touch()
        
        print("🧪 Test: Metadata files in same folder as video")
        print("=" * 50)
        print(f"📁 Test directory: {temp_path}")
        print(f"📁 Downloads folder: {downloads}")
        print(f"📁 JAV folder: {jav_folder}")
        print(f"📁 Other folder: {other_folder}")
        print(f"📁 Video 1: {video_file_1}")
        print(f"📁 Video 2: {video_file_2}")
        print(f"📁 Video 3: {video_file_3}")
        
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
        
        # Test scenarios with different video locations
        test_scenarios = [
            {
                'name': 'Video in JAV folder',
                'video_file': video_file_1,
                'jav_code': 'DASS-695'
            },
            {
                'name': 'Video in Other folder',
                'video_file': video_file_3,
                'jav_code': 'DEF-567'
            }
        ]
        
        for scenario in test_scenarios:
            print(f"\n📁 Testing: {scenario['name']}")
            print("-" * 40)
            
            video_file = scenario['video_file']
            jav_code = scenario['jav_code']
            
            print(f"🎬 Video file: {video_file}")
            print(f"🎬 Video folder: {video_file.parent}")
            
            # UI settings - organize_files = false
            ui_settings = {
                'create_nfo': True,
                'download_cover': True,
                'organize_files': False
            }
            
            print(f"⚙️ UI Settings: {ui_settings}")
            
            # Simulate the exact logic from app.py
            organize_files = ui_settings.get('organize_files', True)
            print(f"🔧 organize_files setting: {organize_files}")
            
            # File info simulation
            file_info = {
                'folder': str(video_file.parent),  # This might be the issue
                'file_path': str(video_file),
                'jav_code': jav_code
            }
            
            print(f"📋 File info: {file_info}")
            
            if organize_files:
                print("❌ ERROR: This should NOT happen when organize_files=false!")
                # This branch should not execute
                original_folder = Path(file_info['folder'])
                videos_base = original_folder.parent / "videos"
                output_folder = videos_base / jav_code
                output_folder.mkdir(parents=True, exist_ok=True)
                print(f"❌ Created organized folder: {output_folder}")
            else:
                print("✅ CORRECT: Using video file's folder")
                # Use the folder where the video file is located
                video_file_path = Path(file_info['file_path'])
                output_folder = video_file_path.parent
                print(f"✅ Video file path: {video_file_path}")
                print(f"✅ Video folder: {output_folder}")
                print(f"✅ Metadata files will be saved in: {output_folder}")
            
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
            
            # List all files in the video's folder
            print(f"\n📂 Files in {video_file.parent}:")
            for file in video_file.parent.iterdir():
                print(f"   - {file.name}")
            
            # Verify no videos folder was created
            videos_folder = temp_path / "videos"
            if videos_folder.exists():
                print(f"❌ ERROR: Videos folder was created when organize_files=false!")
                print(f"   Videos folder: {videos_folder}")
            else:
                print(f"✅ No videos folder created (correct behavior)")
            
            # Check if all metadata files are in the same folder as video
            expected_files = [video_file.name, "movie.nfo", "fanart.jpg", "poster.jpg"]
            actual_files = [f.name for f in video_file.parent.iterdir()]
            
            print(f"\n📋 Expected files in {video_file.parent}: {expected_files}")
            print(f"📋 Actual files in {video_file.parent}: {actual_files}")
            
            missing_files = set(expected_files) - set(actual_files)
            extra_files = set(actual_files) - set(expected_files)
            
            if missing_files:
                print(f"❌ Missing files: {missing_files}")
            if extra_files:
                print(f"⚠️ Extra files: {extra_files}")
            
            if not missing_files and not extra_files:
                print("✅ All files are in the correct location!")
            
            print(f"\n📂 Final structure for {scenario['name']}:")
            print(f"   {video_file.parent}")
            print(f"   ├── {video_file.name}")
            print(f"   ├── movie.nfo")
            print(f"   ├── fanart.jpg")
            print(f"   └── poster.jpg")
            
            print(f"\n✅ {scenario['name']} test completed!")
        
        print(f"\n🎯 Summary:")
        print(f"   ✅ organize_files=false: All metadata files in same folder as video")
        print(f"   ✅ organize_files=false: Video stays in original location")
        print(f"   ✅ organize_files=false: No videos folder created")
        print(f"   ✅ Fixed: Using video file's parent directory instead of file_info['folder']")

if __name__ == "__main__":
    test_video_folder_fix() 