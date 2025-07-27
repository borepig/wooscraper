#!/usr/bin/env python3
"""
Test that no actressportrait tag is added to NFO files
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_no_actressportrait_tag():
    """Test that no actressportrait tag is added to NFO files."""
    
    print("🧪 Test: No Actressportrait Tag in NFO")
    print("=" * 50)
    
    # Create test directory with video file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test video file
        test_video = temp_path / "DASS-695.mp4"
        test_video.touch()
        
        print(f"📁 Test directory: {temp_path}")
        print(f"🎬 Test video: {test_video}")
        
        # Create test metadata with known actress and portrait
        test_metadata = {
            'jav_code': 'DASS-695',
            'detailed_metadata': {
                'actress': 'Itou Meru',
                'thumb_url': 'https://javtiful.com/actress/thumb/itou-meru.jpg'
            },
            'all_details': {
                'Title': 'Test Movie',
                'Actress': 'Itou Meru'
            }
        }
        
        async with JAVScraperEngine() as engine:
            # Create NFO file
            nfo_path = temp_path / "DASS-695.nfo"
            engine.create_nfo_file(test_metadata, str(nfo_path))
            
            # Read and analyze NFO content
            if nfo_path.exists():
                with open(nfo_path, 'r', encoding='utf-8') as f:
                    nfo_content = f.read()
                
                print(f"\n📄 NFO file created: {nfo_path}")
                print(f"📄 NFO content length: {len(nfo_content)} characters")
                
                # Check for actressportrait tag
                if '<actressportrait>' in nfo_content:
                    print(f"❌ NFO contains <actressportrait> tag - THIS SHOULD NOT HAPPEN!")
                    # Extract actressportrait content
                    import re
                    actressportrait_match = re.search(r'<actressportrait>(.*?)</actressportrait>', nfo_content)
                    if actressportrait_match:
                        actressportrait_url = actressportrait_match.group(1)
                        print(f"🎭 Actress Portrait URL in NFO: {actressportrait_url}")
                else:
                    print(f"✅ NFO does not contain <actressportrait> tag - GOOD!")
                
                # Check for thumb tag
                if '<thumb>' in nfo_content:
                    print(f"✅ NFO contains <thumb> tag - GOOD!")
                    # Extract thumb content
                    import re
                    thumb_match = re.search(r'<thumb>(.*?)</thumb>', nfo_content)
                    if thumb_match:
                        thumb_url = thumb_match.group(1)
                        print(f"🎭 Thumb URL in NFO: {thumb_url}")
                else:
                    print(f"❌ NFO does not contain <thumb> tag")
                
                # Show the relevant section of NFO
                print(f"\n📄 Relevant NFO section:")
                lines = nfo_content.split('\n')
                for i, line in enumerate(lines):
                    if '<actor>' in line or '<thumb>' in line or '</actor>' in line:
                        print(f"  {i+1:3d}: {line}")
                
            else:
                print(f"❌ NFO file was not created")

if __name__ == "__main__":
    asyncio.run(test_no_actressportrait_tag()) 