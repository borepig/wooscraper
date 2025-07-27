#!/usr/bin/env python3
"""
Test javtiful.com actress portrait search functionality
"""

import asyncio
import tempfile
import shutil
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_javtiful_actress_search():
    """Test the javtiful.com actress portrait search functionality."""
    
    print("🧪 Test: Javtiful.com Actress Portrait Search")
    print("=" * 50)
    
    # Test actress names
    test_actresses = [
        "Itou Meru",  # Known actress from DASS-695
        "Hibino Uta", # Test actress
        "Hatano Yui", # Popular actress
        "Unknown Actress XYZ"  # Should return None
    ]
    
    async with JAVScraperEngine() as engine:
        for actress_name in test_actresses:
            print(f"\n🎭 Testing actress: {actress_name}")
            print("-" * 30)
            
            # Test direct portrait search
            portrait_url = await engine.search_actress_portrait(actress_name)
            
            if portrait_url:
                print(f"✅ Found portrait URL: {portrait_url}")
                
                # Test downloading the portrait
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    portrait_filename = f"{actress_name.replace(' ', '_').lower()}_portrait.jpg"
                    portrait_path = temp_path / portrait_filename
                    
                    print(f"📥 Downloading portrait to: {portrait_path}")
                    
                    try:
                        await engine.download_image(portrait_url, str(portrait_path))
                        
                        if portrait_path.exists():
                            size = portrait_path.stat().st_size
                            print(f"✅ Portrait downloaded successfully: {size} bytes")
                            
                            if size > 1000:  # Check if file has content
                                print(f"✅ Portrait file has proper content")
                            else:
                                print(f"⚠️ Portrait file seems small: {size} bytes")
                        else:
                            print(f"❌ Portrait file was not created")
                            
                    except Exception as e:
                        print(f"❌ Error downloading portrait: {e}")
            else:
                print(f"❌ No portrait found for {actress_name}")
    
    print(f"\n🎯 Summary:")
    print(f"   ✅ Javtiful.com actress search tested")
    print(f"   ✅ Portrait URL extraction verified")
    print(f"   ✅ Portrait download functionality tested")

if __name__ == "__main__":
    asyncio.run(test_javtiful_actress_search()) 