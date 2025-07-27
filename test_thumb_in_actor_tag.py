#!/usr/bin/env python3
"""
Test thumb tag placement inside actor tags
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_thumb_in_actor_tag():
    """Test that thumb tag is placed inside each actress's actor tag."""
    
    print("🧪 Test: Thumb Tag Inside Actor Tag")
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
                
                # Check for actor tags with thumb
                import re
                actor_pattern = r'<actor>\s*<name>(.*?)</name>\s*<role>(.*?)</role>\s*<order>(.*?)</order>\s*(?:<thumb>(.*?)</thumb>)?\s*</actor>'
                actor_matches = re.findall(actor_pattern, nfo_content, re.DOTALL)
                
                print(f"\n🎭 Found {len(actor_matches)} actor tags:")
                for i, match in enumerate(actor_matches):
                    name, role, order, thumb = match
                    print(f"  Actor {i+1}:")
                    print(f"    Name: {name.strip()}")
                    print(f"    Role: {role.strip()}")
                    print(f"    Order: {order.strip()}")
                    if thumb:
                        print(f"    Thumb: {thumb.strip()}")
                        print(f"    ✅ Thumb tag found!")
                    else:
                        print(f"    ❌ No thumb tag found")
                
                # Check if thumb tag is inside actor tag
                if '<thumb>' in nfo_content:
                    print(f"\n✅ Thumb tag found in NFO")
                    # Check if it's inside actor tag
                    if '<actor>' in nfo_content and '<thumb>' in nfo_content:
                        # Find the position of thumb tag relative to actor tag
                        actor_pos = nfo_content.find('<actor>')
                        thumb_pos = nfo_content.find('<thumb>')
                        if thumb_pos > actor_pos:
                            print(f"✅ Thumb tag appears after actor tag")
                        else:
                            print(f"❌ Thumb tag appears before actor tag")
                else:
                    print(f"\n❌ No thumb tag found in NFO")
                
                # Show the relevant section of NFO
                print(f"\n📄 Relevant NFO section:")
                lines = nfo_content.split('\n')
                for i, line in enumerate(lines):
                    if '<actor>' in line or '<thumb>' in line or '</actor>' in line:
                        print(f"  {i+1:3d}: {line}")
                
            else:
                print(f"❌ NFO file was not created")

if __name__ == "__main__":
    asyncio.run(test_thumb_in_actor_tag()) 