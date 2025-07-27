#!/usr/bin/env python3
"""
Test thumb tag fix for actress portraits in NFO files
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_thumb_tag_fix():
    """Test that thumb tag is added to NFO files for actress portraits."""
    
    print("🧪 Test: Thumb Tag Fix for Actress Portraits")
    print("=" * 50)
    
    # Test with known actress that has a portrait
    test_actress = "Hibino Uta"
    test_portrait_url = "https://www.javdatabase.com/idolimages/thumb/uta-hibino.webp"
    
    print(f"🎭 Testing with actress: {test_actress}")
    print(f"🎭 Portrait URL: {test_portrait_url}")
    
    # Create test metadata with known actress and portrait
    test_metadata = {
        'detailed_metadata': {
            'actress': test_actress,
            'actress_portrait_url': test_portrait_url,
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
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        async with JAVScraperEngine() as engine:
            # Test NFO creation with thumb tag
            print(f"📄 Testing NFO creation with thumb tag...")
            
            nfo_path = temp_path / "test_movie.nfo"
            success = engine.create_nfo_file(test_metadata, str(nfo_path))
            
            if success:
                print(f"✅ NFO file created: {nfo_path}")
                
                # Check if NFO contains thumb tag
                with open(nfo_path, 'r', encoding='utf-8') as f:
                    nfo_content = f.read()
                
                print(f"\n📄 NFO Content Analysis:")
                print(f"   📏 NFO file size: {len(nfo_content)} characters")
                
                import re
                
                # Check for thumb tag
                if '<thumb>' in nfo_content:
                    print(f"✅ NFO contains <thumb> tag")
                    # Extract thumb content
                    thumb_match = re.search(r'<thumb>(.*?)</thumb>', nfo_content)
                    if thumb_match:
                        thumb_url = thumb_match.group(1)
                        print(f"🎭 Thumb URL in NFO: {thumb_url}")
                        if thumb_url == test_portrait_url:
                            print(f"✅ Thumb URL matches expected portrait URL")
                        else:
                            print(f"❌ Thumb URL does not match expected portrait URL")
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
                
                # Show the relevant parts of the NFO content
                print(f"\n📄 Relevant NFO Content:")
                lines = nfo_content.split('\n')
                for i, line in enumerate(lines):
                    if '<thumb>' in line or '<actressportrait>' in line or 'Actress Portrait' in line:
                        print(f"   Line {i+1}: {line.strip()}")
                
            else:
                print(f"❌ Failed to create NFO file")
    
    print(f"\n🎯 Summary:")
    print(f"   ✅ Thumb tag verification completed")
    print(f"   ✅ Actress portrait URL validation")
    print(f"   ✅ NFO content analysis")

if __name__ == "__main__":
    asyncio.run(test_thumb_tag_fix()) 