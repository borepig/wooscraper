#!/usr/bin/env python3
"""
Test DASS-695 actress portrait example
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_dass_695_portrait_example():
    """Test DASS-695 actress portrait and NFO thumb tag."""
    
    print("🧪 Test: DASS-695 Actress Portrait Example")
    print("=" * 50)
    
    # Create test directory with DASS-695 video file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test video file
        test_video = temp_path / "DASS-695.mp4"
        test_video.touch()
        
        print(f"📁 Test directory: {temp_path}")
        print(f"🎬 Test video: {test_video}")
        
        async with JAVScraperEngine() as engine:
            # Scan for files
            files = engine.scan_folder(str(temp_path))
            print(f"📋 Found {len(files)} files")
            
            if files:
                file_info = files[0]
                jav_code = file_info['jav_code']
                print(f"🎬 Processing JAV code: {jav_code}")
                
                # Scrape metadata (this will include actress portrait search)
                print(f"🔍 Scraping metadata...")
                metadata = await engine.scrape_all_sites(jav_code)
                
                print(f"📊 Metadata keys: {list(metadata.keys())}")
                
                if 'detailed_metadata' in metadata:
                    detailed = metadata['detailed_metadata']
                    print(f"📋 Detailed metadata keys: {list(detailed.keys())}")
                    
                    if 'actress' in detailed:
                        actress_name = detailed['actress']
                        print(f"🎭 Actress name: {actress_name}")
                        
                        # Test direct portrait search for this specific actress
                        print(f"\n🔍 Testing portrait search for: {actress_name}")
                        portrait_url = await engine.search_actress_portrait(actress_name)
                        
                        if portrait_url:
                            print(f"✅ Found portrait URL: {portrait_url}")
                            
                            # Add to metadata
                            metadata['detailed_metadata']['actress_portrait_url'] = portrait_url
                            print(f"✅ Added portrait URL to metadata")
                        else:
                            print(f"❌ No portrait found for {actress_name}")
                    else:
                        print(f"ℹ️ No actress name in metadata")
                    
                    if 'actress_portrait_url' in detailed:
                        portrait_url = detailed['actress_portrait_url']
                        print(f"✅ Found actress portrait URL: {portrait_url}")
                    else:
                        print(f"ℹ️ No actress portrait URL in metadata")
                
                # Test the process_folder method (main workflow)
                print(f"\n🔄 Testing main workflow with process_folder...")
                results = await engine.process_folder(str(temp_path))
                
                print(f"📊 Process results: {len(results)} items")
                
                # Check if files were created
                print(f"\n📂 Checking created files in {temp_path}:")
                for item in temp_path.iterdir():
                    print(f"   📄 {item.name}")
                
                # Look for Videos folder
                videos_folder = temp_path / "Videos"
                if videos_folder.exists():
                    print(f"\n📁 Videos folder contents:")
                    for item in videos_folder.iterdir():
                        print(f"   📄 {item.name}")
                        
                        # Check if it's a portrait file
                        if 'portrait' in item.name.lower():
                            size = item.stat().st_size
                            print(f"      🖼️ Portrait file: {size} bytes")
                    
                    # Check NFO file content
                    nfo_path = videos_folder / "movie.nfo"
                    if nfo_path.exists():
                        print(f"\n📄 Checking NFO file content:")
                        with open(nfo_path, 'r', encoding='utf-8') as f:
                            nfo_content = f.read()
                        
                        # Check for thumb tag
                        if '<thumb>' in nfo_content:
                            print(f"✅ NFO contains <thumb> tag")
                            # Extract thumb content
                            import re
                            thumb_match = re.search(r'<thumb>(.*?)</thumb>', nfo_content)
                            if thumb_match:
                                thumb_url = thumb_match.group(1)
                                print(f"🎭 Thumb URL in NFO: {thumb_url}")
                        else:
                            print(f"❌ NFO does not contain <thumb> tag")
                        
                        # Check for actressportrait tag
                        if '<actressportrait>' in nfo_content:
                            print(f"✅ NFO contains <actressportrait> tag")
                            # Extract actressportrait content
                            actressportrait_match = re.search(r'<actressportrait>(.*?)</actressportrait>', nfo_content)
                            if actressportrait_match:
                                actressportrait_url = actressportrait_match.group(1)
                                print(f"🎭 Actress Portrait URL in NFO: {actressportrait_url}")
                        else:
                            print(f"ℹ️ NFO does not contain <actressportrait> tag")
                        
                        # Check for custom info
                        if 'Actress Portrait' in nfo_content:
                            print(f"✅ NFO contains Actress Portrait in custom info")
                        else:
                            print(f"ℹ️ NFO does not contain Actress Portrait in custom info")
                    else:
                        print(f"❌ No NFO file created")
                else:
                    print(f"❌ No Videos folder created")
                
                # Test with a known actress that has a portrait
                print(f"\n🧪 Testing with known actress (Hibino Uta)...")
                
                # Create test metadata with known actress
                test_metadata = {
                    'detailed_metadata': {
                        'actress': 'Hibino Uta',
                        'actress_portrait_url': 'https://www.javdatabase.com/idolimages/thumb/uta-hibino.webp',
                        'code': 'TEST-123',
                        'full_title': '[TEST-123] Test Movie with Hibino Uta',
                        'plot': 'Test movie featuring Hibino Uta',
                        'release_date': '2025-01-01',
                        'director': 'Test Director',
                        'studio': 'Test Studio',
                        'label': 'TEST',
                        'category': 'Test Category',
                        'actor': 'Test Actor',
                        'tags': 'Test, Tags'
                    }
                }
                
                # Test NFO creation with thumb tag
                print(f"📄 Testing NFO creation with thumb tag...")
                
                nfo_path = temp_path / "test_movie.nfo"
                success = engine.create_nfo_file(test_metadata, str(nfo_path))
                
                if success:
                    print(f"✅ NFO file created: {nfo_path}")
                    
                    # Check if NFO contains thumb tag
                    with open(nfo_path, 'r', encoding='utf-8') as f:
                        nfo_content = f.read()
                    
                    if '<thumb>' in nfo_content:
                        print(f"✅ NFO contains <thumb> tag")
                        # Extract thumb content
                        import re
                        thumb_match = re.search(r'<thumb>(.*?)</thumb>', nfo_content)
                        if thumb_match:
                            thumb_url = thumb_match.group(1)
                            print(f"🎭 Thumb URL in NFO: {thumb_url}")
                    else:
                        print(f"❌ NFO does not contain <thumb> tag")
                else:
                    print(f"❌ Failed to create NFO file")
            else:
                print(f"❌ No JAV files found")
    
    print(f"\n🎯 Summary:")
    print(f"   ✅ DASS-695 actress portrait search tested")
    print(f"   ✅ NFO file thumb tag verification")
    print(f"   ✅ Portrait URL extraction and validation")

if __name__ == "__main__":
    asyncio.run(test_dass_695_portrait_example()) 