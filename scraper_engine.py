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
                    # Save detail page HTML for inspection
                    with open(f'debug_detail_{jav_code}.html', 'w', encoding='utf-8') as f:
                        f.write(detail_html)
                    logging.info(f"💾 Detail page HTML saved to: debug_detail_{jav_code}.html")
                    
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
                
                # Store the metadata
                metadata[field_name] = field_value
                
                logging.info(f"📋 Extracted {field_name}: {field_value}")
            
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
        enabled_sites = [site for site in self.config.get('scraper', {}).get('sites', []) if site.get('enabled', True)]
        logging.info(f"🔍 Enabled sites: {[site['name'] for site in enabled_sites]}")
        
        tasks = []
        for site in enabled_sites:
            site_name = site['name']
            if site_name == 'javguru':
                tasks.append(self.scrape_javguru(jav_code))
                
        logging.info(f"📡 Starting {len(tasks)} scraping tasks")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logging.info(f"📊 Scraping results: {results}")
        
        # Check if all sites failed or returned empty results
        all_failed = True
        for result in results:
            if isinstance(result, dict) and result:
                # Check if the result has meaningful data
                has_title = result.get('title') and result.get('title') != 'None'
                has_cover = result.get('cover_url')
                has_actress = result.get('details', {}).get('Actress') or result.get('details', {}).get('Actor')
                
                if has_title or has_cover or has_actress:
                    all_failed = False
                    break
        
        # If all sites failed, try JAVmost as fallback
        if all_failed:
            logging.warning(f"⚠️ All scraping sites failed for {jav_code}, trying JAVmost")
            javmost_result = await self.scrape_javmost(jav_code)
            if javmost_result:
                results = [javmost_result]
                # Add JAVmost as a source
                enabled_sites.append({'name': 'javmost', 'enabled': True})
            else:
                # If JAVmost also failed, use basic fallback
                logging.warning(f"⚠️ JAVmost also failed for {jav_code}, using basic fallback")
                fallback_result = await self.scrape_fallback(jav_code)
                if fallback_result:
                    results = [fallback_result]
                    # Add fallback as a source
                    enabled_sites.append({'name': 'fallback', 'enabled': True})
                else:
                    # If fallback also failed, create a basic result
                    logging.warning(f"⚠️ All fallbacks failed for {jav_code}, creating basic result")
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
            
            # Create Videos folder in the same directory as the original video
            original_folder = Path(file_info['folder'])
            videos_folder = original_folder / "Videos"
            videos_folder.mkdir(exist_ok=True)
            
            # Create NFO file
            if self.config.get('scraper', {}).get('create_nfo', True):
                nfo_path = videos_folder / "movie.nfo"
                self.create_nfo_file(metadata, str(nfo_path))
                
            # Download fanart and create poster
            # Prioritize fanart_url from detailed metadata, fallback to best_cover
            fanart_url = None
            needs_webp_conversion = False
            
            if metadata.get('detailed_metadata', {}).get('fanart_url'):
                fanart_url = metadata['detailed_metadata']['fanart_url']
                needs_webp_conversion = metadata['detailed_metadata'].get('needs_webp_conversion', False)
                logging.info(f"🎨 Using fanart URL from detailed metadata: {fanart_url}")
            elif metadata.get('best_cover'):
                fanart_url = metadata['best_cover']
                logging.info(f"🎨 Using fallback cover URL: {fanart_url}")
            
            if self.config.get('scraper', {}).get('download_cover', True) and fanart_url:
                fanart_path = videos_folder / "fanart.jpg"
                poster_path = videos_folder / "poster.jpg"
                
                # Handle webp conversion if needed
                if needs_webp_conversion and metadata.get('detailed_metadata', {}).get('webp_url'):
                    webp_url = metadata['detailed_metadata']['webp_url']
                    logging.info(f"🔄 Converting webp to jpg: {webp_url}")
                    if await self.download_and_convert_webp_to_jpg(webp_url, str(fanart_path)):
                        # Create poster by cropping the right 47.125% of fanart
                        self.create_poster_from_fanart(str(fanart_path), str(poster_path))
                        logging.info(f"✅ Successfully created fanart.jpg and poster.jpg for {jav_code}")
                    else:
                        logging.warning(f"⚠️ Failed to convert webp for {jav_code}")
                else:
                    # Regular image download
                    if await self.download_image(fanart_url, str(fanart_path)):
                        # Create poster by cropping the right 47.125% of fanart
                        self.create_poster_from_fanart(str(fanart_path), str(poster_path))
                        logging.info(f"✅ Successfully created fanart.jpg and poster.jpg for {jav_code}")
                    else:
                        logging.warning(f"⚠️ Failed to download fanart for {jav_code}")
            else:
                logging.warning(f"⚠️ No fanart URL available for {jav_code}")
            
            # Download actress portrait if available
            actress_name = ""
            if metadata.get('detailed_metadata', {}).get('actress'):
                actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
            
            if actress_name and self.config.get('scraper', {}).get('download_cover', True):
                # Clean actress name for filename
                import re
                clean_actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
                clean_actress_name = clean_actress_name.replace(' ', '_')
                
                portrait_path = videos_folder / f"{clean_actress_name}_portrait.jpg"
                
                logging.info(f"🎭 Searching for actress portrait: {actress_name}")
                
                # Search for actress portrait using the existing method
                actress_portrait_url = await self.search_actress_portrait(actress_name)
                
                if actress_portrait_url:
                    logging.info(f"🎭 Found portrait URL: {actress_portrait_url}")
                    logging.info(f"🎭 Save path: {portrait_path}")
                    
                    if await self.download_image(actress_portrait_url, str(portrait_path)):
                        logging.info(f"✅ Successfully downloaded actress portrait: {portrait_path}")
                        # Check file size
                        if portrait_path.exists():
                            size = portrait_path.stat().st_size
                            logging.info(f"📏 Portrait file size: {size} bytes")
                    else:
                        logging.warning(f"⚠️ Failed to download actress portrait for {actress_name}")
                else:
                    logging.warning(f"⚠️ No actress portrait found for {actress_name}")
            else:
                logging.info(f"ℹ️ No actress name found, skipping portrait download")
                
            # Save metadata JSON
            json_path = videos_folder / f"{jav_code}-metadata.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
                
            results.append(metadata)
            
        return results 

    async def search_actress_portrait(self, actress_name: str) -> Optional[str]:
        """
        Search for actress portrait using multiple sources:
        1. javtiful.com (primary)
        2. javmost.com (fallback)
        3. Google Images (final fallback)
        Returns the portrait URL if found.
        """
        try:
            if not actress_name or actress_name.strip() == "":
                logging.info(f"⚠️ No actress name provided for portrait search")
                return None
            
            # Clean actress name for search
            clean_name = actress_name.strip()
            logging.info(f"🔍 Searching for actress portrait: {clean_name}")
            
            # Try javtiful.com first
            portrait_url = await self._search_javtiful_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javtiful.com: {portrait_url}")
                return portrait_url
            
            # Try javmost.com as fallback
            portrait_url = await self._search_javmost_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on javmost.com: {portrait_url}")
                return portrait_url
            
            # Try Google Images as final fallback
            portrait_url = await self._search_google_images_portrait(clean_name)
            if portrait_url:
                logging.info(f"✅ Found portrait on Google Images: {portrait_url}")
                return portrait_url
            
            logging.warning(f"⚠️ No actress portrait found for {clean_name} on any source")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching for actress portrait {actress_name}: {e}")
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
    
    async def _search_google_images_portrait(self, clean_name: str) -> Optional[str]:
        """Search for actress portrait on Google Images as final fallback."""
        try:
            logging.info(f"🔍 Searching Google Images for: {clean_name}")
            
            # Ensure session is available
            if not hasattr(self, 'session') or self.session is None:
                self.session = aiohttp.ClientSession()
            
            # Construct Google Images search URL
            search_query = f"{clean_name} JAV actress portrait"
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}&tbm=isch"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with self.session.get(search_url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Look for image URLs in Google Images results
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        if src and src.startswith('http') and not src.endswith('.webp'):
                            # Check if this looks like a portrait image
                            if any(term in src.lower() for term in ['portrait', 'profile', 'actress', 'avatar']):
                                logging.info(f"🖼️ Found Google Images portrait: {src}")
                                return src
                    
                    # If no specific portrait found, return the first image
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        if src and src.startswith('http') and not src.endswith('.webp'):
                            logging.info(f"🖼️ Found Google Images image: {src}")
                            return src
                else:
                    logging.warning(f"❌ Failed to fetch Google Images for {clean_name}: {response.status}")
            
            logging.warning(f"⚠️ No Google Images portrait found for {clean_name}")
            return None
                
        except Exception as e:
            logging.error(f"❌ Error searching Google Images for {clean_name}: {e}")
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
        Enhance metadata by searching for actress portraits on javdatabase.com.
        This method will be called after scraping the main metadata.
        """
        try:
            # Get actress information from metadata
            actress_name = None
            
            # Check different possible fields for actress name
            if metadata.get('detailed_metadata', {}).get('actress'):
                actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
            elif metadata.get('detailed_metadata', {}).get('actresses'):
                actress_name = metadata['detailed_metadata']['actresses'].split(',')[0].strip()
            elif metadata.get('all_details', {}).get('Actress'):
                actress_name = metadata['all_details']['Actress'].split(',')[0].strip()
            
            if not actress_name:
                logging.info(f"ℹ️ No actress name found in metadata, skipping portrait search")
                return metadata
            
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
            logging.info(f"🔍 Starting JAVmost scrape for {jav_code}")
            url = f"https://www5.javmost.com/search/{jav_code}/"
            
            # Ensure session is initialized
            if not hasattr(self, 'session') or self.session is None:
                import aiohttp
                self.session = aiohttp.ClientSession()
            
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
                    
                    # Look for search results - JAVmost has specific structure
                    # Find cards that contain the JAV code
                    results = soup.find_all('div', class_='card')
                    if not results:
                        # Try alternative selectors
                        results = soup.find_all('div', class_=lambda x: x and 'result' in x.lower())
                    if not results:
                        # Try finding any div that contains the JAV code
                        results = soup.find_all('div', string=lambda text: text and jav_code in text)
                    if not results:
                        # Last resort: look for any content containing the JAV code
                        results = [soup]  # Use the entire page if no specific results found
                    
                    if results:
                        logging.info(f"✅ Found {len(results)} results for {jav_code}")
                        
                        # Find the result that matches the exact JAV code
                        exact_match = None
                        for result in results:
                            # Check if this result contains the exact JAV code
                            result_text = result.get_text()
                            if jav_code in result_text:
                                # Check if it's the exact match (not a variant)
                                title_elem = result.find('h1', class_='card-title')
                                if title_elem:
                                    title_text = title_elem.get_text().strip()
                                    if title_text == jav_code:
                                        exact_match = result
                                        break
                        
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
                                        actress_text = actress_link.get_text().strip()
                        
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