#!/usr/bin/env python3
"""
Test script to debug cover download issues and test scraping functionality
"""

import asyncio
import aiohttp
import logging
from bs4 import BeautifulSoup
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def test_javbus_scraping(jav_code: str):
    """Test JavBus scraping specifically."""
    print(f"\n🔍 Testing JavBus scraping for {jav_code}")
    
    async with aiohttp.ClientSession() as session:
        url = f"https://www.javbus.com/{jav_code}"
        print(f"📡 Fetching: {url}")
        
        try:
            async with session.get(url) as response:
                print(f"📊 Status: {response.status}")
                
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Test different cover image selectors
                    selectors = [
                        ('img', {'class': 'bigImage'}),
                        ('img', {'id': 'video_jacket_img'}),
                        ('img', {'class': 'jacket'}),
                        ('img', {'class': 'cover'}),
                        ('img', {'alt': lambda x: x and 'cover' in x.lower()}),
                        ('img', {'src': lambda x: x and ('jpg' in x or 'png' in x)})
                    ]
                    
                    print("\n🔍 Testing cover image selectors:")
                    for selector_name, selector in selectors:
                        elements = soup.find_all(selector_name, selector)
                        print(f"  {selector_name}: {len(elements)} found")
                        for i, elem in enumerate(elements[:3]):  # Show first 3
                            src = elem.get('src', 'NO_SRC')
                            alt = elem.get('alt', 'NO_ALT')
                            print(f"    {i+1}. src='{src}' alt='{alt}'")
                    
                    # Test title extraction
                    title_selectors = [
                        'h3',
                        'h1',
                        'title',
                        ('span', {'class': 'title'}),
                        ('div', {'class': 'title'})
                    ]
                    
                    print("\n🔍 Testing title selectors:")
                    for selector in title_selectors:
                        if isinstance(selector, str):
                            elements = soup.find_all(selector)
                        else:
                            elements = soup.find_all(selector[0], selector[1])
                        
                        print(f"  {selector}: {len(elements)} found")
                        for i, elem in enumerate(elements[:2]):
                            text = elem.get_text().strip()
                            print(f"    {i+1}. '{text[:50]}...'")
                    
                    # Test table extraction
                    tables = soup.find_all('table')
                    print(f"\n📋 Found {len(tables)} tables")
                    for i, table in enumerate(tables):
                        rows = table.find_all('tr')
                        print(f"  Table {i+1}: {len(rows)} rows")
                        
                else:
                    print(f"❌ Failed to fetch: {response.status}")
                    
        except Exception as e:
            print(f"❌ Error: {e}")

async def test_javlibrary_scraping(jav_code: str):
    """Test JavLibrary scraping specifically."""
    print(f"\n🔍 Testing JavLibrary scraping for {jav_code}")
    
    async with aiohttp.ClientSession() as session:
        url = f"https://www.javlibrary.com/cn/?v={jav_code}"
        print(f"📡 Fetching: {url}")
        
        try:
            async with session.get(url) as response:
                print(f"📊 Status: {response.status}")
                
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Test cover image extraction
                    cover_elem = soup.find('img', {'id': 'video_jacket_img'})
                    if cover_elem:
                        cover_url = cover_elem.get('src')
                        print(f"✅ Found cover: {cover_url}")
                    else:
                        print("❌ No cover found with id='video_jacket_img'")
                        
                        # Try alternative selectors
                        alt_selectors = [
                            ('img', {'class': 'jacket'}),
                            ('img', {'class': 'cover'}),
                            ('img', {'alt': lambda x: x and 'cover' in x.lower()})
                        ]
                        
                        for selector_name, selector in alt_selectors:
                            elements = soup.find_all('img', selector)
                            print(f"  {selector_name}: {len(elements)} found")
                            for elem in elements[:2]:
                                src = elem.get('src', 'NO_SRC')
                                print(f"    src='{src}'")
                    
                    # Test title extraction
                    title_elem = soup.find('h3', {'class': 'post-title'})
                    if title_elem:
                        title = title_elem.get_text().strip()
                        print(f"✅ Found title: {title[:50]}...")
                    else:
                        print("❌ No title found")
                        
                else:
                    print(f"❌ Failed to fetch: {response.status}")
                    
        except Exception as e:
            print(f"❌ Error: {e}")

async def test_image_download(url: str, save_path: str):
    """Test image download functionality."""
    print(f"\n📥 Testing image download: {url}")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                print(f"📊 Status: {response.status}")
                print(f"📏 Content-Type: {response.headers.get('content-type', 'unknown')}")
                print(f"📏 Content-Length: {response.headers.get('content-length', 'unknown')}")
                
                if response.status == 200:
                    content = await response.read()
                    print(f"📦 Downloaded {len(content)} bytes")
                    
                    # Save the image
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    print(f"💾 Saved to: {save_path}")
                    
                    # Check if file exists and has content
                    if Path(save_path).exists():
                        size = Path(save_path).stat().st_size
                        print(f"✅ File saved successfully: {size} bytes")
                    else:
                        print("❌ File not saved")
                        
                else:
                    print(f"❌ Download failed: {response.status}")
                    
        except Exception as e:
            print(f"❌ Error downloading: {e}")

async def main():
    """Main test function."""
    print("🚀 JAV Scraper - Cover Download Test")
    print("=" * 50)
    
    # Test with a known JAV code
    test_codes = ["WANZ-295", "DASS-695", "ABC-123"]
    
    for jav_code in test_codes:
        print(f"\n{'='*20} Testing {jav_code} {'='*20}")
        
        # Test JavBus
        await test_javbus_scraping(jav_code)
        
        # Test JavLibrary
        await test_javlibrary_scraping(jav_code)
        
        # Test image download if we found a cover URL
        # (This would be implemented based on the scraping results)
        
    print(f"\n{'='*20} Test Complete {'='*20}")

if __name__ == "__main__":
    asyncio.run(main()) 