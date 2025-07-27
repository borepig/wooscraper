#!/usr/bin/env python3
"""
Debug script to test JAV scraper functionality
"""

import asyncio
import logging
from scraper_engine import JAVScraperEngine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def test_scraper():
    """Test the scraper with a sample JAV code."""
    test_code = "DASS-695"  # More realistic JAV code
    
    print(f"🔍 Testing scraper with code: {test_code}")
    
    async with JAVScraperEngine() as engine:
        print("✅ Engine initialized")
        
        # Test scraping
        print(f"📡 Scraping metadata for {test_code}...")
        metadata = await engine.scrape_all_sites(test_code)
        
        print(f"📋 Metadata result:")
        print(f"  - JAV Code: {metadata.get('jav_code')}")
        print(f"  - Best Title: {metadata.get('best_title')}")
        print(f"  - Best Cover: {metadata.get('best_cover')}")
        print(f"  - Sources: {list(metadata.get('sources', {}).keys())}")
        
        # Print detailed source information
        for source_name, source_data in metadata.get('sources', {}).items():
            print(f"  📋 {source_name}:")
            if source_data:
                print(f"    - Title: {source_data.get('title')}")
                print(f"    - Cover URL: {source_data.get('cover_url')}")
                print(f"    - Details: {source_data.get('details', {})}")
            else:
                print(f"    - No data")
        
        # Test image download if we have a cover URL
        if metadata.get('best_cover'):
            print(f"🖼️ Testing image download...")
            test_path = f"test_cover_{test_code}.jpg"
            success = await engine.download_image(metadata['best_cover'], test_path)
            print(f"  - Download success: {success}")
            if success:
                print(f"  - Image saved to: {test_path}")
        else:
            print("⚠️ No cover URL found to test download")

if __name__ == "__main__":
    asyncio.run(test_scraper()) 