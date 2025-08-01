import re
import os
import asyncio
import aiohttp
import yaml
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path
import json
from datetime import datetime
from PIL import Image
from playwright.async_api import async_playwright
import urllib.parse
import tempfile

class JAVScraperEngine:
    def __init__(self, config_path: str = "config.yml"):
        """Initialize the JAV scraper engine."""
        self.config = self._load_config(config_path)
        self.setup_logging()
        self.session = None
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logging.error(f"Config file {config_path} not found")
            return {}
            
    def setup_logging(self):
        """Setup logging configuration."""
        log_config = self.config.get('logging', {})
        logging.basicConfig(
            level=getattr(logging, log_config.get('level', 'INFO')),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_config.get('file', 'scraper.log')),
                logging.StreamHandler()
            ]
        )
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.get('scraper', {}).get('timeout', 30))
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            
    def extract_jav_code(self, filename: str) -> Optional[str]:
        """
        Extract JAV code from filename.
        Pattern: XXXX-NNNN where XXXX is letters and NNNN is numbers
        """
        # Remove file extension
        name_without_ext = os.path.splitext(filename)[0]
        
        # Pattern for JAV codes: letters-numbers (e.g., ABC-1234, ABC1234, ABC-123)
        patterns = [
            r'([A-Z]{2,5})-?(\d{2,5})',  # ABC-1234, ABC1234
            r'([A-Z]{2,5})[-_](\d{2,5})',  # ABC_1234
            r'([A-Z]{2,5})(\d{2,5})',  # ABC1234
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name_without_ext.upper())
            if match:
                prefix, number = match.groups()
                return f"{prefix}-{number}"
                
        return None
        
    def clean_actress_name(self, actress_name: str) -> str:
        """
        Clean actress name by removing Japanese characters and keeping only English/Romanized names.
        Examples:
        - "Miku Abeno 阿部乃みく" -> "Miku Abeno"
        - "Yui Hatano 波多野結衣" -> "Yui Hatano"
        - "Asahi Mizuno 水野朝陽" -> "Asahi Mizuno"
        """
        if not actress_name:
            return ""
            
        # Remove Japanese characters (Hiragana, Katakana, Kanji)
        # Japanese Unicode ranges:
        # Hiragana: 3040-309F
        # Katakana: 30A0-30FF
        # Kanji: 4E00-9FAF
        # Full-width characters: FF00-FFEF
        cleaned_name = re.sub(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\uFF00-\uFFEF]', '', actress_name)
        
        # Remove any remaining parentheses and their contents
        cleaned_name = re.sub(r'\s*\([^)]*\)', '', cleaned_name)
        
        # Remove extra whitespace and normalize
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        
        # Remove any remaining special characters that might be left
        cleaned_name = re.sub(r'[^\w\s\-\.]', '', cleaned_name)
        
        # Final cleanup of extra spaces
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        
        return cleaned_name
        
    def scan_folder(self, folder_path: str) -> List[Dict]:
        """Scan folder for video files and extract JAV codes."""
        video_extensions = self.config.get('scraper', {}).get('video_extensions', ['.mp4', '.avi', '.mkv'])
        results = []
        
        folder = Path(folder_path)
        if not folder.exists():
            logging.error(f"Folder {folder_path} does not exist")
            return results
            
        for file_path in folder.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                jav_code = self.extract_jav_code(file_path.name)
                if jav_code:
                    results.append({
                        'file_path': str(file_path),
                        'filename': file_path.name,
                        'jav_code': jav_code,
                        'folder': str(file_path.parent)
                    })
                    
        return results
        
    async def fetch_html_with_playwright(self, url: str) -> Optional[str]:
        """Fetch HTML content using Playwright to bypass bot detection."""
        try:
            logging.info(f"🌐 Using Playwright to fetch: {url}")
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
                
                # Navigate to the page
                await page.goto(url, wait_until='networkidle', timeout=30000)
                logging.info(f"✅ Page loaded successfully")
                
                # Get the HTML content
                html = await page.content()
                logging.info(f"📄 Retrieved HTML length: {len(html)} characters")
                
                await browser.close()
                return html
        except Exception as e:
            logging.error(f"❌ Error fetching HTML with Playwright: {e}")
            return None

    async def scrape_javguru(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JavGuru using Playwright to bypass bot detection."""
        try:
            logging.info(f"🔍 Starting JavGuru scrape for {jav_code}")
            url = f"https://jav.guru/?s={jav_code}"
            
            logging.info(f"📡 Requesting URL with Playwright: {url}")
            html = await self.fetch_html_with_playwright(url)
            if not html:
                logging.warning(f"❌ Failed to fetch HTML with Playwright for {jav_code}")
                return None
            soup = BeautifulSoup(html, 'html.parser')
            # Find the first result
            article = soup.select_one('div.inside-article')
            if not article:
                logging.warning(f"⚠️ No search results found for {jav_code}")
                return None
            # Detail page link
            link_tag = article.select_one('div.imgg a')
            detail_url = link_tag['href'] if link_tag and link_tag.has_attr('href') else None
            # Cover image
            img_tag = link_tag.find('img') if link_tag else None
            cover_url = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
            # Title
            title_tag = article.select_one('div.grid1 h2 a')
            title = title_tag['title'] if title_tag and title_tag.has_attr('title') else (title_tag.text.strip() if title_tag else None)
            # Tags
            tags = [a.text for a in article.select('div.grid3 p.tags a')]
            # Stats
            stats = article.select_one('div.javstats')
            stats_text = stats.text.strip() if stats else ""
            # Date
            date_tag = article.select_one('div.date')
            date = date_tag.text.strip() if date_tag else ""
            # Now fetch the detail page for comprehensive metadata
            if detail_url:
                logging.info(f"🔗 Fetching detail page: {detail_url}")
                detail_html = await self.fetch_html_with_playwright(detail_url)
                
                if detail_html:
                    logging.info(f"📄 Detail page HTML length: {len(detail_html)} characters")
                    
                    # Parse detail page for comprehensive metadata
                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                    
                    # Extract detailed metadata
                    detailed_metadata = self._extract_detailed_metadata(detail_soup, jav_code)
                    
                    # Merge search result with detailed metadata
                    # Use fanart URL as the primary image source
                    fanart_url = detailed_metadata.get('fanart_url', cover_url)
                    
                    result = {
                        'title': title,
                        'cover_url': cover_url,  # Keep original cover for fallback
                        'fanart_url': fanart_url,  # Use large image as fanart
                        'detail_url': detail_url,
                        'tags': tags,
                        'stats': stats_text,
                        'date': date,
                        'detail_html': detail_html,  # Include the full HTML for parsing
                        'detailed_metadata': detailed_metadata,  # Add comprehensive metadata
                        'source': 'javguru'
                    }
                    logging.info(f"✅ JavGuru scrape completed for {jav_code}")
                    return result
                else:
                    logging.warning(f"❌ Failed to fetch detail page for {jav_code}")
            
            # Return search result only if detail page failed
            result = {
                'title': title,
                'cover_url': cover_url,
                'detail_url': detail_url,
                'tags': tags,
                'stats': stats_text,
                'date': date,
                'source': 'javguru'
            }
            logging.info(f"✅ JavGuru scrape completed for {jav_code} (search results only)")
            return result
        except Exception as e:
            logging.error(f"❌ Error scraping JavGuru for {jav_code}: {e}")
            return None

    def _extract_detailed_metadata(self, soup, jav_code):
        """Extract comprehensive metadata from detail page."""
        try:
            metadata = {}
            
            # Find the infoleft section containing movie information
            infoleft = soup.find('div', class_='infoleft')
            if not infoleft:
                logging.warning(f"⚠️ Could not find infoleft section for {jav_code}")
                return metadata
            
            # Extract all list items from the movie information section
            info_items = infoleft.find_all('li')
            
            for item in info_items:
                # Get the strong tag which contains the field name
                strong_tag = item.find('strong')
                if not strong_tag:
                    continue
                
                # Extract field name (remove any span tags and get clean text)
                field_name = strong_tag.get_text(strip=True).replace(':', '').lower()
                
                # Extract field value (everything after the strong tag)
                field_value = item.get_text()
                # Remove the field name from the value
                if ':' in field_value:
                    field_value = field_value.split(':', 1)[1].strip()
                
                # Clean up the field name
                field_name = field_name.replace(' ', '_').replace('-', '_')
                
                # Clean actress names if this is an actress-related field
                if field_name in ['actress', 'actresses', 'cast', 'star', 'stars']:
                    original_value = field_value
                    field_value = self.clean_actress_name(field_value)
                    logging.info(f"📋 Extracted {field_name}: {original_value} -> {field_value}")
                else:
                    logging.info(f"📋 Extracted {field_name}: {field_value}")
                
                # Store the metadata
                metadata[field_name] = field_value
            
            # Also extract the main title from the page
            title_tag = soup.find('h1', class_='titl')
            if title_tag:
                metadata['full_title'] = title_tag.get_text(strip=True)
                logging.info(f"📋 Extracted full_title: {metadata['full_title']}")
            
            # Extract cover image from the large screenshot (this will be used as fanart)
            large_screenshot = soup.find('div', class_='large-screenshot')
            if large_screenshot:
                img_tag = large_screenshot.find('img')
                if img_tag and img_tag.get('src'):
                    metadata['fanart_url'] = img_tag['src']  # Use as fanart
                    metadata['large_cover_url'] = img_tag['src']  # Keep for compatibility
                    logging.info(f"📋 Extracted fanart_url: {metadata['fanart_url']}")
            
            # Extract plot/synopsis from wp-content
            wp_content = soup.find('div', class_='wp-content')
            if wp_content:
                paragraphs = wp_content.find_all('p')
                plot_text = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and not text.startswith('http'):  # Skip image URLs
                        plot_text.append(text)
                
                if plot_text:
                    metadata['plot'] = ' '.join(plot_text)
                    logging.info(f"📋 Extracted plot: {metadata['plot'][:100]}...")
            
            logging.info(f"✅ Extracted {len(metadata)} detailed metadata fields for {jav_code}")
            return metadata
            
        except Exception as e:
            logging.error(f"❌ Error extracting detailed metadata for {jav_code}: {e}")
            return {}

    async def scrape_fallback(self, jav_code: str) -> Optional[Dict]:
        """Fallback scraper that generates basic metadata when sites are blocked."""
        try:
            logging.info(f"🔄 Using fallback scraper for {jav_code}")
            
            # Generate a basic cover URL using a more reliable service
            # This is just for testing - in a real scenario you'd want to use a proper image service
            cover_url = f"https://picsum.photos/300/450?random={jav_code}"
            
            result = {
                'title': f"{jav_code} - JAV Content",
                'cover_url': cover_url,
                'details': {
                    'Actor': 'Unknown',
                    'Studio': 'Unknown',
                    'Genre': 'Adult, JAV',
                    'Plot': f'JAV content with code {jav_code}',
                    'Runtime': '120',
                    'Release Date': '2024-01-01'
                },
                'source': 'fallback'
            }
            
            logging.info(f"✅ Fallback scraper completed for {jav_code}")
            return result
        except Exception as e:
            logging.error(f"❌ Error in fallback scraper for {jav_code}: {e}")
            return None
        """Scrape metadata from JavGuru."""
        try:
            logging.info(f"🔍 Starting JavGuru scrape for {jav_code}")
            url = f"https://jav.guru/?s={jav_code}"
            
            # Add headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            logging.info(f"📡 Requesting URL: {url}")
            async with self.session.get(url, headers=headers) as response:
                logging.info(f"📊 Response status: {response.status}")
                
                if response.status == 200:
                    html = await response.text()
                    logging.info(f"📄 Received HTML length: {len(html)} characters")
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Since this is a search results page, we need to find the first result
                    # Look for article elements or product cards
                    first_result = soup.find('article') or \
                        soup.find('div', {'class': 'product'}) or \
                        soup.find('div', {'class': 'item'}) or \
                        soup.find('div', {'class': 'result'})
                    
                    if first_result:
                        logging.info(f"✅ Found first result for {jav_code}")
                        
                        # Extract title from the first result
                        title_elem = first_result.find('h2') or first_result.find('h3') or \
                                   first_result.find('a', href=True)
                        title_text = title_elem.get_text().strip() if title_elem else f"{jav_code} - JAV Content"
                        logging.info(f"📝 Title extracted: {title_text}")
                        
                        # Try to find the link to the detailed page
                        detail_link = first_result.find('a', href=True)
                        if detail_link:
                            detail_url = detail_link.get('href')
                            if detail_url.startswith('/'):
                                detail_url = 'https://jav.guru' + detail_url
                            elif not detail_url.startswith('http'):
                                detail_url = 'https://jav.guru/' + detail_url
                            
                            logging.info(f"🔗 Detail URL: {detail_url}")
                            
                            # Now scrape the detailed page
                            async with self.session.get(detail_url, headers=headers) as detail_response:
                                logging.info(f"📊 Detail page status: {detail_response.status}")
                                
                                if detail_response.status == 200:
                                    detail_html = await detail_response.text()
                                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                                    
                                    # Extract cover image from detailed page
                                    cover_url = None
                                    cover_selectors = [
                                        ('img', {'class': 'poster'}),
                                        ('img', {'class': 'cover'}),
                                        ('img', {'class': 'jacket'}),
                                        ('img', {'id': 'poster'}),
                                        ('img', {'alt': lambda x: x and 'cover' in x.lower()}),
                                        ('img', {'src': lambda x: x and ('jpg' in x or 'png' in x) and 'logo' not in x and 'avatar' not in x})
                                    ]
                                    
                                    for selector_name, selector in cover_selectors:
                                        cover_img = detail_soup.find('img', selector)
                                        if cover_img:
                                            cover_url = cover_img.get('src')
                                            if cover_url and 'logo' not in cover_url and 'avatar' not in cover_url:
                                                # Make sure it's a full URL
                                                if cover_url.startswith('//'):
                                                    cover_url = 'https:' + cover_url
                                                elif cover_url.startswith('/'):
                                                    cover_url = 'https://jav.guru' + cover_url
                                                logging.info(f"🖼️ Found cover URL: {cover_url}")
                                                break
                                    
                                    if not cover_url:
                                        logging.warning(f"⚠️ No cover URL found for {jav_code}")
                                    
                                    # Extract details from the detailed page
                                    details = {}
                                    
                                    # Look for actor information
                                    actor_elem = detail_soup.find('a', href=lambda x: x and '/actress/' in x) or \
                                                detail_soup.find('span', text=lambda x: x and 'actress' in x.lower()) or \
                                                detail_soup.find('div', text=lambda x: x and 'actress' in x.lower())
                                    if actor_elem:
                                        details['Actor'] = actor_elem.get_text().strip()
                                        logging.info(f"👤 Actor: {details['Actor']}")
                                    
                                    # Look for studio information
                                    studio_elem = detail_soup.find('a', href=lambda x: x and '/studio/' in x) or \
                                                 detail_soup.find('span', text=lambda x: x and 'studio' in x.lower())
                                    if studio_elem:
                                        details['Studio'] = studio_elem.get_text().strip()
                                        logging.info(f"🏢 Studio: {details['Studio']}")
                                    
                                    # Look for release date
                                    date_elem = detail_soup.find('span', text=lambda x: x and 'date' in x.lower()) or \
                                               detail_soup.find('div', text=lambda x: x and 'date' in x.lower())
                                    if date_elem:
                                        details['Release Date'] = date_elem.get_text().strip()
                                        logging.info(f"📅 Release Date: {details['Release Date']}")
                                    
                                    # Look for runtime/duration
                                    runtime_elem = detail_soup.find('span', text=lambda x: x and ('runtime' in x.lower() or 'duration' in x.lower())) or \
                                                  detail_soup.find('div', text=lambda x: x and ('runtime' in x.lower() or 'duration' in x.lower()))
                                    if runtime_elem:
                                        details['Runtime'] = runtime_elem.get_text().strip()
                                        logging.info(f"⏱️ Runtime: {details['Runtime']}")
                                    
                                    # Look for genre information
                                    genre_elems = detail_soup.find_all('a', href=lambda x: x and '/genre/' in x) or \
                                                 detail_soup.find_all('span', text=lambda x: x and 'genre' in x.lower())
                                    if genre_elems:
                                        genres = [elem.get_text().strip() for elem in genre_elems]
                                        details['Genre'] = ', '.join(genres)
                                        logging.info(f"🎭 Genres: {details['Genre']}")
                                    
                                    # Extract plot/description
                                    plot_elem = detail_soup.find('div', {'class': 'description'}) or \
                                               detail_soup.find('div', {'class': 'plot'}) or \
                                               detail_soup.find('p', text=lambda x: x and len(x) > 50)
                                    if plot_elem:
                                        details['Plot'] = plot_elem.get_text().strip()
                                        logging.info(f"📖 Plot length: {len(details['Plot'])} characters")
                                    
                                    result = {
                                        'title': title_text,
                                        'cover_url': cover_url,
                                        'details': details,
                                        'source': 'javguru'
                                    }
                                    
                                    logging.info(f"✅ JavGuru scrape completed for {jav_code}")
                                    return result
                                else:
                                    logging.warning(f"❌ Detail page returned status {detail_response.status} for {jav_code}")
                        else:
                            logging.warning(f"❌ No detail link found for {jav_code}")
                    
                    # If no detailed page found, return basic info from search results
                    logging.warning(f"⚠️ No detailed page found for {jav_code}, returning basic info")
                    return {
                        'title': f"{jav_code} - JAV Content",
                        'cover_url': None,
                        'details': {'Actor': 'Unknown', 'Studio': 'Unknown'},
                        'source': 'javguru'
                    }
                else:
                    logging.warning(f"❌ JavGuru returned status {response.status} for {jav_code}")
                    return None
        except Exception as e:
            logging.error(f"❌ Error scraping JavGuru for {jav_code}: {e}")
            return None
            

            

            
    async def scrape_all_sites(self, jav_code: str) -> Dict:
        """Scrape metadata from all enabled sites."""
        logging.info(f"🔍 ==== METADATA SCRAPING START ====")
        logging.info(f"🔍 JAV Code: {jav_code}")
        logging.info(f"🔍 Config: {self.config.get('scraper', {})}")
        
        enabled_sites = [site for site in self.config.get('scraper', {}).get('sites', []) if site.get('enabled', True)]
        logging.info(f"🔍 Enabled sites: {[site['name'] for site in enabled_sites]}")
        
        tasks = []
        for site in enabled_sites:
            site_name = site['name']
            if site_name == 'javguru':
                logging.info(f"🌐 Adding JavGuru task for {jav_code}")
                tasks.append(self.scrape_javguru(jav_code))
            elif site_name == 'javtrailers':
                logging.info(f"🌐 Adding JAV Trailers task for {jav_code}")
                tasks.append(self.scrape_javtrailers(jav_code))
                
        logging.info(f"📡 Starting {len(tasks)} scraping tasks")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logging.info(f"📊 Scraping results: {results}")
        
        # Check if all sites failed or returned empty results
        all_failed = True
        for i, result in enumerate(results):
            logging.info(f"📊 Analyzing result {i+1}: {type(result)}")
            if isinstance(result, dict) and result:
                # Check if the result has meaningful data
                has_title = result.get('title') and result.get('title') != 'None'
                has_cover = result.get('cover_url')
                has_actress = result.get('details', {}).get('Actress') or result.get('details', {}).get('Actor')
                
                logging.info(f"📊 Result {i+1} analysis:")
                logging.info(f"   📊 Has title: {has_title} ({result.get('title', 'N/A')})")
                logging.info(f"   📊 Has cover: {has_cover} ({result.get('cover_url', 'N/A')})")
                logging.info(f"   📊 Has actress: {has_actress}")
                
                if has_title or has_cover or has_actress:
                    all_failed = False
                    logging.info(f"✅ Result {i+1} has meaningful data")
                    break
            else:
                logging.warning(f"⚠️ Result {i+1} is not valid: {result}")
        
        # If all sites failed, try fallback sites in order: JAVmost -> JAV Trailers -> Basic
        if all_failed:
            logging.warning(f"⚠️ ==== ALL ENABLED SITES FAILED, TRYING FALLBACK SITES ====")
            logging.warning(f"⚠️ All scraping sites failed for {jav_code}, trying fallback sites")
            
            # Try JAVmost first
            logging.info(f"🔍 Trying JAVmost for {jav_code}")
            javmost_result = None
            try:
                javmost_result = await self.scrape_javmost(jav_code)
                if javmost_result:
                    # Check if JAVmost result has meaningful data
                    has_meaningful_data = (javmost_result.get('title') and 
                                          javmost_result.get('title') != jav_code and
                                          javmost_result.get('title') != f"{jav_code} - JAV Content" and
                                          javmost_result.get('title') != "JAV MOST") or \
                                         (javmost_result.get('cover_url') and javmost_result.get('cover_url').strip() != '') or \
                                         (javmost_result.get('details', {}).get('Actress') and 
                                          javmost_result.get('details', {}).get('Actress').strip() != '') or \
                                         (javmost_result.get('details', {}).get('Studio') and 
                                          javmost_result.get('details', {}).get('Studio').strip() != '') or \
                                         (javmost_result.get('detailed_metadata', {}).get('actress') and 
                                          javmost_result.get('detailed_metadata', {}).get('actress').strip() != '') or \
                                         (javmost_result.get('detailed_metadata', {}).get('studio') and 
                                          javmost_result.get('detailed_metadata', {}).get('studio').strip() != '')
                    
                    # Log the meaningful data check for debugging
                    logging.info(f"🔍 JAVmost meaningful data check:")
                    logging.info(f"   🔍 Title: {javmost_result.get('title', 'N/A')}")
                    logging.info(f"   🔍 Cover URL: {javmost_result.get('cover_url', 'N/A')}")
                    logging.info(f"   🔍 Details Actress: {javmost_result.get('details', {}).get('Actress', 'N/A')}")
                    logging.info(f"   🔍 Details Studio: {javmost_result.get('details', {}).get('Studio', 'N/A')}")
                    logging.info(f"   🔍 Detailed Metadata Actress: {javmost_result.get('detailed_metadata', {}).get('actress', 'N/A')}")
                    logging.info(f"   🔍 Detailed Metadata Studio: {javmost_result.get('detailed_metadata', {}).get('studio', 'N/A')}")
                    logging.info(f"   🔍 Has meaningful data: {has_meaningful_data}")
                    
                    if has_meaningful_data:
                        logging.info(f"✅ JAVmost fallback successful with meaningful data")
                        results = [javmost_result]
                        enabled_sites.append({'name': 'javmost', 'enabled': True})
                    else:
                        logging.warning(f"⚠️ JAVmost returned data but no meaningful content for {jav_code}")
                        logging.warning(f"⚠️ No actress information found, will try next fallback site")
                        javmost_result = None  # Mark as failed for next fallback
                else:
                    logging.warning(f"⚠️ JAVmost fallback failed for {jav_code}")
            except Exception as e:
                logging.error(f"❌ Error in JAVmost fallback: {e}")
                javmost_result = None
            
            # If JAVmost failed or had no meaningful data, try JAV Trailers
            if not javmost_result:
                logging.info(f"🔍 Trying JAV Trailers for {jav_code}")
                javtrailers_result = None
                try:
                    javtrailers_result = await self.scrape_javtrailers(jav_code)
                    if javtrailers_result:
                        # Check if JAV Trailers result has meaningful data
                        has_meaningful_data = (javtrailers_result.get('title') and 
                                              javtrailers_result.get('title') != jav_code and
                                              javtrailers_result.get('title') != f"{jav_code} - JAV Content") or \
                                             javtrailers_result.get('cover_url') or \
                                             (javtrailers_result.get('detailed_metadata', {}).get('actress') and 
                                              javtrailers_result.get('detailed_metadata', {}).get('actress').strip() != '') or \
                                             (javtrailers_result.get('detailed_metadata', {}).get('studio') and 
                                              javtrailers_result.get('detailed_metadata', {}).get('studio').strip() != '')
                        
                        if has_meaningful_data:
                            logging.info(f"✅ JAV Trailers fallback successful with meaningful data")
                            results = [javtrailers_result]
                            enabled_sites.append({'name': 'javtrailers', 'enabled': True})
                        else:
                            logging.warning(f"⚠️ JAV Trailers returned data but no meaningful content for {jav_code}")
                            logging.warning(f"⚠️ No actress information found, will try next fallback site")
                            javtrailers_result = None  # Mark as failed for next fallback
                    else:
                        logging.warning(f"⚠️ JAV Trailers fallback failed for {jav_code}")
                except Exception as e:
                    logging.error(f"❌ Error in JAV Trailers fallback: {e}")
                    javtrailers_result = None
                
                # If JAV Trailers also failed, try basic fallback
                if not javtrailers_result:
                    logging.info(f"🔍 Trying basic fallback for {jav_code}")
                    try:
                        fallback_result = await self.scrape_fallback(jav_code)
                        if fallback_result:
                            logging.info(f"✅ Basic fallback successful")
                            results = [fallback_result]
                            enabled_sites.append({'name': 'fallback', 'enabled': True})
                        else:
                            logging.warning(f"⚠️ Basic fallback failed for {jav_code}")
                            # Create basic result as last resort
                            results = [{
                                'title': f"{jav_code} - JAV Content",
                                'cover_url': None,
                                'details': {'Actor': 'Unknown', 'Studio': 'Unknown'},
                                'source': 'basic'
                            }]
                            enabled_sites.append({'name': 'basic', 'enabled': True})
                    except Exception as e:
                        logging.error(f"❌ Error in basic fallback: {e}")
                        # Create basic result as last resort
                        results = [{
                            'title': f"{jav_code} - JAV Content",
                            'cover_url': None,
                            'details': {'Actor': 'Unknown', 'Studio': 'Unknown'},
                            'source': 'basic'
                        }]
                        enabled_sites.append({'name': 'basic', 'enabled': True})
        

        
        # Combine results
        combined_data = {
            'jav_code': jav_code,
            'sources': {},
            'best_title': '',
            'best_cover': '',
            'all_details': {},
            'detailed_metadata': {}  # Add detailed metadata section
        }
        
        for i, result in enumerate(results):
            if isinstance(result, dict) and result:
                site_name = enabled_sites[i]['name']
                combined_data['sources'][site_name] = result
                
                # Use the first available title and cover
                if not combined_data['best_title'] and result.get('title'):
                    combined_data['best_title'] = result['title']
                if not combined_data['best_cover'] and result.get('cover_url'):
                    combined_data['best_cover'] = result['cover_url']
                    
                # Merge details
                combined_data['all_details'].update(result.get('details', {}))
                
                # Include detailed metadata if available
                if result.get('detailed_metadata'):
                    combined_data['detailed_metadata'] = result['detailed_metadata']
        
        # Enhance metadata with actress portraits
        combined_data = await self.enhance_actress_metadata(combined_data)
        
        return combined_data
        
    def create_nfo_file(self, metadata: Dict, output_path: str):
        """Create comprehensive NFO file for media servers using metadata.json structure."""
        # Get JAV code from various possible locations
        jav_code = (metadata.get('jav_code') or 
                   metadata.get('detailed_metadata', {}).get('code') or 
                   metadata.get('code', ''))
        
        # Get the best title from various sources
        title = (metadata.get('detailed_metadata', {}).get('full_title') or 
                metadata.get('best_title') or 
                metadata.get('title') or 
                jav_code)
        
        # Get plot from detailed metadata
        plot = (metadata.get('detailed_metadata', {}).get('plot') or 
               metadata.get('all_details', {}).get('Plot', f'JAV content: {title}'))
        
        # Get release date from detailed metadata
        release_date = (metadata.get('detailed_metadata', {}).get('release_date') or 
                       metadata.get('all_details', {}).get('Release Date', ''))
        if not release_date:
            release_date = datetime.now().strftime('%Y-%m-%d')
        
        # Extract year from release date
        year = ''
        if release_date:
            try:
                year = release_date.split('-')[0]
            except:
                year = str(datetime.now().year)
        else:
            year = str(datetime.now().year)
        
        # Get director from detailed metadata
        director = (metadata.get('detailed_metadata', {}).get('director') or 
                   metadata.get('all_details', {}).get('Director', ''))
        
        # Get studio from detailed metadata
        studio = (metadata.get('detailed_metadata', {}).get('studio') or 
                 metadata.get('all_details', {}).get('Studio', ''))
        
        # Get label from detailed metadata
        label = metadata.get('detailed_metadata', {}).get('label', '')
        
        # Get category from detailed metadata
        category = metadata.get('detailed_metadata', {}).get('category', '')
        
        # Get actors (male performers) from detailed metadata
        actors = []
        actor_text = (metadata.get('detailed_metadata', {}).get('actor') or 
                     metadata.get('all_details', {}).get('Actor', ''))
        if actor_text:
            actors = [actor.strip() for actor in actor_text.split(',') if actor.strip()]
        
        # Get actresses (female performers) from detailed metadata
        actresses = []
        actress_text = (metadata.get('detailed_metadata', {}).get('actress') or 
                       metadata.get('all_details', {}).get('Actress', ''))
        if actress_text:
            actresses = [actress.strip() for actress in actress_text.split(',') if actress.strip()]
        
        # Get tags from detailed metadata
        tags = []
        tags_text = metadata.get('detailed_metadata', {}).get('tags', '')
        if tags_text:
            tags = [tag.strip() for tag in tags_text.split(',') if tag.strip()]
        
        # Get genres (combine category and tags)
        genres = []
        if category:
            genres.extend([cat.strip() for cat in category.split(',') if cat.strip()])
        if tags:
            genres.extend(tags)
        if not genres:
            genres = ['Adult', 'JAV']
        
        # Get runtime (default to 0 if not available)
        runtime = metadata.get('all_details', {}).get('Runtime', '0')
        if runtime and runtime.isdigit():
            runtime = runtime
        else:
            runtime = '0'
        
        # Get trailer URL
        trailer = metadata.get('all_details', {}).get('Trailer', '')
        
        # Get actor thumb URL
        actor_thumb = metadata.get('all_details', {}).get('Actor Thumb', '')
        
        # Get series/set information
        series = metadata.get('all_details', {}).get('Series', '')
        
        # Get source information
        source = metadata.get('source', '')
        
        # Get fanart and cover URLs
        fanart_url = metadata.get('detailed_metadata', {}).get('fanart_url', '')
        large_cover_url = metadata.get('detailed_metadata', {}).get('large_cover_url', '')
        
        # Get actress portrait URL
        actress_portrait_url = metadata.get('detailed_metadata', {}).get('thumb_url', '')
        
        nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<movie>
    <title>{title}</title>
    <originaltitle>{title}</originaltitle>
    <plot>{plot}</plot>
    <runtime>{runtime}</runtime>
    <mpaa>NC-17</mpaa>
    <uniqueid type="num" default="true">{jav_code}</uniqueid>
    <uniqueid type="jav" default="false">{jav_code}</uniqueid>
    <year>{year}</year>
    <releasedate>{release_date}</releasedate>
    <country>Japan</country>
    <language>Japanese</language>
    <studio>{studio}</studio>
    <label>{label}</label>
    <director>{director}</director>
    <category>{category}</category>
    <tags>{', '.join(tags)}</tags>
    <source>{source}</source>"""
        
        # Add genres
        for genre in genres:
            nfo_content += f"\n    <genre>{genre}</genre>"
        
        # Add female performers (actresses)
        for actress in actresses:
            nfo_content += f"\n    <actor>"
            nfo_content += f"\n        <name>{actress}</name>"
            nfo_content += f"\n        <role>Female Performer</role>"
            nfo_content += f"\n        <order>0</order>"
            # Add thumb tag for actresses if portrait URL is available
            if actress_portrait_url:
                nfo_content += f"\n        <thumb>{actress_portrait_url}</thumb>"
            nfo_content += f"\n    </actor>"
        
        # Add additional metadata
        if series:
            nfo_content += f"\n    <set>{series}</set>"
        
        if trailer:
            nfo_content += f"\n    <trailer>{trailer}</trailer>"
        
        if actor_thumb:
            nfo_content += f"\n    <actorthumb>{actor_thumb}</actorthumb>"
        
        if fanart_url:
            nfo_content += f"\n    <fanart>{fanart_url}</fanart>"
        
        if large_cover_url:
            nfo_content += f"\n    <cover>{large_cover_url}</cover>"
        
        # Add custom fields for additional metadata
        nfo_content += f"""
    <custominfo>
        <info name="JAV Code">{jav_code}</info>
        <info name="Release Date">{release_date}</info>
        <info name="Category">{category}</info>
        <info name="Director">{director}</info>
        <info name="Studio">{studio}</info>
        <info name="Label">{label}</info>
        <info name="Tags">{', '.join(tags)}</info>
        <info name="Female Performers">{', '.join(actresses)}</info>
        <info name="Source">{source}</info>
        <info name="Plot">{plot}</info>
    </custominfo>
</movie>"""
        
        # Write NFO file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(nfo_content)
            logging.info(f"✅ NFO file created: {output_path}")
            return True
        except Exception as e:
            logging.error(f"❌ Error creating NFO file {output_path}: {e}")
            return False
    

            
    async def download_image(self, url: str, save_path: str):
        """Download image from URL using Playwright to bypass 403 errors and get the actual image file."""
        try:
            logging.info(f"🖼️ Starting image download with Playwright: {url}")
            logging.info(f"💾 Save path: {save_path}")

            # The referer should be the detail page where the image is shown
            # Try to guess the referer from the image URL if not provided
            referer = None
            if 'cdn.javsts.com' in url:
                import re
                m = re.search(r'/([a-z0-9]+)pl', url)
                if m:
                    code = m.group(1).upper()
                    referer = f"https://jav.guru/?s={code}"
                else:
                    referer = "https://jav.guru/"
            else:
                referer = "https://jav.guru/"

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # Set headers to look like a real browser
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Referer': referer,
                    'Connection': 'keep-alive',
                })

                logging.info(f"🌐 Navigating to image URL: {url}")
                response = await page.goto(url, wait_until='networkidle', timeout=30000)
                if response and response.status == 200:
                    image_bytes = await response.body()
                    if image_bytes and len(image_bytes) > 1000:
                        with open(save_path, 'wb') as f:
                            f.write(image_bytes)
                        logging.info(f"✅ Successfully downloaded actual image: {save_path} ({len(image_bytes)} bytes)")
                        await browser.close()
                        return True
                    else:
                        logging.error(f"❌ Image data is empty or too small")
                        await browser.close()
                        return False
                else:
                    logging.error(f"❌ Failed to download image: HTTP {response.status if response else 'no response'}")
                    await browser.close()
                    return False
        except Exception as e:
            logging.error(f"❌ Error downloading image with Playwright: {e}")
            return False
            
    def create_poster_from_fanart(self, fanart_path: str, poster_path: str):
        """Create poster.jpg by cropping the right 47.125% of fanart.jpg."""
        try:
            with Image.open(fanart_path) as img:
                width, height = img.size
                
                # Calculate the crop area (right 47.125%)
                crop_width = int(width * 0.47125)
                left = width - crop_width
                
                # Crop the right portion
                cropped_img = img.crop((left, 0, width, height))
                
                # Save as poster
                cropped_img.save(poster_path, 'JPEG', quality=95)
                logging.info(f"Created poster from fanart: {poster_path}")
                return True
        except Exception as e:
            logging.error(f"Error creating poster from fanart: {e}")
            return False
            
    async def process_folder(self, folder_path: str) -> List[Dict]:
        """Process all files in a folder and scrape metadata."""
        # Scan for JAV files
        files = self.scan_folder(folder_path)
        logging.info(f"Found {len(files)} JAV files in {folder_path}")
        
        results = []
        for file_info in files:
            jav_code = file_info['jav_code']
            logging.info(f"Processing {jav_code}")
            
            # Scrape metadata
            metadata = await self.scrape_all_sites(jav_code)
            metadata.update(file_info)
            
            # Enhance metadata with actress portraits
            metadata = await self.enhance_actress_metadata(metadata)
            
            # Note: File creation (NFO, fanart, poster) is handled in app.py
            # This method only scrapes metadata and enhances it with actress portraits
            logging.info(f"✅ Metadata processing completed for {jav_code}")
            
            # Save metadata JSON in the original folder for reference
            original_folder = Path(file_info['folder'])
            json_path = original_folder / f"{jav_code}-metadata.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
            results.append(metadata)
            
        return results 

    async def search_actress_portrait(self, actress_name: str) -> Optional[str]:
        """
        Search for actress portrait using multiple sources:
        1. javtiful.com (primary)
        2. javmost.com (fallback)
        3. javdatabase.com (final fallback)
        Returns the portrait URL if found.
        """
        try:
            if not actress_name or actress_name.strip() == "":
                logging.info(f"⚠️ No actress name provided for portrait search")
                return None
            
            # Clean actress name for search
            clean_name = actress_name.strip()
            logging.info(f"🎭 ==== ACTRESS PORTRAIT SEARCH START ====")
            logging.info(f"🎭 Actress name: {clean_name}")
            logging.info(f"🎭 Search strategy: javtiful.com → javmost.com → javdatabase.com")
            
            # Try javtiful.com first
            logging.info(f"🎭 ==== TRYING JAVTIFUL.COM ====")
            portrait_url = await self._search_javtiful_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javtiful.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javtiful.com")
            
            # Try javmost.com as fallback
            logging.info(f"🎭 ==== TRYING JAVMOST.COM ====")
            portrait_url = await self._search_javmost_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javmost.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javmost.com")
            
            # Try javdatabase.com as final fallback
            logging.info(f"🎭 ==== TRYING JAVDATABASE.COM (FINAL FALLBACK) ====")
            portrait_url = await self._search_javdatabase_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javdatabase.com: {portrait_url}")
                logging.info(f"🎭 Portrait search completed successfully")
                return portrait_url
            else:
                logging.warning(f"⚠️ No portrait found on javdatabase.com")
            
            logging.warning(f"⚠️ ==== PORTRAIT SEARCH FAILED ====")
            logging.warning(f"⚠️ No actress portrait found for {clean_name} on any source")
            logging.warning(f"⚠️ Tried: javtiful.com, javmost.com, javdatabase.com")
            return None
                
        except Exception as e:
            logging.error(f"❌ ==== PORTRAIT SEARCH ERROR ====")
            logging.error(f"❌ Error searching for actress portrait {actress_name}: {e}")
            logging.error(f"❌ Exception type: {type(e).__name__}")
            return None
    
    async def _search_javtiful_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javtiful.com."""
        try:
            logging.info(f"🔍 Searching javtiful.com for: {clean_name}")
            
            # Construct search URL for javtiful.com
            search_url = f"https://javtiful.com/actresses?q={clean_name.replace(' ', '+')}"
            
            # Fetch search results using Playwright
            html = await self.fetch_html_with_playwright(search_url)
            if not html:
                logging.warning(f"❌ Failed to fetch javtiful search results for {clean_name}")
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for actress profile links in search results
            actress_links = []
            
            # Pattern 1: Look for links with actress names and extract portrait from profile page
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Check if this looks like an actress profile link
                if ('/actress/' in href or '/actresses/' in href) and clean_name.lower() in text.lower():
                    logging.info(f"🎯 Found potential actress link: {href} ({text})")
                    
                    # Fetch the actress profile page to get the portrait
                    profile_url = href if href.startswith('http') else f"https://javtiful.com{href}"
                    profile_html = await self.fetch_html_with_playwright(profile_url)
                    
                    if profile_html:
                        profile_soup = BeautifulSoup(profile_html, 'html.parser')
                        
                        # Look for portrait image in the profile page
                        portrait_img = profile_soup.find('img', {
                            'src': lambda x: x and any(term in x.lower() for term in ['portrait', 'profile', 'actress', 'avatar', 'thumb'])
                        })
                        
                        if portrait_img and portrait_img.get('src'):
                            portrait_url = portrait_img['src']
                            if not portrait_url.startswith('http'):
                                portrait_url = f"https://javtiful.com{portrait_url}"
                            
                            # Remove query parameters (everything after ?)
                            if '?' in portrait_url:
                                portrait_url = portrait_url.split('?')[0]
                            
                            logging.info(f"🖼️ Found javtiful portrait: {portrait_url}")
                            return portrait_url
            
            # Pattern 2: Look for any image that might be a portrait
            all_images = soup.find_all('img')
            for img in all_images:
                src = img.get('src', '')
                alt = img.get('alt', '')
                
                # Check if this image looks like an actress portrait
                if (clean_name.lower() in alt.lower() or 
                    any(term in src.lower() for term in ['portrait', 'profile', 'actress', 'avatar'])):
                    
                    # Make sure it's a full URL
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://javtiful.com' + src
                    
                    logging.info(f"🖼️ Found javtiful actress image: {src} ({alt})")
                    return src
            
            logging.warning(f"⚠️ No javtiful portrait found for {clean_name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching javtiful for {clean_name}: {e}")
            return None
    
    async def _search_javmost_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javmost.com."""
        try:
            logging.info(f"🔍 Searching javmost.com for: {clean_name}")
            
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            # Construct search URL for javmost.com
            search_url = f"https://www5.javmost.com/star/{clean_name.replace(' ', '+')}/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(search_url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for actress profile links in search results
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '')
                        text = link.get_text(strip=True)
                        
                        # Check if this looks like an actress profile link
                        if '/star/' in href and clean_name.lower() in text.lower():
                            logging.info(f"🎯 Found potential javmost actress link: {href} ({text})")
                            
                            # Fetch the actress profile page to get the portrait
                            profile_url = href if href.startswith('http') else f"https://www5.javmost.com{href}"
                            profile_html = await self._fetch_profile_page(profile_url, headers)
                            
                            if profile_html:
                                profile_soup = BeautifulSoup(profile_html, 'html.parser')
                                
                                # Look for portrait image in the profile page
                                portrait_img = profile_soup.find('img', {
                                    'src': lambda x: x and any(term in x.lower() for term in ['portrait', 'profile', 'actress', 'avatar', 'thumb'])
                                })
                                
                                if portrait_img and portrait_img.get('src'):
                                    portrait_url = portrait_img['src']
                                    if not portrait_url.startswith('http'):
                                        portrait_url = f"https://www5.javmost.com{portrait_url}"
                                    
                                    # Remove query parameters (everything after ?)
                                    if '?' in portrait_url:
                                        portrait_url = portrait_url.split('?')[0]
                                    
                                    logging.info(f"🖼️ Found javmost portrait: {portrait_url}")
                                    return portrait_url
                                else:
                                    # If no specific portrait found, look for any image
                                    for img in profile_soup.find_all('img', src=True)[:5]:
                                        src = img.get('src', '')
                                        if src and not src.endswith('.webp'):  # Avoid webp for now
                                            if not src.startswith('http'):
                                                src = f"https://www5.javmost.com{src}"
                                            
                                            # Remove query parameters
                                            if '?' in src:
                                                src = src.split('?')[0]
                                            
                                            logging.info(f"🖼️ Found javmost image: {src}")
                                            return src
                else:
                    logging.warning(f"❌ Failed to fetch javmost search results for {clean_name}: {response.status}")
            
            logging.warning(f"⚠️ No javmost portrait found for {clean_name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching javmost for {clean_name}: {e}")
            return None
    
    async def _search_javdatabase_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on javdatabase.com as final fallback."""
        try:
            logging.info(f"🔍 ==== JAVDATABASE PORTRAIT SEARCH ====")
            logging.info(f"🔍 Actress name: {clean_name}")
            
            # Convert actress name to URL slug format
            # Example: "Kana Yume" -> "kana-yume"
            actress_slug = clean_name.lower().replace(' ', '-')
            logging.info(f"🔍 Actress slug: {actress_slug}")
            
            # Construct direct portrait URL using the known pattern
            portrait_url = f"https://www.javdatabase.com/idolimages/thumb/{actress_slug}.webp"
            logging.info(f"🔍 Direct portrait URL: {portrait_url}")
            
            # Check if the portrait exists by making a HEAD request
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'image/webp,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
                logging.info(f"🔍 Created new aiohttp session for JAV Database check")
            
            logging.info(f"📡 Checking if portrait exists...")
            async with self.session.head(portrait_url, headers=headers) as response:
                logging.info(f"📊 Response status: {response.status}")
                
                if response.status == 200:
                    logging.info(f"✅ Portrait found at: {portrait_url}")
                    return portrait_url
                else:
                    logging.warning(f"⚠️ Portrait not found at: {portrait_url}")
                    
                    # Try alternative slug formats if the first one doesn't work
                    alternative_slugs = [
                        actress_slug.replace('-', ''),  # "kana-yume" -> "kanayume"
                        actress_slug.replace('-', '_'),  # "kana-yume" -> "kana_yume"
                        clean_name.lower().replace(' ', ''),  # "Kana Yume" -> "kanayume"
                    ]
                    
                    for alt_slug in alternative_slugs:
                        alt_portrait_url = f"https://www.javdatabase.com/idolimages/thumb/{alt_slug}.webp"
                        logging.info(f"🔍 Trying alternative URL: {alt_portrait_url}")
                        
                        async with self.session.head(alt_portrait_url, headers=headers) as alt_response:
                            if alt_response.status == 200:
                                logging.info(f"✅ Portrait found at alternative URL: {alt_portrait_url}")
                                return alt_portrait_url
                    
                    logging.warning(f"⚠️ No portrait found for {clean_name} with any slug format")
                    return None
                
        except Exception as e:
            logging.error(f"❌ ==== JAVDATABASE SEARCH ERROR ====")
            logging.error(f"❌ Error searching JAV Database for {clean_name}: {e}")
            logging.error(f"❌ Exception type: {type(e).__name__}")
            return None
    
    async def _fetch_profile_page(self, url: str, headers: dict) -> Optional[str]:
        """Fetch actress profile page."""
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.warning(f"❌ Failed to fetch profile page: {response.status}")
                    return None
        except Exception as e:
            logging.error(f"❌ Error fetching profile page: {e}")
            return None

    async def enhance_actress_metadata(self, metadata: Dict) -> Dict:
        """
        Enhance metadata by searching for actress portraits.
        Only attempts portrait search if actress information is found in metadata.
        """
        try:
            # Get actress information from metadata
            actress_name = None
            actress_source = None
            
            # Check different possible fields for actress name
            if metadata.get('detailed_metadata', {}).get('actress'):
                actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
                actress_source = 'detailed_metadata.actress'
            elif metadata.get('detailed_metadata', {}).get('actresses'):
                actress_name = metadata['detailed_metadata']['actresses'].split(',')[0].strip()
                actress_source = 'detailed_metadata.actresses'
            elif metadata.get('all_details', {}).get('Actress'):
                actress_name = metadata['all_details']['Actress'].split(',')[0].strip()
                actress_source = 'all_details.Actress'
            
            if not actress_name:
                logging.info(f"ℹ️ No actress name found in metadata, skipping portrait search")
                logging.info(f"ℹ️ Metadata source: {metadata.get('source', 'unknown')}")
                return metadata
            
            # Clean the actress name to remove Japanese characters
            original_actress_name = actress_name
            actress_name = self.clean_actress_name(actress_name)
            
            if not actress_name:
                logging.warning(f"⚠️ Actress name cleaned to empty: {original_actress_name}")
                return metadata
            
            logging.info(f"🎭 ==== ACTRESS PORTRAIT SEARCH START ====")
            logging.info(f"🎭 Original actress name: {original_actress_name}")
            logging.info(f"🎭 Cleaned actress name: {actress_name}")
            logging.info(f"🎭 Actress source: {actress_source}")
            logging.info(f"🎭 Metadata source: {metadata.get('source', 'unknown')}")
            logging.info(f"🎭 Enhancing metadata for actress: {actress_name}")
            
            # Search for actress portrait
            portrait_url = await self.search_actress_portrait(actress_name)
            
            if portrait_url:
                # Add portrait URL to metadata
                if 'detailed_metadata' not in metadata:
                    metadata['detailed_metadata'] = {}
                
                metadata['detailed_metadata']['thumb_url'] = portrait_url
                logging.info(f"✅ Added actress portrait URL: {portrait_url}")
                
                # Also add to all_details for compatibility
                if 'all_details' not in metadata:
                    metadata['all_details'] = {}
                metadata['all_details']['Actress Portrait'] = portrait_url
            else:
                logging.info(f"ℹ️ No portrait found for {actress_name}")
            
            return metadata
            
        except Exception as e:
            logging.error(f"❌ Error enhancing actress metadata: {e}")
            return metadata 

    async def search_google_for_title(self, jav_code: str) -> Optional[str]:
        """Search Google for the actual title of the JAV."""
        try:
            logging.info(f"🔍 Searching Google for title of {jav_code}")
            
            # Search query
            search_query = f"{jav_code} title"
            encoded_query = urllib.parse.quote(search_query)
            url = f"https://www.google.com/search?q={encoded_query}"
            
            # Headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for search results that might contain the actual title
                    # Google search results are typically in h3 tags
                    search_results = soup.find_all('h3')
                    
                    for result in search_results:
                        result_text = result.get_text().strip()
                        # Look for results that contain the JAV code and might have a title
                        if jav_code in result_text and len(result_text) > len(jav_code):
                            # Extract potential title (remove the JAV code and clean up)
                            potential_title = result_text.replace(jav_code, '').strip()
                            if potential_title and len(potential_title) > 3:
                                # Clean up common prefixes/suffixes
                                potential_title = re.sub(r'^[-_\s]+', '', potential_title)
                                potential_title = re.sub(r'[-_\s]+$', '', potential_title)
                                if potential_title:
                                    logging.info(f"✅ Found potential title: {potential_title}")
                                    return potential_title
                    
                    logging.warning(f"⚠️ No suitable title found for {jav_code}")
                    return None
                else:
                    logging.warning(f"⚠️ Google search failed with status {response.status}")
                    return None
                    
        except Exception as e:
            logging.error(f"❌ Error searching Google for {jav_code}: {e}")
            return None

    async def download_and_convert_webp_to_jpg(self, webp_url: str, output_path: str) -> bool:
        """Download webp image and convert to jpg."""
        try:
            logging.info(f"📥 Downloading webp image: {webp_url}")
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            async with self.session.get(webp_url) as response:
                if response.status == 200:
                    # Download the webp image
                    webp_data = await response.read()
                    
                    # Create a temporary file for the webp
                    with tempfile.NamedTemporaryFile(suffix='.webp', delete=False) as temp_webp:
                        temp_webp.write(webp_data)
                        temp_webp_path = temp_webp.name
                    
                    try:
                        # Open and convert to jpg
                        with Image.open(temp_webp_path) as img:
                            # Convert to RGB if necessary
                            if img.mode in ('RGBA', 'LA', 'P'):
                                img = img.convert('RGB')
                            
                            # Save as jpg
                            img.save(output_path, 'JPEG', quality=95)
                        
                        logging.info(f"✅ Successfully converted webp to jpg: {output_path}")
                        return True
                        
                    finally:
                        # Clean up temporary file
                        if os.path.exists(temp_webp_path):
                            os.unlink(temp_webp_path)
                else:
                    logging.error(f"❌ Failed to download webp image: {response.status}")
                    return False
                    
        except Exception as e:
            logging.error(f"❌ Error converting webp to jpg: {e}")
            return False

    async def scrape_javmost(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JAVmost."""
        try:
            logging.info(f"🌐 ==== JAVMOST SCRAPING START ====")
            logging.info(f"🌐 JAV Code: {jav_code}")
            url = f"https://www5.javmost.com/search/{jav_code}/"
            logging.info(f"🌐 Search URL: {url}")
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                import aiohttp
                self.session = aiohttp.ClientSession()
                logging.info(f"🌐 Created new aiohttp session")
            
            # Add headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            logging.info(f"🌐 Using headers: {list(headers.keys())}")
            
            logging.info(f"📡 Requesting URL: {url}")
            async with self.session.get(url, headers=headers) as response:
                logging.info(f"📊 Response status: {response.status}")
                logging.info(f"📊 Response headers: {dict(response.headers)}")
                
                if response.status == 200:
                    html = await response.text()
                    logging.info(f"📄 Received HTML length: {len(html)} characters")
                    
                    # Check if HTML contains the JAV code
                    if jav_code in html:
                        logging.info(f"✅ HTML contains JAV code: {jav_code}")
                    else:
                        logging.warning(f"⚠️ HTML does not contain JAV code: {jav_code}")
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    logging.info(f"🔍 Parsed HTML with BeautifulSoup")
                    
                    # Look for search results - JAVmost has specific structure
                    logging.info(f"🔍 ==== SEARCHING FOR RESULTS ====")
                    # Find cards that contain the JAV code
                    results = soup.find_all('div', class_='card')
                    logging.info(f"🔍 Found {len(results)} divs with class 'card'")
                    
                    if not results:
                        logging.info(f"🔍 No 'card' divs found, trying 'result' class")
                        # Try alternative selectors
                        results = soup.find_all('div', class_=lambda x: x and 'result' in x.lower())
                        logging.info(f"🔍 Found {len(results)} divs with 'result' in class")
                    
                    if not results:
                        logging.info(f"🔍 No 'result' divs found, searching for JAV code in text")
                        # Try finding any div that contains the JAV code
                        results = soup.find_all('div', string=lambda text: text and jav_code in text)
                        logging.info(f"🔍 Found {len(results)} divs containing JAV code in text")
                    
                    if not results:
                        logging.info(f"🔍 No specific results found, using entire page")
                        # Last resort: look for any content containing the JAV code
                        results = [soup]  # Use the entire page if no specific results found
                        logging.info(f"🔍 Using entire page as result")
                    
                    if results:
                        logging.info(f"✅ Found {len(results)} results for {jav_code}")
                        
                        # Find the result that matches the exact JAV code
                        exact_match = None
                        logging.info(f"🔍 ==== SEARCHING FOR EXACT MATCH ====")
                        for i, result in enumerate(results):
                            logging.info(f"🔍 Checking result {i+1}/{len(results)}")
                            # Check if this result contains the exact JAV code
                            result_text = result.get_text()
                            if jav_code in result_text:
                                logging.info(f"✅ Result {i+1} contains JAV code")
                                # Check if it's the exact match (not a variant)
                                title_elem = result.find('h1', class_='card-title')
                                if title_elem:
                                    title_text = title_elem.get_text().strip()
                                    logging.info(f"🔍 Found title: '{title_text}'")
                                    if title_text == jav_code:
                                        exact_match = result
                                        logging.info(f"✅ Found exact match in result {i+1}")
                                        break
                                    else:
                                        logging.info(f"⚠️ Title doesn't match JAV code: '{title_text}' != '{jav_code}'")
                                else:
                                    logging.info(f"⚠️ No title element found in result {i+1}")
                            else:
                                logging.info(f"⚠️ Result {i+1} doesn't contain JAV code")
                        
                        # Use exact match if found, otherwise use first result
                        first_result = exact_match if exact_match else results[0]
                        
                        # Extract title from the card title
                        title = f"{jav_code} - JAV Content"
                        title_elem = first_result.find('h1', class_='card-title')
                        if title_elem:
                            title = title_elem.get_text().strip()
                        else:
                            # Fallback to finding any title element
                            title_elem = first_result.find('h2') or first_result.find('h3') or \
                                       first_result.find('a', href=True)
                            if title_elem:
                                title = title_elem.get_text().strip()
                        
                        # If title is same as JAV code, try to get better title from Google
                        if title == jav_code:
                            logging.info(f"🔍 Title is same as JAV code, searching Google for better title")
                            google_title = await self.search_google_for_title(jav_code)
                            if google_title:
                                title = f"{jav_code} - {google_title}"
                                logging.info(f"✅ Enhanced title: {title}")
                        
                        # Extract metadata from the result
                        metadata = {
                            'code': jav_code,
                            'full_title': title,
                            'actress': '',
                            'director': '',
                            'studio': '',
                            'label': '',
                            'release_date': '',
                            'runtime': '',
                            'category': '',
                            'tags': '',
                            'plot': f'JAV content: {title}',
                            'fanart_url': '',
                            'large_cover_url': '',
                            'thumb_url': ''
                        }
                        
                        # Extract actress/star information from the card-text section
                        actress_text = ""
                        card_text = first_result.find('p', class_='card-text')
                        if card_text:
                            # Look for star/actress information
                            star_section = card_text.find('i', class_='fa-female')
                            if star_section:
                                # Get the next sibling that contains the actress name
                                star_parent = star_section.find_parent()
                                if star_parent:
                                    # Find the actress link
                                    actress_link = star_parent.find('a', href=lambda x: x and 'star' in x)
                                    if actress_link:
                                        original_actress_text = actress_link.get_text().strip()
                                        # Clean the actress name to remove Japanese characters
                                        actress_text = self.clean_actress_name(original_actress_text)
                                        logging.info(f"🎭 JAVmost original actress: {original_actress_text}")
                                        logging.info(f"🎭 JAVmost cleaned actress: {actress_text}")
                        
                        metadata['actress'] = actress_text
                        
                        # Extract director from the card-text section
                        director_text = ""
                        if card_text:
                            # Look for director information
                            director_section = card_text.find('i', class_='fa-bullhorn')
                            if director_section:
                                # Get the next sibling that contains the director name
                                director_parent = director_section.find_parent()
                                if director_parent:
                                    # Find the director link
                                    director_link = director_parent.find('a', href=lambda x: x and 'director' in x)
                                    if director_link:
                                        director_text = director_link.get_text().strip()
                        
                        metadata['director'] = director_text
                        
                        # Extract maker/studio from the card-text section
                        studio_text = ""
                        if card_text:
                            # Look for maker information
                            maker_section = card_text.find('i', class_='fa-group')
                            if maker_section:
                                # Get the next sibling that contains the maker name
                                maker_parent = maker_section.find_parent()
                                if maker_parent:
                                    # Find the maker link
                                    maker_link = maker_parent.find('a', href=lambda x: x and 'maker' in x)
                                    if maker_link:
                                        studio_text = maker_link.get_text().strip()
                        
                        metadata['studio'] = studio_text
                        
                        # Extract release date from the card-text section
                        release_date = ""
                        if card_text:
                            # Look for release date
                            release_text = card_text.get_text()
                            import re
                            release_match = re.search(r'Release\s+(\d{4}-\d{2}-\d{2})', release_text)
                            if release_match:
                                release_date = release_match.group(1)
                        
                        metadata['release_date'] = release_date
                        
                        # Extract runtime from the card-text section
                        runtime = ""
                        if card_text:
                            # Look for runtime
                            runtime_text = card_text.get_text()
                            import re
                            runtime_match = re.search(r'Time\s+(\d+)', runtime_text)
                            if runtime_match:
                                runtime = runtime_match.group(1)
                        
                        metadata['runtime'] = runtime
                        
                        # Extract genre/category from the card-text section
                        category_text = ""
                        if card_text:
                            # Look for genre information
                            genre_section = card_text.find('i', class_='ion-ios-videocam')
                            if genre_section:
                                # Get the next sibling that contains the genre names
                                genre_parent = genre_section.find_parent()
                                if genre_parent:
                                    # Find all genre links
                                    genre_links = genre_parent.find_all('a', href=lambda x: x and 'category' in x)
                                    if genre_links:
                                        categories = [link.get_text().strip() for link in genre_links]
                                        category_text = ", ".join(categories)
                        
                        metadata['category'] = category_text
                        
                        # Try to find cover image from the source elements
                        cover_url = ""
                        # Look for source elements with the JAV code in the data-srcset
                        sources = first_result.find_all('source', attrs={'data-srcset': True})
                        for source in sources:
                            srcset = source.get('data-srcset', '')
                            if jav_code in srcset and '.webp' in srcset:
                                # Prefer the exact JAV code match, not variants
                                if jav_code == srcset.split('/')[-1].replace('.webp', ''):
                                    cover_url = srcset
                                    break
                                elif cover_url == "":  # Fallback to any match
                                    cover_url = srcset
                        
                        if cover_url:
                            if cover_url.startswith('//'):
                                cover_url = 'https:' + cover_url
                            elif cover_url.startswith('/'):
                                cover_url = 'https://www5.javmost.com' + cover_url
                            metadata['fanart_url'] = cover_url
                            metadata['large_cover_url'] = cover_url
                            
                            # If it's a webp image, we'll need to download and convert it
                            if cover_url.endswith('.webp'):
                                metadata['needs_webp_conversion'] = True
                                metadata['webp_url'] = cover_url
                        
                        # Try to find detail page link
                        detail_link = first_result.find('a', href=True)
                        if detail_link:
                            detail_url = detail_link.get('href')
                            if detail_url.startswith('/'):
                                detail_url = 'https://www5.javmost.com' + detail_url
                            elif not detail_url.startswith('http'):
                                detail_url = 'https://www5.javmost.com/' + detail_url
                            
                            # Only proceed if this is the exact JAV code detail page
                            if jav_code in detail_url and jav_code == detail_url.split('/')[-2]:
                                logging.info(f"🔗 Detail URL: {detail_url}")
                            
                            # Scrape detail page for more information
                            async with self.session.get(detail_url, headers=headers) as detail_response:
                                if detail_response.status == 200:
                                    detail_html = await detail_response.text()
                                    detail_soup = BeautifulSoup(detail_html, 'html.parser')
                                    
                                    # Extract plot/synopsis
                                    plot_elem = detail_soup.find('div', class_=lambda x: x and 'plot' in x.lower()) or \
                                              detail_soup.find('div', class_=lambda x: x and 'synopsis' in x.lower())
                                    if plot_elem:
                                        plot_text = plot_elem.get_text().strip()
                                        if plot_text:
                                            metadata['plot'] = plot_text
                                    
                                    # Try to find better cover image on detail page
                                    detail_cover = detail_soup.find('img', src=lambda x: x and ('cover' in x.lower() or 'poster' in x.lower()))
                                    if detail_cover:
                                        detail_cover_url = detail_cover.get('src')
                                        if detail_cover_url:
                                            if detail_cover_url.startswith('//'):
                                                detail_cover_url = 'https:' + detail_cover_url
                                            elif detail_cover_url.startswith('/'):
                                                detail_cover_url = 'https://www5.javmost.com' + detail_cover_url
                                            metadata['fanart_url'] = detail_cover_url
                                            metadata['large_cover_url'] = detail_cover_url
                        
                        result = {
                            'title': title,
                            'cover_url': metadata['fanart_url'],
                            'details': {
                                'Actor': metadata['actress'],
                                'Actress': metadata['actress'],
                                'Director': metadata['director'],
                                'Studio': metadata['studio'],
                                'Maker': metadata['studio'],
                                'Release Date': metadata['release_date'],
                                'Runtime': metadata['runtime'],
                                'Genre': metadata['category'],
                                'Category': metadata['category'],
                                'Plot': metadata['plot']
                            },
                            'detailed_metadata': metadata,
                            'source': 'javmost'
                        }
                        
                        logging.info(f"✅ JAVmost scrape completed for {jav_code}")
                        return result
                    else:
                        logging.warning(f"⚠️ No results found on JAVmost for {jav_code}")
                        return None
                else:
                    logging.warning(f"⚠️ JAVmost returned status {response.status} for {jav_code}")
                    return None
                    
        except Exception as e:
            logging.error(f"❌ Error in JAVmost scraper for {jav_code}: {e}")
            return None 
            return None 

    async def scrape_javtrailers(self, jav_code: str) -> Optional[Dict]:
        """Scrape metadata from JavTrailers.com."""
        try:
            logging.info(f"🎬 ==== JAVTRAILERS SCRAPING START ====")
            logging.info(f"🎬 JAV Code: {jav_code}")
            
            # Step 1: Search for the JAV code
            search_url = f"https://javtrailers.com/search/{jav_code}"
            logging.info(f"🔍 Search URL: {search_url}")
            
            search_html = await self.fetch_html_with_playwright(search_url)
            if not search_html:
                logging.warning(f"⚠️ Failed to fetch search page for {jav_code}")
                return None
            
            search_soup = BeautifulSoup(search_html, 'html.parser')
            
            # Look for the first video result that matches our JAV code
            video_links = search_soup.find_all('a', href=True)
            detail_url = None
            
            for link in video_links:
                href = link.get('href', '')
                # Look for video links that contain the JAV code
                if '/video/' in href:
                    # Check if this link contains our JAV code
                    link_text = link.get_text(strip=True)
                    if jav_code.lower() in link_text.lower():
                        detail_url = href if href.startswith('http') else f"https://javtrailers.com{href}"
                        logging.info(f"🎯 Found detail URL: {detail_url}")
                        logging.info(f"🎯 Link text: {link_text}")
                        break
            
            # If not found by text, try to find by URL pattern
            if not detail_url:
                for link in video_links:
                    href = link.get('href', '')
                    if '/video/' in href and jav_code.lower() in href.lower():
                        detail_url = href if href.startswith('http') else f"https://javtrailers.com{href}"
                        logging.info(f"🎯 Found detail URL by URL pattern: {detail_url}")
                        break
            
            if not detail_url:
                logging.warning(f"⚠️ No detail page found for {jav_code}")
                return None
            
            # Step 2: Fetch the detail page
            logging.info(f"📄 Fetching detail page: {detail_url}")
            detail_html = await self.fetch_html_with_playwright(detail_url)
            
            if not detail_html:
                logging.warning(f"⚠️ Failed to fetch detail page for {jav_code}")
                return None
            
            detail_soup = BeautifulSoup(detail_html, 'html.parser')
            
            # Extract metadata from detail page
            metadata = {}
            
            # Extract title
            title_tag = detail_soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)
                metadata['title'] = title
                logging.info(f"📋 Title: {title}")
            else:
                # Fallback: use JAV code as title
                title = f"{jav_code} - JAV Content"
                metadata['title'] = title
                logging.info(f"📋 Title (fallback): {title}")
            
            # Extract DVD ID and Content ID
            dvd_id = jav_code
            content_id = None
            
            # Look for content ID in the page - try multiple patterns
            content_patterns = [
                r'Content ID:\s*([^\s<]+)',
                r'DVD ID:\s*([^\s<]+)',
                r'ID:\s*([^\s<]+)'
            ]
            for pattern in content_patterns:
                content_match = re.search(pattern, detail_html)
                if content_match:
                    content_id = content_match.group(1)
                    logging.info(f"📋 Content ID: {content_id}")
                    break
            
            # Extract release date - try multiple patterns
            release_date = None
            date_patterns = [
                r'Release Date:\s*(\d+\s+\w+\s+\d+)',
                r'(\d+\s+\w+\s+\d+)\s*$',  # Date at end of line
                r'(\d{1,2}\s+\w+\s+\d{4})'  # General date pattern
            ]
            for pattern in date_patterns:
                date_match = re.search(pattern, detail_html)
                if date_match:
                    release_date = date_match.group(1)
                    logging.info(f"📋 Release Date: {release_date}")
                    break
            
            # Extract duration - try multiple patterns
            duration = None
            duration_patterns = [
                r'Duration:\s*(\d+)\s*mins',
                r'(\d+)\s*mins',
                r'(\d+):(\d+)'  # HH:MM format
            ]
            for pattern in duration_patterns:
                duration_match = re.search(pattern, detail_html)
                if duration_match:
                    if ':' in pattern:
                        hours, minutes = duration_match.groups()
                        duration = str(int(hours) * 60 + int(minutes))
                    else:
                        duration = duration_match.group(1)
                    logging.info(f"📋 Duration: {duration} mins")
                    break
            
            # Extract studio using BeautifulSoup
            studio = None
            studio_span = detail_soup.find('span', string=lambda text: text and 'Studio:' in text)
            if studio_span:
                studio_link = studio_span.find_next('a')
                if studio_link:
                    studio = studio_link.get_text(strip=True)
                    logging.info(f"📋 Studio: {studio}")
            
            # Extract categories using BeautifulSoup
            categories = []
            categories_span = detail_soup.find('span', string=lambda text: text and 'Categories:' in text)
            if categories_span:
                category_links = categories_span.find_next_siblings('a')
                for link in category_links:
                    category_text = link.get_text(strip=True)
                    if category_text:
                        categories.append(category_text)
                logging.info(f"📋 Categories: {categories}")
            
            # Extract cast using BeautifulSoup
            cast = []
            cast_span = detail_soup.find('span', string=lambda text: text and 'Cast(s):' in text)
            if cast_span:
                cast_link = cast_span.find_next('a')
                if cast_link:
                    cast_text = cast_link.get_text(strip=True)
                    # Clean up the cast text using the new cleaning function
                    cleaned_cast_text = self.clean_actress_name(cast_text)
                    if cleaned_cast_text:
                        cast = [cleaned_cast_text]
                        logging.info(f"📋 Original cast text: {cast_text}")
                        logging.info(f"📋 Cleaned cast: {cleaned_cast_text}")
                    else:
                        logging.warning(f"⚠️ Cast text cleaned to empty: {cast_text}")
            
            # Extract series using BeautifulSoup
            series = None
            series_span = detail_soup.find('span', string=lambda text: text and 'Series:' in text)
            if series_span:
                series_link = series_span.find_next('a')
                if series_link:
                    series = series_link.get_text(strip=True)
                    logging.info(f"📋 Series: {series}")
            
            # Extract images from JavTrailers
            fanart_url = None
            poster_url = None
            
            # Look for image URLs in the page
            img_tags = detail_soup.find_all('img')
            for img in img_tags:
                src = img.get('src', '')
                data_src = img.get('data-src', '')
                img_url = data_src if data_src else src
                
                if img_url and 'pics.dmm.co.jp' in img_url:
                    # This is likely a cover/poster image
                    if not poster_url:
                        poster_url = img_url
                        logging.info(f"📋 Poster URL: {poster_url}")
                    elif not fanart_url:
                        fanart_url = img_url
                        logging.info(f"📋 Fanart URL: {fanart_url}")
            
            # If we found a poster but no fanart, use poster as fanart too
            if poster_url and not fanart_url:
                fanart_url = poster_url
                logging.info(f"📋 Using poster as fanart: {fanart_url}")
            
            # Create detailed metadata structure
            detailed_metadata = {
                'dvd_id': dvd_id,
                'content_id': content_id,
                'release_date': release_date,
                'duration': duration,
                'studio': studio,
                'categories': categories,
                'cast': cast,
                'series': series,
                'source': 'javtrailers'
            }
            
            # Add image URLs to detailed metadata
            if poster_url:
                detailed_metadata['poster_url'] = poster_url
            if fanart_url:
                detailed_metadata['fanart_url'] = fanart_url
            
            # Extract actress information
            if cast:
                # Look for female performers (typically Japanese names)
                actresses = []
                for person in cast:
                    # Use the new cleaning function for consistent actress name cleaning
                    clean_name = self.clean_actress_name(person)
                    if clean_name:
                        actresses.append(clean_name)
                        logging.info(f"🎭 Original actress: {person}")
                        logging.info(f"🎭 Cleaned actress: {clean_name}")
                    else:
                        logging.warning(f"⚠️ Actress name cleaned to empty: {person}")
                
                if actresses:
                    detailed_metadata['actress'] = ', '.join(actresses)
                    logging.info(f"🎭 Final actresses list: {actresses}")
                else:
                    logging.warning(f"⚠️ No valid actresses found after cleaning")
            
            # Create result structure
            result = {
                'title': metadata.get('title', f"{jav_code} - JAV Content"),
                'cover_url': poster_url,  # Use poster URL as cover URL
                'detail_url': detail_url,
                'detailed_metadata': detailed_metadata,
                'source': 'javtrailers'
            }
            
            logging.info(f"✅ JavTrailers scrape completed for {jav_code}")
            return result
            
        except Exception as e:
            logging.error(f"❌ Error scraping JavTrailers for {jav_code}: {e}")
            return None