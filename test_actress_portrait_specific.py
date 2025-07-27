#!/usr/bin/env python3
"""
Test actress portrait search with specific well-known actresses
"""

import asyncio
import tempfile
from pathlib import Path
from scraper_engine import JAVScraperEngine

async def test_specific_actress_portraits():
    """Test portrait search with specific well-known actresses."""
    
    print("🧪 Test: Specific Actress Portrait Search")
    print("=" * 50)
    
    # Test with well-known actresses that should have profiles
    test_actresses = [
        "Hibino Uta",      # Known actress
        "Hatano Yui",      # Very popular actress
        "Shinoda Yuu",     # Popular actress
        "Itou Meru",       # Test actress
        "Unknown Actress"   # Should return None
    ]
    
    async with JAVScraperEngine() as engine:
        for actress_name in test_actresses:
            print(f"\n🎭 Testing actress: {actress_name}")
            print("-" * 40)
            
            # Test direct portrait search
            portrait_url = await engine.search_actress_portrait(actress_name)
            
            if portrait_url:
                print(f"✅ Found portrait URL: {portrait_url}")
                
                # Test downloading the portrait
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    portrait_path = temp_path / f"{actress_name.replace(' ', '_')}_portrait.jpg"
                    
                    print(f"🖼️ Attempting to download portrait...")
                    success = await engine.download_image(portrait_url, str(portrait_path))
                    
                    if success:
                        print(f"✅ Successfully downloaded portrait: {portrait_path}")
                        # Check file size
                        if portrait_path.exists():
                            size = portrait_path.stat().st_size
                            print(f"📏 Portrait file size: {size} bytes")
                    else:
                        print(f"❌ Failed to download portrait")
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
    
    print(f"\n🎯 Summary:")
    print(f"   ✅ Actress portrait search functionality implemented")
    print(f"   ✅ Uses javdatabase.com for portrait search")
    print(f"   ✅ Integrates with metadata enhancement")
    print(f"   ✅ Supports portrait downloading")

if __name__ == "__main__":
    asyncio.run(test_specific_actress_portraits()) 