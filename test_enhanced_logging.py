#!/usr/bin/env python3
"""
Test script to verify enhanced logging functionality
"""

import asyncio
import logging
from scraper_engine import JAVScraperEngine

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_enhanced_logging():
    """Test enhanced logging with STKO-005."""
    print("🧪 Testing enhanced logging functionality...")
    
    async with JAVScraperEngine() as engine:
        jav_code = "STKO-005"
        print(f"🔍 Testing JAV code: {jav_code}")
        
        # Test the full scraping workflow with enhanced logging
        result = await engine.scrape_all_sites(jav_code)
        
        if result:
            print("✅ Enhanced logging test successful!")
            print(f"📋 Source: {result.get('source', 'N/A')}")
            print(f"📋 Title: {result.get('title', 'N/A')}")
            
            detailed_metadata = result.get('detailed_metadata', {})
            print(f"📋 Studio: {detailed_metadata.get('studio', 'N/A')}")
            print(f"📋 Actresses: {detailed_metadata.get('actress', 'N/A')}")
            print(f"📋 Poster URL: {detailed_metadata.get('poster_url', 'N/A')}")
            print(f"📋 Fanart URL: {detailed_metadata.get('fanart_url', 'N/A')}")
        else:
            print("❌ Enhanced logging test failed")

if __name__ == "__main__":
    asyncio.run(test_enhanced_logging()) 