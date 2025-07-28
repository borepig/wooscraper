from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import asyncio
import os
import json
from pathlib import Path
from scraper_engine import JAVScraperEngine
import logging
import threading
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Global variables for job tracking
current_job = None
job_status = {
    'running': False,
    'progress': 0,
    'total_files': 0,
    'processed_files': 0,
    'current_file': '',
    'results': [],
    'error': None
}

def reset_job_status():
    """Reset job status to initial state."""
    global job_status
    job_status = {
        'running': False,
        'progress': 0,
        'total_files': 0,
        'processed_files': 0,
        'current_file': '',
        'results': [],
        'error': None
    }

@app.route('/')
def index():
    """Main page with the scraper UI."""
    return render_template('index.html')

@app.route('/api/scan-folder', methods=['POST'])
def scan_folder():
    """Scan folder for JAV files without scraping."""
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')
        
        # Debug logging
        logging.info(f"Scan folder request: '{folder_path}'")
        logging.info(f"Current working directory: {os.getcwd()}")
        
        if not folder_path:
            return jsonify({'error': 'No folder path provided'}), 400
        
        # Convert relative path to absolute path
        if not os.path.isabs(folder_path):
            # Try to resolve relative path
            resolved_path = os.path.abspath(folder_path)
            logging.info(f"Converted relative path '{folder_path}' to absolute path '{resolved_path}'")
            folder_path = resolved_path
        
        logging.info(f"Final absolute path: {folder_path}")
        
        # Check if path exists
        if not os.path.exists(folder_path):
            return jsonify({'error': f'Folder does not exist: {folder_path}'}), 400
        
        # Check if it's a directory
        if not os.path.isdir(folder_path):
            return jsonify({'error': f'Path is not a directory: {folder_path}'}), 400
        
        # Check if directory is readable
        if not os.access(folder_path, os.R_OK):
            return jsonify({'error': f'Directory is not readable: {folder_path}'}), 400
            
        # Initialize scraper engine
        engine = JAVScraperEngine()
        files = engine.scan_folder(folder_path)
        
        logging.info(f"Found {len(files)} JAV files in {folder_path}")
        
        return jsonify({
            'success': True,
            'files': files,
            'count': len(files),
            'resolved_path': folder_path  # Return the resolved absolute path
        })
    except Exception as e:
        logging.error(f"Error scanning folder: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-scraping', methods=['POST'])
def start_scraping():
    """Start the scraping process."""
    global current_job, job_status
    
    if job_status['running']:
        return jsonify({'error': 'Job already running'}), 400
        
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')
        
        # Get UI settings
        ui_settings = {
            'create_nfo': data.get('create_nfo', True),
            'download_cover': data.get('download_cover', True),
            'organize_files': data.get('organize_files', True),
            'folder_path': folder_path  # Pass the selected folder path for organization
        }
        
        logging.info(f"📥 Raw data from UI: {data}")
        logging.info(f"📥 UI Settings processed: {ui_settings}")
        logging.info(f"📥 organize_files from UI: {data.get('organize_files')}")
        logging.info(f"📥 organize_files default: {data.get('organize_files', True)}")
        
        if not folder_path:
            return jsonify({'error': 'No folder path provided'}), 400
        
        # Convert relative path to absolute path
        if not os.path.isabs(folder_path):
            # Try to resolve relative path
            resolved_path = os.path.abspath(folder_path)
            logging.info(f"Converted relative path '{folder_path}' to absolute path '{resolved_path}'")
            folder_path = resolved_path
        
        if not os.path.exists(folder_path):
            return jsonify({'error': f'Folder does not exist: {folder_path}'}), 400
            
        # Reset job status
        reset_job_status()
        job_status['running'] = True
        
        # Start scraping in background thread with UI settings
        thread = threading.Thread(target=run_scraping_job, args=(folder_path, ui_settings))
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True, 'message': 'Scraping started'})
    except Exception as e:
        logging.error(f"Error starting scraping: {e}")
        job_status['error'] = str(e)
        job_status['running'] = False
        return jsonify({'error': str(e)}), 500

def run_scraping_job(folder_path, ui_settings):
    """Run the scraping job in background thread."""
    global job_status
    
    async def async_scraping():
        try:
            logging.info(f"🚀 Starting scraping job with detailed logging")
            logging.info(f"📁 Folder to scan: {folder_path}")
            logging.info(f"⚙️ UI Settings: {ui_settings}")
            
            async with JAVScraperEngine() as engine:
                # Scan for files
                logging.info(f"🔍 Scanning folder for JAV files: {folder_path}")
                files = engine.scan_folder(folder_path)
                job_status['total_files'] = len(files)
                logging.info(f"📊 Found {len(files)} JAV files to process")
                
                if len(files) == 0:
                    error_msg = 'No JAV files found in folder'
                    logging.error(f"❌ {error_msg}")
                    job_status['error'] = error_msg
                    job_status['running'] = False
                    return
                
                results = []
                for i, file_info in enumerate(files):
                    if not job_status['running']:
                        logging.info(f"⏹️ Job stopped by user")
                        break
                        
                    jav_code = file_info['jav_code']
                    job_status['current_file'] = jav_code
                    job_status['processed_files'] = i
                    job_status['progress'] = int((i / len(files)) * 100)
                    job_status['message'] = f'Processing {jav_code} ({i+1}/{len(files)})'
                    
                    logging.info(f"🎬 ===== Processing {jav_code} ({i+1}/{len(files)}) =====")
                    logging.info(f"📄 File info: {file_info}")
                    
                    try:
                        # Scrape metadata
                        job_status['message'] = f'Scraping metadata for {jav_code}...'
                        logging.info(f"🔍 Starting metadata scraping for {jav_code}")
                        metadata = await engine.scrape_all_sites(jav_code)
                        metadata.update(file_info)
                        logging.info(f"✅ Metadata scraping completed for {jav_code}")
                        logging.info(f"📊 Metadata source: {metadata.get('source', 'unknown')}")
                        logging.info(f"📊 Metadata details: {metadata.get('detailed_metadata', {}).keys()}")
                        
                        # Determine output folder based on UI settings
                        organize_files = ui_settings.get('organize_files', True)
                        logging.info(f"🔧 UI Settings analysis:")
                        logging.info(f"   📋 organize_files: {organize_files}")
                        logging.info(f"   📋 folder_path: {ui_settings.get('folder_path', 'Not set')}")
                        logging.info(f"   📋 download_cover: {ui_settings.get('download_cover', True)}")
                        logging.info(f"🔧 Original video folder: {file_info['folder']}")
                        logging.info(f"🔧 Original video path: {file_info['file_path']}")
                        
                        if organize_files:
                            logging.info(f"📁 ==== FOLDER ORGANIZATION MODE ====")
                            # Create organized folder structure: videos/actress_name/jav_code/
                            # Use the selected folder from UI settings, not the video's current folder
                            selected_folder = Path(ui_settings.get('folder_path', file_info['folder']))
                            logging.info(f"🎯 Selected base folder: {selected_folder}")
                            
                            # Always create organized structure under selected folder, regardless of existing nested folders
                            videos_base = selected_folder / "videos"
                            logging.info(f"📁 Videos base folder: {videos_base}")
                            
                            # Get actress name from detailed metadata
                            actress_name = ""
                            if metadata.get('detailed_metadata', {}).get('actress'):
                                actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
                                logging.info(f"🎭 Found actress in metadata: '{actress_name}'")
                            elif metadata.get('detailed_metadata', {}).get('actresses'):
                                actress_name = metadata['detailed_metadata']['actresses'].split(',')[0].strip()
                                logging.info(f"🎭 Found actress in actresses field: '{actress_name}'")
                            else:
                                logging.warning(f"⚠️ No actress name found in metadata")
                            
                            # Clean actress name for folder creation (remove special characters)
                            if actress_name:
                                import re
                                original_actress_name = actress_name
                                actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
                                actress_name = actress_name.strip()
                                logging.info(f"🎭 Actress name cleaned: '{original_actress_name}' → '{actress_name}'")
                            
                            # Create folder structure
                            if actress_name:
                                actress_folder = videos_base / actress_name
                                output_folder = actress_folder / jav_code
                                logging.info(f"📁 Actress folder: {actress_folder}")
                                logging.info(f"📁 Final output folder: {output_folder}")
                            else:
                                # Fallback if no actress name
                                output_folder = videos_base / jav_code
                                logging.info(f"⚠️ No actress name, using fallback folder: {output_folder}")
                            
                            # Check if this exact folder already exists to avoid nested creation
                            if output_folder.exists():
                                logging.info(f"⚠️ Target folder already exists: {output_folder}")
                                logging.info(f"⚠️ Will use existing folder to avoid nested structure")
                                logging.info(f"📁 Existing folder contents: {list(output_folder.iterdir())}")
                            else:
                                logging.info(f"📁 Creating new folder structure...")
                                output_folder.mkdir(parents=True, exist_ok=True)
                                logging.info(f"✅ Created new folder: {output_folder}")
                            
                            logging.info(f"📁 ==== FINAL FOLDER STRUCTURE ====")
                            logging.info(f"   📁 Selected folder: {selected_folder}")
                            logging.info(f"   📁 Videos folder: {videos_base}")
                            logging.info(f"   📁 Actress folder: {actress_folder if actress_name else 'N/A'}")
                            logging.info(f"   📁 Final folder: {output_folder}")
                            
                            # Move and rename video file to organized structure
                            original_video_path = Path(file_info['file_path'])
                            new_video_path = output_folder / f"{jav_code}{original_video_path.suffix}"
                            
                            logging.info(f"🎬 ==== VIDEO FILE MOVEMENT ====")
                            logging.info(f"   📄 Original video: {original_video_path}")
                            logging.info(f"   📄 Target video: {new_video_path}")
                            logging.info(f"   📄 Original exists: {original_video_path.exists()}")
                            logging.info(f"   📄 Target exists: {new_video_path.exists()}")
                            
                            # Always move video to organized structure, regardless of current location
                            if original_video_path.exists():
                                import shutil
                                # Check if target file already exists
                                if new_video_path.exists():
                                    logging.warning(f"⚠️ Target video already exists: {new_video_path}")
                                    logging.warning(f"⚠️ Skipping video move to avoid overwrite")
                                else:
                                    logging.info(f"🔄 Moving video file...")
                                    shutil.move(str(original_video_path), str(new_video_path))
                                    logging.info(f"✅ Successfully moved video from {original_video_path} to {new_video_path}")
                            else:
                                logging.error(f"❌ Original video not found: {original_video_path}")
                        else:
                            logging.info(f"📁 ==== NO ORGANIZATION MODE ====")
                            # Use the folder where the video file is located
                            video_file_path = Path(file_info['file_path'])
                            output_folder = video_file_path.parent
                            logging.info(f"✅ Video file path: {video_file_path}")
                            logging.info(f"✅ Video folder: {output_folder}")
                            logging.info(f"✅ Metadata files will be saved in: {output_folder}")
                        
                        # Create NFO file directly from metadata (no metadata.json needed)
                        job_status['message'] = f'Creating NFO file for {jav_code}...'
                        nfo_path = output_folder / "movie.nfo"
                        logging.info(f"📄 ==== NFO FILE CREATION ====")
                        logging.info(f"   📄 NFO path: {nfo_path}")
                        logging.info(f"   📄 Output folder: {output_folder}")
                        logging.info(f"   📄 Output folder exists: {output_folder.exists()}")
                        
                        engine.create_nfo_file(metadata, str(nfo_path))
                        logging.info(f"✅ Successfully created NFO file: {nfo_path}")
                        if nfo_path.exists():
                            size = nfo_path.stat().st_size
                            logging.info(f"📏 NFO file size: {size} bytes")
                        
                        # Download fanart and create poster
                        logging.info(f"🎨 ==== FANART AND POSTER CREATION ====")
                        # Prioritize fanart_url from detailed metadata, fallback to best_cover
                        fanart_url = None
                        if metadata.get('detailed_metadata', {}).get('fanart_url'):
                            fanart_url = metadata['detailed_metadata']['fanart_url']
                            logging.info(f"🎨 Using fanart URL from detailed metadata: {fanart_url}")
                        elif metadata.get('best_cover'):
                            fanart_url = metadata['best_cover']
                            logging.info(f"🎨 Using fallback cover URL: {fanart_url}")
                        else:
                            logging.warning(f"⚠️ No fanart URL found in metadata")
                            logging.info(f"📊 Available metadata keys: {list(metadata.get('detailed_metadata', {}).keys())}")
                        
                        if ui_settings.get('download_cover', True) and fanart_url:
                            fanart_path = output_folder / "fanart.jpg"
                            poster_path = output_folder / "poster.jpg"
                            
                            logging.info(f"🎨 Fanart download path: {fanart_path}")
                            logging.info(f"🎨 Poster creation path: {poster_path}")
                            
                            # Check if webp conversion is needed (for JAVmost)
                            needs_webp_conversion = metadata.get('detailed_metadata', {}).get('needs_webp_conversion', False)
                            webp_url = metadata.get('detailed_metadata', {}).get('webp_url')
                            
                            logging.info(f"🔄 Webp conversion check:")
                            logging.info(f"   🔄 needs_webp_conversion: {needs_webp_conversion}")
                            logging.info(f"   🔄 webp_url: {webp_url}")
                            
                            if needs_webp_conversion and webp_url:
                                logging.info(f"🔄 ==== WEBP CONVERSION MODE ====")
                                logging.info(f"🔄 Converting webp to jpg: {webp_url}")
                                logging.info(f"🔄 Target fanart path: {fanart_path}")
                                
                                if await engine.download_and_convert_webp_to_jpg(webp_url, str(fanart_path)):
                                    logging.info(f"✅ Webp conversion successful")
                                    # Create poster by cropping the right 47.125% of fanart
                                    logging.info(f"🎨 Creating poster from fanart...")
                                    engine.create_poster_from_fanart(str(fanart_path), str(poster_path))
                                    logging.info(f"✅ Successfully created fanart.jpg and poster.jpg for {jav_code}")
                                    logging.info(f"✅ Fanart location: {fanart_path}")
                                    logging.info(f"✅ Poster location: {poster_path}")
                                    
                                    # Verify file sizes
                                    if fanart_path.exists():
                                        fanart_size = fanart_path.stat().st_size
                                        logging.info(f"📏 Fanart file size: {fanart_size} bytes")
                                    if poster_path.exists():
                                        poster_size = poster_path.stat().st_size
                                        logging.info(f"📏 Poster file size: {poster_size} bytes")
                                else:
                                    logging.error(f"❌ Failed to convert webp for {jav_code}")
                            else:
                                logging.info(f"📄 ==== REGULAR IMAGE DOWNLOAD MODE ====")
                                # Regular image download
                                logging.info(f"📄 Downloading regular image: {fanart_url}")
                                if await engine.download_image(fanart_url, str(fanart_path)):
                                    logging.info(f"✅ Regular image download successful")
                                    # Create poster by cropping the right 47.125% of fanart
                                    logging.info(f"🎨 Creating poster from fanart...")
                                    engine.create_poster_from_fanart(str(fanart_path), str(poster_path))
                                    logging.info(f"✅ Successfully created fanart.jpg and poster.jpg for {jav_code}")
                                    logging.info(f"✅ Fanart location: {fanart_path}")
                                    logging.info(f"✅ Poster location: {poster_path}")
                                    
                                    # Verify file sizes
                                    if fanart_path.exists():
                                        fanart_size = fanart_path.stat().st_size
                                        logging.info(f"📏 Fanart file size: {fanart_size} bytes")
                                    if poster_path.exists():
                                        poster_size = poster_path.stat().st_size
                                        logging.info(f"📏 Poster file size: {poster_size} bytes")
                                else:
                                    logging.error(f"❌ Failed to download fanart for {jav_code}")
                        else:
                            if not ui_settings.get('download_cover', True):
                                logging.info(f"ℹ️ Cover download disabled in UI settings")
                            else:
                                logging.warning(f"⚠️ No fanart URL available for {jav_code}")
                        
                        # Download actress portrait if available
                        logging.info(f"🎭 ==== ACTRESS PORTRAIT DOWNLOAD ====")
                        actress_name = ""
                        if metadata.get('detailed_metadata', {}).get('actress'):
                            actress_name = metadata['detailed_metadata']['actress'].split(',')[0].strip()
                            logging.info(f"🎭 Found actress name: '{actress_name}'")
                        else:
                            logging.info(f"ℹ️ No actress name found in metadata")
                        
                        if actress_name and ui_settings.get('download_cover', True):
                            # Clean actress name for filename
                            import re
                            original_actress_name = actress_name
                            clean_actress_name = re.sub(r'[<>:"/\\|?*]', '', actress_name)
                            clean_actress_name = clean_actress_name.replace(' ', '_')
                            logging.info(f"🎭 Actress name cleaned: '{original_actress_name}' → '{clean_actress_name}'")
                            
                            portrait_path = output_folder / f"{clean_actress_name}_portrait.jpg"
                            logging.info(f"🎭 Portrait save path: {portrait_path}")
                            
                            logging.info(f"🎭 Searching for actress portrait: {actress_name}")
                            
                            # Search for actress portrait using the enhanced method
                            actress_portrait_url = await engine.search_actress_portrait(actress_name)
                            
                            if actress_portrait_url:
                                logging.info(f"🎭 Found portrait URL: {actress_portrait_url}")
                                logging.info(f"🎭 Attempting to download portrait...")
                                
                                if await engine.download_image(actress_portrait_url, str(portrait_path)):
                                    logging.info(f"✅ Successfully downloaded actress portrait: {portrait_path}")
                                    # Check file size
                                    if portrait_path.exists():
                                        size = portrait_path.stat().st_size
                                        logging.info(f"📏 Portrait file size: {size} bytes")
                                else:
                                    logging.error(f"❌ Failed to download actress portrait for {actress_name}")
                                    logging.error(f"❌ Portrait URL: {actress_portrait_url}")
                                    logging.error(f"❌ Portrait path: {portrait_path}")
                            else:
                                logging.warning(f"⚠️ No actress portrait found for {actress_name}")
                                logging.warning(f"⚠️ Portrait search returned no results")
                        else:
                            if not actress_name:
                                logging.info(f"ℹ️ No actress name found, skipping portrait download")
                            else:
                                logging.info(f"ℹ️ Cover download disabled in UI settings, skipping portrait")
                            
                        results.append(metadata)
                        job_status['message'] = f'Completed {jav_code}'
                        
                    except Exception as e:
                        logging.error(f"Error processing {jav_code}: {e}")
                        job_status['error'] = f"Error processing {jav_code}: {str(e)}"
                        job_status['message'] = f'Error processing {jav_code}: {str(e)}'
                        results.append({
                            'jav_code': jav_code,
                            'error': str(e),
                            'file_path': file_info['file_path']
                        })
                
                job_status['results'] = results
                job_status['progress'] = 100
                job_status['processed_files'] = len(files)
                job_status['current_file'] = 'Completed'
                
        except Exception as e:
            logging.error(f"Error in scraping job: {e}")
            job_status['error'] = str(e)
        finally:
            job_status['running'] = False
    
    # Run async function in thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(async_scraping())
    loop.close()

@app.route('/api/job-status')
def get_job_status():
    """Get current job status."""
    return jsonify(job_status)

@app.route('/api/stop-scraping', methods=['POST'])
def stop_scraping():
    """Stop the current scraping job."""
    global job_status
    job_status['running'] = False
    return jsonify({'success': True, 'message': 'Job stopped'})

@app.route('/api/test-connection')
def test_connection():
    """Test connection to scraping sites."""
    async def test_sites():
        async with JAVScraperEngine() as engine:
            test_code = "ABC-123"  # Test code
            results = await engine.scrape_all_sites(test_code)
            return results
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(test_sites())
        loop.close()
        
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/config')
def get_config():
    """Get current configuration."""
    try:
        engine = JAVScraperEngine()
        return jsonify(engine.config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/common-paths')
def get_common_paths():
    """Get common video folder paths."""
    import os
    from pathlib import Path
    
    common_paths = []
    
    # Check common locations
    locations = [
        os.path.expanduser("~/media/Others/JAV"),
        os.path.expanduser("~/Videos"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Desktop"),
        "/mnt",
        "/media",
        "./test_videos"
    ]
    
    for location in locations:
        if os.path.exists(location):
            try:
                # Look for JAV-like folders
                for item in os.listdir(location):
                    item_path = os.path.join(location, item)
                    if os.path.isdir(item_path):
                        # Check if it contains video files
                        video_count = 0
                        try:
                            for file in os.listdir(item_path):
                                if file.lower().endswith(('.mp4', '.avi', '.mkv', '.wmv', '.mov')):
                                    video_count += 1
                                    break  # Found at least one video
                        except:
                            pass
                        
                        if video_count > 0:
                            common_paths.append({
                                'path': item_path,
                                'name': item,
                                'video_count': video_count
                            })
            except:
                pass
    
    return jsonify({
        'success': True,
        'paths': common_paths
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 