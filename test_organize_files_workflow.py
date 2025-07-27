#!/usr/bin/env python3
"""
Test organize files workflow with correct folder structure
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_organize_files_workflow():
    """Test the organize files workflow with correct folder structure."""
    
    print("🧪 Test: Organize Files Workflow")
    print("=" * 50)
    
    # Create test directory structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create base folder structure like /home/joe/media/Others/JAV/
        base_folder = temp_path / "media" / "Others" / "JAV"
        base_folder.mkdir(parents=True, exist_ok=True)
        
        # Create test video in a subfolder
        test_subfolder = base_folder / "Downloads" / "JAV"
        test_subfolder.mkdir(parents=True, exist_ok=True)
        
        # Create test video file
        test_video = test_subfolder / "DASS-695.mp4"
        test_video.touch()
        
        print(f"📁 Base folder: {base_folder}")
        print(f"📁 Test video location: {test_video}")
        
        # Simulate the organize files workflow
        async with JAVScraperEngine() as engine:
            # Extract JAV code
            jav_code = engine.extract_jav_code("DASS-695.mp4")
            print(f"🎬 JAV Code: {jav_code}")
            
            # Create test metadata with actress
            test_metadata = {
                'jav_code': 'DASS-695',
                'detailed_metadata': {
                    'actress': 'JULIA',
                    'thumb_url': 'https://javtiful.com/actress/thumb/julia.jpg'
                },
                'all_details': {
                    'Title': 'Test Movie',
                    'Actress': 'JULIA'
                }
            }
            
            # Simulate organize files logic
            actress_name = "JULIA"
            
            # Clean actress name for folder creation
            import re
            clean_actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
            clean_actress_name = clean_actress_name.strip()
            
            # Create folder structure
            videos_folder = base_folder / "videos"
            actress_folder = videos_folder / clean_actress_name
            output_folder = actress_folder / jav_code
            
            print(f"\n📁 Folder structure creation:")
            print(f"   📁 Base folder: {base_folder}")
            print(f"   📁 Videos folder: {videos_folder}")
            print(f"   📁 Actress folder: {actress_folder}")
            print(f"   📁 Final folder: {output_folder}")
            
            # Create folders
            output_folder.mkdir(parents=True, exist_ok=True)
            
            # Move video file
            new_video_path = output_folder / f"{jav_code}.mp4"
            shutil.move(str(test_video), str(new_video_path))
            
            print(f"\n✅ File operations:")
            print(f"   📁 Original video: {test_video}")
            print(f"   📁 Moved video: {new_video_path}")
            print(f"   📁 Video exists: {new_video_path.exists()}")
            
            # Create NFO file
            nfo_path = output_folder / "movie.nfo"
            engine.create_nfo_file(test_metadata, str(nfo_path))
            
            print(f"\n✅ Metadata files:")
            print(f"   📄 NFO file: {nfo_path}")
            print(f"   📄 NFO exists: {nfo_path.exists()}")
            
            # List final structure
            print(f"\n📁 Final folder structure:")
            for item in output_folder.iterdir():
                print(f"   📄 {item.name}")
            
            # Verify the complete structure
            print(f"\n✅ Structure verification:")
            print(f"   📁 Videos folder exists: {videos_folder.exists()}")
            print(f"   📁 Actress folder exists: {actress_folder.exists()}")
            print(f"   📁 Movie folder exists: {output_folder.exists()}")
            print(f"   📄 Video file exists: {new_video_path.exists()}")
            print(f"   📄 NFO file exists: {nfo_path.exists()}")
            
            print(f"\n✅ Organize files workflow completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_organize_files_workflow()) 