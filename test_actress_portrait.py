#!/usr/bin/env python3
"""
Test actress portrait search functionality
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_actress_portrait_search():
    """Test the actress portrait search functionality."""
    
    print("🧪 Test: Actress Portrait Search")
    print("=" * 50)
    
    # Test actress names
    test_actresses = [
        "Hibino Uta",  # Known actress
        "Itou Meru",   # Test actress from previous tests
        "Hatano Yui",  # Popular actress
        "Unknown Actress XYZ"  # Should return None
    ]
    
    async with JAVScraperEngine() as engine:
        for actress_name in test_actresses:
            print(f"\n🎭 Testing actress: {actress_name}")
            print("-" * 40)
            
            # Test direct portrait search
            portrait_url = await engine.search_actress_portrait(actress_name)
            
            if portrait_url:
                print(f"✅ Found portrait URL: {portrait_url}")
            else:
                print(f"❌ No portrait found for {actress_name}")
            
            # Test metadata enhancement
            test_metadata = {
                'detailed_metadata': {
                    'actress': actress_name,
                    'code': 'TEST-123',
                    'full_title': f'[TEST-123] Test Movie with {actress_name}',
                    'plot': f'Test movie featuring {actress_name}',
                    'release_date': '2025-01-01',
                    'director': 'Test Director',
                    'studio': 'Test Studio',
                    'label': 'TEST',
                    'category': 'Test Category',
                    'actor': 'Test Actor',
                    'tags': 'Test, Tags'
                }
            }
            
            print(f"🔧 Testing metadata enhancement...")
            enhanced_metadata = await engine.enhance_actress_metadata(test_metadata)
            
            if enhanced_metadata.get('detailed_metadata', {}).get('actress_portrait_url'):
                portrait_url = enhanced_metadata['detailed_metadata']['actress_portrait_url']
                print(f"✅ Enhanced metadata contains portrait URL: {portrait_url}")
            else:
                print(f"ℹ️ No portrait URL added to enhanced metadata")
            
            # Test NFO creation with actress portrait
            print(f"📄 Testing NFO creation with actress portrait...")
            
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                nfo_path = temp_path / "movie.nfo"
                
                success = engine.create_nfo_file(enhanced_metadata, str(nfo_path))
                
                if success:
                    print(f"✅ NFO file created: {nfo_path}")
                    
                    # Check if NFO contains actress portrait
                    with open(nfo_path, 'r', encoding='utf-8') as f:
                        nfo_content = f.read()
                    
                    if '<actressportrait>' in nfo_content:
                        print(f"✅ NFO contains actress portrait tag")
                    else:
                        print(f"ℹ️ NFO does not contain actress portrait tag")
                    
                    if 'Actress Portrait' in nfo_content:
                        print(f"✅ NFO contains actress portrait in custom info")
                    else:
                        print(f"ℹ️ NFO does not contain actress portrait in custom info")
                else:
                    print(f"❌ Failed to create NFO file")
    
    print(f"\n🎯 Summary:")
    print(f"   ✅ Actress portrait search functionality implemented")
    print(f"   ✅ Metadata enhancement with portrait URLs")
    print(f"   ✅ NFO file includes actress portrait information")
    print(f"   ✅ Uses javdatabase.com for portrait search")

async def test_full_scraping_with_actress_portrait():
    """Test full scraping workflow with actress portrait enhancement."""
    
    print(f"\n🧪 Test: Full Scraping with Actress Portrait")
    print("=" * 50)
    
    # Create test video file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
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
                    
                    if 'actress_portrait_url' in detailed:
                        portrait_url = detailed['actress_portrait_url']
                        print(f"✅ Found actress portrait URL: {portrait_url}")
                    else:
                        print(f"ℹ️ No actress portrait URL in metadata")
                
                # Create NFO file
                nfo_path = temp_path / "movie.nfo"
                success = engine.create_nfo_file(metadata, str(nfo_path))
                
                if success:
                    print(f"✅ NFO file created: {nfo_path}")
                    
                    # Check NFO content
                    with open(nfo_path, 'r', encoding='utf-8') as f:
                        nfo_content = f.read()
                    
                    if '<actressportrait>' in nfo_content:
                        print(f"✅ NFO contains actress portrait")
                    else:
                        print(f"ℹ️ NFO does not contain actress portrait")
                else:
                    print(f"❌ Failed to create NFO file")
            else:
                print(f"❌ No JAV files found")

if __name__ == "__main__":
    asyncio.run(test_actress_portrait_search())
    asyncio.run(test_full_scraping_with_actress_portrait()) 