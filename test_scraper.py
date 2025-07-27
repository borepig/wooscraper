#!/usr/bin/env python3
"""
Test script for JAV Scraper
Tests the core functionality of the scraper engine
"""

import asyncio
import os
import tempfile
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_jav_code_extraction():
    """Test JAV code extraction from filenames."""
    print("🧪 Testing JAV code extraction...")
    
    engine = JAVScraperEngine()
    
    test_cases = [
        ("ABC-1234.mp4", "ABC-1234"),
        ("ABC1234.mp4", "ABC-1234"),
        ("ABC_1234.mp4", "ABC-1234"),
        ("DEF-567.avi", "DEF-567"),
        ("GHI-890.mkv", "GHI-890"),
        ("invalid.mp4", None),
        ("ABC123.mp4", "ABC-123"),
    ]
    
    passed = 0
    total = len(test_cases)
    
    for filename, expected in test_cases:
        result = engine.extract_jav_code(filename)
        if result == expected:
            print(f"✅ {filename} -> {result}")
            passed += 1
        else:
            print(f"❌ {filename} -> {result} (expected: {expected})")
    
    print(f"\n📊 Extraction test: {passed}/{total} passed")
    return passed == total

def test_folder_scanning():
    """Test folder scanning functionality."""
    print("\n🧪 Testing folder scanning...")
    
    engine = JAVScraperEngine()
    
    # Create temporary test folder
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create test files
        test_files = [
            "ABC-1234.mp4",
            "DEF-567.avi",
            "GHI-890.mkv",
            "invalid.txt",
            "JKL-123.mp4"
        ]
        
        for filename in test_files:
            (temp_path / filename).touch()
        
        # Scan folder
        results = engine.scan_folder(str(temp_path))
        
        print(f"📁 Found {len(results)} JAV files:")
        for result in results:
            print(f"  ✅ {result['filename']} -> {result['jav_code']}")
        
        expected_count = 4  # 4 valid JAV files
        success = len(results) == expected_count
        
        print(f"\n📊 Scanning test: {'✅ PASSED' if success else '❌ FAILED'}")
        return success

async def test_scraping():
    """Test scraping functionality."""
    print("\n🧪 Testing scraping functionality...")
    
    async with JAVScraperEngine() as engine:
        # Test with a sample JAV code
        test_code = "ABC-123"
        
        print(f"🔍 Testing scraping for: {test_code}")
        
        try:
            result = await engine.scrape_all_sites(test_code)
            
            print(f"📊 Scraping results:")
            print(f"  - JAV Code: {result.get('jav_code', 'N/A')}")
            print(f"  - Best Title: {result.get('best_title', 'N/A')}")
            print(f"  - Sources: {list(result.get('sources', {}).keys())}")
            
            # Check if we got any results
            success = len(result.get('sources', {})) > 0
            print(f"\n📊 Scraping test: {'✅ PASSED' if success else '❌ FAILED'}")
            return success
            
        except Exception as e:
            print(f"❌ Scraping error: {e}")
            return False

def test_config_loading():
    """Test configuration loading."""
    print("\n🧪 Testing configuration loading...")
    
    try:
        engine = JAVScraperEngine()
        
        # Check if config loaded
        if engine.config:
            print("✅ Configuration loaded successfully")
            print(f"  - Sites configured: {len(engine.config.get('scraper', {}).get('sites', []))}")
            print(f"  - Max threads: {engine.config.get('scraper', {}).get('max_threads', 'N/A')}")
            return True
        else:
            print("❌ Configuration failed to load")
            return False
            
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 JAV Scraper - Test Suite")
    print("=" * 40)
    
    tests = [
        ("Configuration Loading", test_config_loading),
        ("JAV Code Extraction", test_jav_code_extraction),
        ("Folder Scanning", test_folder_scanning),
        ("Scraping Functionality", test_scraping),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*50}")
    print("📊 TEST SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The scraper is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Please check the configuration and dependencies.")
        return False

if __name__ == "__main__":
    asyncio.run(main()) 