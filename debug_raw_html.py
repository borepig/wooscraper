#!/usr/bin/env python3
"""
Debug script to show raw HTML from Playwright
"""

import asyncio
import logging
from playwright.async_api import async_playwright

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

async def debug_raw_html():
    """Show raw HTML from jav.guru search."""
    test_code = "DASS-695"  # Test code
    
    print(f"🔍 Fetching raw HTML for search: {test_code}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Set user agent to look like a real browser
        await page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        url = f"https://jav.guru/?s={test_code}"
        print(f"📡 URL: {url}")
        
        # Navigate to the page
        await page.goto(url, wait_until='networkidle', timeout=30000)
        print(f"✅ Page loaded successfully")
        
        # Get the HTML content
        html = await page.content()
        print(f"📄 HTML length: {len(html)} characters")
        
        # Save HTML to file for inspection
        with open('debug_raw_html.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"💾 Raw HTML saved to: debug_raw_html.html")
        print(f"🔍 You can open this file in a browser to inspect the structure")
        
        # Also show first 2000 characters
        print(f"\n📋 First 2000 characters of HTML:")
        print("=" * 50)
        print(html[:2000])
        print("=" * 50)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_raw_html()) 