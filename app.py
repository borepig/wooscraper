"""
JAV Scraper Web Application
===========================

A web-based application for scraping metadata from JAV (Japanese Adult Video) content.

This application provides a user-friendly interface to scan folders containing JAV video files,
scrape metadata from multiple sources, and generate NFO files for media servers like Emby/Jellyfin/Kodi.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import asyncio
import os
import json
from pathlib import Path
from scraper_engine import (
    JAVScraperEngine,
    actor_image_rel,
    artwork_profile,
    copy_bytes_as,
    image_request_headers,
    remove_stray_audit_copies,
    title_assets_ready,
)
import logging
import threading
from datetime import datetime
import shutil
import re
import traceback

app = Flask(__name__)
CORS(app)

# Application metadata
__version__ = "1.7.0"
HOSTED = bool(os.environ.get('VERCEL'))
__author__ = "JAV Scraper Team"

# Global variables for job tracking with thread-safe lock
_job_status_lock = threading.Lock()
job_status = {
    'running': False,
    'progress': 0,
    'total_files': 0,
    'processed_files': 0,
    'current_file': '',
    'results': [],
    'error': None,
    'message': ''
}


def _get_job_status_copy():
    """Thread-safe getter for job status (internal helper)."""
    with _job_status_lock:
        return job_status.copy()


def update_job_status(**kwargs):
    """Thread-safe updater for job status."""
    with _job_status_lock:
        job_status.update(kwargs)

def reset_job_status():
    """
    Reset job status to initial state (thread-safe).

    This function resets all job tracking variables to their default values,
    clearing any previous job information and preparing for a new scraping operation.
    """
    global job_status
    with _job_status_lock:
        job_status = {
            'running': False,
            'progress': 0,
            'total_files': 0,
            'processed_files': 0,
            'current_file': '',
            'results': [],
            'error': None,
            'message': ''
        }

@app.route('/')
def index():
    """
    Main page with the scraper UI.

    Returns:
        str: Rendered HTML template for the main application page
    """
    return render_template('index.html', version=__version__)

@app.route('/api/scan-folder', methods=['POST'])
def scan_folder():
    """
    Scan folder for JAV files without scraping.

    This endpoint receives a folder path and scans it for JAV video files.
    It validates the path and returns information about the found files.

    Returns:
        Response: JSON response with either success or error information
    """
    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')
        library = data.get('library') or 'jav'

        # Debug logging
        logging.info(f"Scan folder request: '{folder_path}'")
        logging.info(f"Current working directory: {os.getcwd()}")

        if not folder_path:
            return jsonify({'error': 'No folder path provided'}), 400

        # Validate and sanitize the folder path to prevent directory traversal
        try:
            # Resolve the absolute path
            resolved_path = os.path.abspath(folder_path)

            # Check if path exists and is a directory
            if not os.path.exists(resolved_path):
                return jsonify({'error': f'Folder does not exist: {resolved_path}'}), 400

            if not os.path.isdir(resolved_path):
                return jsonify({'error': f'Path is not a directory: {resolved_path}'}), 400

            # Check if directory is readable
            if not os.access(resolved_path, os.R_OK):
                return jsonify({'error': f'Directory is not readable: {resolved_path}'}), 400

        except Exception as path_error:
            logging.error(f"Error validating folder path: {path_error}")
            return jsonify({'error': 'Invalid folder path provided'}), 400

        if library == 'hentai':
            from hentai_library import scan_for_ui
            files = scan_for_ui(resolved_path)
        else:
            engine = JAVScraperEngine()
            files = engine.scan_folder(resolved_path)

        logging.info(f"Found {len(files)} videos in {resolved_path}")

        return jsonify({
            'success': True,
            'files': files,
            'count': len(files),
            'resolved_path': resolved_path  # Return the resolved absolute path
        })
    except Exception as e:
        logging.error(f"Error scanning folder: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/start-scraping', methods=['POST'])
def start_scraping():
    """
    Start the scraping process.

    This endpoint initiates the metadata scraping process for JAV files in the specified folder.
    It validates the input parameters and starts a background thread to handle the scraping.

    Returns:
        Response: JSON response indicating success or failure of the operation
    """
    # Check if job is already running using thread-safe check
    with _job_status_lock:
        if job_status['running']:
            return jsonify({'error': 'Job already running'}), 400

    try:
        data = request.get_json()
        folder_path = data.get('folder_path', '')

        # Get UI settings
        ui_settings = {
            'create_nfo': data.get('create_nfo', True),
            'download_cover': data.get('download_cover', True),
            'download_trailer': data.get('download_trailer', True),
            'organize_files': data.get('organize_files', True),
            'audit': bool(data.get('audit')),
            'media_server': data.get('media_server') or 'plex',
            'library': data.get('library') or 'jav',
            'skip_complete': bool(data.get('skip_complete')),
            'folder_path': folder_path
        }

        logging.info(f"Raw data from UI: {data}")
        logging.info(f"UI Settings: {ui_settings}")

        if not folder_path:
            return jsonify({'error': 'No folder path provided'}), 400

        # Convert relative path to absolute path
        if not os.path.isabs(folder_path):
            resolved_path = os.path.abspath(folder_path)
            logging.info(f"Converted relative path '{folder_path}' to absolute path '{resolved_path}'")
            folder_path = resolved_path

        if not os.path.exists(folder_path):
            return jsonify({'error': f'Folder does not exist: {folder_path}'}), 400

        # Reset job status and set running
        reset_job_status()
        update_job_status(running=True)

        # Start scraping in background thread with UI settings
        thread = threading.Thread(target=run_scraping_job, args=(folder_path, ui_settings))
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'message': 'Scraping started'})
    except (OSError, ValueError, KeyError) as e:
        logging.error(f"Error starting scraping: {e}")
        update_job_status(error=str(e), running=False)
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logging.error(f"Unexpected error starting scraping: {e}")
        update_job_status(error=str(e), running=False)
        return jsonify({'error': str(e)}), 500

def run_scraping_job(folder_path, ui_settings):
    """Run the scraping job in background thread with thread-safe status updates."""

    async def async_scraping():
        try:
            logging.info(f"Starting scraping job")
            logging.info(f"Folder to scan: {folder_path}")
            logging.info(f"UI Settings: {ui_settings}")

            if (ui_settings.get('library') or 'jav') == 'hentai':
                from hentai_library import process_library
                def _keep_going():
                    with _job_status_lock:
                        return job_status['running']
                process_library(folder_path, ui_settings, update_job_status, _keep_going)
                return

            async with JAVScraperEngine() as engine:
                # Scan for files
                logging.info(f"Scanning folder for JAV files: {folder_path}")
                files = engine.scan_folder(folder_path)
                logging.info(f"Found {len(files)} JAV files to process")
                skipped = 0
                if ui_settings.get('skip_complete'):
                    pending = []
                    for file_info in files:
                        if title_assets_ready(
                            file_info['folder'],
                            create_nfo=ui_settings.get('create_nfo', True),
                            download_cover=ui_settings.get('download_cover', True),
                            download_trailer=ui_settings.get('download_trailer', True),
                            media_server=ui_settings.get('media_server') or 'plex',
                        ):
                            skipped += 1
                            continue
                        pending.append(file_info)
                    logging.info(f"Skipping {skipped} titles that already have their files")
                    files = pending
                update_job_status(total_files=len(files))

                if len(files) == 0:
                    if skipped:
                        update_job_status(
                            progress=100,
                            processed_files=0,
                            current_file='Completed',
                            message=f'Nothing to do. {skipped} titles already have their files.',
                        )
                        return
                    error_msg = 'No JAV files found in folder'
                    logging.error(error_msg)
                    update_job_status(error=error_msg, running=False)
                    return

                results = []
                for i, file_info in enumerate(files):
                    # Check if job is still running
                    with _job_status_lock:
                        if not job_status['running']:
                            logging.info("Job stopped by user")
                            break

                    jav_code = file_info['jav_code']
                    stray = remove_stray_audit_copies(file_info['file_path'])
                    if stray:
                        logging.info(f"{jav_code}: {stray}")
                        update_job_status(message=f'{jav_code}: {stray}')
                    update_job_status(
                        current_file=jav_code,
                        processed_files=i,
                        progress=int((i / len(files)) * 100),
                        message=f'Processing {jav_code} ({i+1}/{len(files)})'
                    )
                    
                    logging.info(f"🎬 ===== Processing {jav_code} ({i+1}/{len(files)}) =====")
                    logging.info(f"📄 File info: {file_info}")
                    
                    try:
                        # Scrape metadata
                        update_job_status(message=f'🔍 Scraping metadata for {jav_code}...')
                        logging.info(f"🔍 ==== METADATA SCRAPING START ====")
                        logging.info(f"🔍 JAV Code: {jav_code}")
                        logging.info(f"🔍 File: {file_info['file_path']}")
                        
                        # Update job status with detailed scraping info
                        update_job_status(message=f'🔍 Searching JAV.guru for {jav_code}...')
                        metadata = await engine.scrape_all_sites(jav_code, enhance=False)
                        metadata = await engine.attach_library_artwork(metadata)
                        if not (metadata.get('detailed_metadata') or {}).get('portraits'):
                            metadata = await engine.enhance_actress_metadata(metadata)
                            thumb = (metadata.get('detailed_metadata') or {}).get('thumb_url')
                            first_actress = ((metadata.get('detailed_metadata') or {}).get('actress') or '').split(',')[0].strip()
                            if thumb and first_actress:
                                metadata.setdefault('detailed_metadata', {})['portraits'] = [{
                                    'name': first_actress,
                                    'url': thumb,
                                    'file': actor_image_rel(first_actress),
                                }]
                        metadata.update(file_info)
                        
                        # Log detailed scraping results
                        source = metadata.get('source', 'unknown')
                        detailed_metadata = metadata.get('detailed_metadata', {})
                        
                        logging.info(f"✅ ==== METADATA SCRAPING COMPLETED ====")
                        logging.info(f"✅ Source: {source}")
                        logging.info(f"✅ Title: {metadata.get('title', 'N/A')}")
                        logging.info(f"✅ Studio: {detailed_metadata.get('studio', 'N/A')}")
                        logging.info(f"✅ Release Date: {detailed_metadata.get('release_date', 'N/A')}")
                        logging.info(f"✅ Duration: {detailed_metadata.get('duration', 'N/A')} mins")
                        logging.info(f"✅ Actresses: {detailed_metadata.get('actress', 'N/A')}")
                        logging.info(f"✅ Categories: {detailed_metadata.get('categories', [])}")
                        logging.info(f"✅ Series: {detailed_metadata.get('series', 'N/A')}")
                        logging.info(f"✅ Poster URL: {detailed_metadata.get('poster_url', 'N/A')}")
                        logging.info(f"✅ Fanart URL: {detailed_metadata.get('fanart_url', 'N/A')}")
                        
                        # Update job status with results
                        if source != 'unknown':
                            update_job_status(message=f'✅ Found metadata on {source} for {jav_code}')
                        else:
                            update_job_status(message=f'⚠️ No metadata found for {jav_code}')
                        
                        # Determine output folder based on UI settings
                        organize_files = ui_settings.get('organize_files', True)
                        if ui_settings.get('audit'):
                            organize_files = False
                        logging.info(f"🔧 UI Settings analysis:")
                        logging.info(f"   📋 organize_files: {organize_files}")
                        logging.info(f"   📋 folder_path: {ui_settings.get('folder_path', 'Not set')}")
                        logging.info(f"   📋 download_cover: {ui_settings.get('download_cover', True)}")
                        logging.info(f"🔧 Original video folder: {file_info['folder']}")
                        logging.info(f"🔧 Original video path: {file_info['file_path']}")
                        
                        if organize_files:
                            update_job_status(message=f'📁 Organizing files for {jav_code}...')
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
                                update_job_status(message=f'📁 Creating folder: {actress_name}/{jav_code}')
                            else:
                                # Use UNKNOWN as actress name for folder structure when no actress found
                                actress_folder = videos_base / "UNKNOWN"
                                output_folder = actress_folder / jav_code
                                logging.info(f"📁 UNKNOWN actress folder: {actress_folder}")
                                logging.info(f"📁 Final output folder: {output_folder}")
                                update_job_status(message=f'📁 Creating folder: UNKNOWN/{jav_code}')
                            
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
                                import errno
                                # Check if target file already exists
                                if new_video_path.exists():
                                    logging.warning(f"⚠️ Target video already exists: {new_video_path}")
                                    logging.warning(f"⚠️ Skipping video move to avoid overwrite")
                                    update_job_status(message=f'⚠️ Video already exists in target folder')
                                elif original_video_path.resolve() == new_video_path.resolve():
                                    update_job_status(message='Video is already in the organized folder')
                                else:
                                    logging.info(f"🔄 Renaming video file...")
                                    update_job_status(message=f'🔄 Renaming video into the organized folder...')
                                    try:
                                        os.rename(original_video_path, new_video_path)
                                        logging.info(f"✅ Renamed video from {original_video_path} to {new_video_path}")
                                        update_job_status(message=f'✅ Video renamed successfully')
                                    except OSError as move_error:
                                        if move_error.errno != errno.EXDEV:
                                            raise
                                        output_folder = original_video_path.parent
                                        logging.warning('Leaving the video in place because moving it would copy the file')
                                        update_job_status(message='Video left in place. Metadata will be written beside it.')
                            else:
                                logging.error(f"❌ Original video not found: {original_video_path}")
                                update_job_status(message=f'❌ Original video not found')
                        else:
                            logging.info(f"📁 ==== NO ORGANIZATION MODE ====")
                            # Use the folder where the video file is located
                            video_file_path = Path(file_info['file_path'])
                            output_folder = video_file_path.parent
                            logging.info(f"✅ Video file path: {video_file_path}")
                            logging.info(f"✅ Video folder: {output_folder}")
                            logging.info(f"✅ Metadata files will be saved in: {output_folder}")
                        
                        # Create NFO file directly from metadata (no metadata.json needed)
                        update_job_status(message=f'📄 Creating NFO file for {jav_code}...')
                        nfo_path = output_folder / "movie.nfo"
                        logging.info(f"📄 ==== NFO FILE CREATION ====")
                        logging.info(f"   📄 NFO path: {nfo_path}")
                        logging.info(f"   📄 Output folder: {output_folder}")
                        logging.info(f"   📄 Output folder exists: {output_folder.exists()}")
                        
                        # movie.nfo is written after the image files exist, so the
                        # actor thumbs and trailer tag can name those local files.
                        
                        # Download fanart and create poster
                        update_job_status(message=f'🎨 Checking for images for {jav_code}...')
                        logging.info(f"🎨 ==== FANART AND POSTER CREATION ====")
                        # Prioritize fanart_url from detailed metadata, fallback to best_cover
                        fanart_url = None
                        if metadata.get('detailed_metadata', {}).get('fanart_url'):
                            fanart_url = metadata['detailed_metadata']['fanart_url']
                            logging.info(f"🎨 Using fanart URL from detailed metadata: {fanart_url}")
                            update_job_status(message=f'🎨 Found fanart URL from metadata')
                        elif metadata.get('best_cover'):
                            fanart_url = metadata['best_cover']
                            logging.info(f"🎨 Using fallback cover URL: {fanart_url}")
                            update_job_status(message=f'🎨 Using fallback cover URL')
                        else:
                            logging.warning(f"⚠️ No fanart URL found in metadata")
                            logging.info(f"📊 Available metadata keys: {list(metadata.get('detailed_metadata', {}).keys())}")
                            update_job_status(message=f'⚠️ No fanart URL found')

                        auditing = bool(ui_settings.get('audit'))
                        if auditing:
                            update_job_status(message=f'🔎 Auditing metadata for {jav_code}...')
                            audit_notes = await engine.audit_folder(
                                metadata,
                                output_folder,
                                Path(file_info['file_path']),
                                download_cover=ui_settings.get('download_cover', True),
                                download_trailer=ui_settings.get('download_trailer', True),
                                media_server=ui_settings.get('media_server') or 'plex',
                            )
                            for note in audit_notes:
                                logging.info(f"🔎 {jav_code}: {note}")
                                update_job_status(message=f'{jav_code}: {note}')

                        media_server = ui_settings.get('media_server') or 'plex'
                        art = artwork_profile(media_server)
                        if not auditing and ui_settings.get('download_cover', True) and fanart_url:
                            fanart_path = output_folder / art['backgrounds'][0]
                            poster_path = output_folder / art['posters'][0]

                            logging.info(f"🎨 Fanart download path: {fanart_path}")
                            logging.info(f"🎨 Poster creation path: {poster_path}")

                            # Check if webp conversion is needed (for JAVmost)
                            needs_webp_conversion = metadata.get('detailed_metadata', {}).get('needs_webp_conversion', False)
                            webp_url = metadata.get('detailed_metadata', {}).get('webp_url')

                            logging.info(f"🔄 Webp conversion check:")
                            logging.info(f"   🔄 needs_webp_conversion: {needs_webp_conversion}")
                            logging.info(f"   🔄 webp_url: {webp_url}")

                            if needs_webp_conversion and webp_url:
                                update_job_status(message=f'🔄 Converting WebP image for {jav_code}...')
                                logging.info(f"🔄 ==== WEBP CONVERSION MODE ====")
                                logging.info(f"🔄 Converting webp to jpg: {webp_url}")
                                logging.info(f"🔄 Target fanart path: {fanart_path}")

                                try:
                                    # Ensure output folder exists before downloading
                                    output_folder.mkdir(parents=True, exist_ok=True)
                                    # Call the function directly without await since we're already in an async context
                                    if engine.download_and_convert_webp_to_jpg(webp_url, str(fanart_path)):
                                        logging.info(f"✅ Webp conversion successful")
                                        update_job_status(message=f'🎨 Creating poster from fanart...')
                                        # Create poster by cropping the right 47.125% of fanart
                                        logging.info(f"🎨 Creating poster from fanart...")
                                        engine.create_poster_from_fanart(str(fanart_path), str(poster_path))
                                        copy_bytes_as(fanart_path, art['backgrounds'])
                                        copy_bytes_as(poster_path, art['posters'])
                                        logging.info(f"✅ Successfully created artwork for {jav_code}")
                                        logging.info(f"✅ Fanart location: {fanart_path}")
                                        logging.info(f"✅ Poster location: {poster_path}")

                                        # Verify file sizes
                                        if fanart_path.exists():
                                            fanart_size = fanart_path.stat().st_size
                                            logging.info(f"📏 Fanart file size: {fanart_size} bytes")
                                        if poster_path.exists():
                                            poster_size = poster_path.stat().st_size
                                            logging.info(f"📏 Poster file size: {poster_size} bytes")

                                        update_job_status(message=f'✅ Images created successfully')
                                    else:
                                        logging.error(f"❌ Failed to convert webp for {jav_code}")
                                        update_job_status(message=f'❌ Failed to convert WebP image')
                                except Exception as e:
                                    logging.error(f"❌ Error in webp conversion: {e}")
                                    update_job_status(message=f'❌ Error converting webp image: {str(e)}')
                            else:
                                update_job_status(message=f'📄 Downloading image for {jav_code}...')
                                logging.info(f"📄 ==== REGULAR IMAGE DOWNLOAD MODE ====")
                                # Regular image download
                                logging.info(f"📄 Downloading regular image: {fanart_url}")
                                try:
                                    # Ensure output folder exists before downloading
                                    output_folder.mkdir(parents=True, exist_ok=True)
                                    # Call the async function with await
                                    if await engine.download_image(fanart_url, str(fanart_path)):
                                        logging.info(f"✅ Regular image download successful")
                                        update_job_status(message=f'🎨 Creating high-resolution poster from fanart...')
                                        logging.info(f"🎨 Creating poster from fanart...")
                                        engine.create_poster_from_fanart(str(fanart_path), str(poster_path))
                                        copy_bytes_as(fanart_path, art['backgrounds'])
                                        copy_bytes_as(poster_path, art['posters'])
                                        logging.info(f"✅ Successfully created artwork for {jav_code}")
                                        logging.info(f"✅ Fanart location: {fanart_path}")
                                        logging.info(f"✅ Poster location: {poster_path}")

                                        # Verify file sizes
                                        if fanart_path.exists():
                                            fanart_size = fanart_path.stat().st_size
                                            logging.info(f"📏 Fanart file size: {fanart_size} bytes")
                                        if poster_path.exists():
                                            poster_size = poster_path.stat().st_size
                                            logging.info(f"📏 Poster file size: {poster_size} bytes")

                                        update_job_status(message=f'✅ Images created successfully')
                                    else:
                                        logging.error(f"❌ Failed to download fanart for {jav_code}")
                                        update_job_status(message=f'❌ Failed to download image')
                                except Exception as e:
                                    logging.error(f"❌ Error in image download: {e}")
                                    update_job_status(message=f'❌ Error downloading image: {str(e)}')
                        elif not auditing:
                            if not ui_settings.get('download_cover', True):
                                logging.info(f"ℹ️ Cover download disabled in UI settings")
                            else:
                                logging.warning(f"⚠️ No fanart URL available for {jav_code}")

                        portraits = (metadata.get('detailed_metadata') or {}).get('portraits') or []
                        portrait_path = None
                        if not auditing and ui_settings.get('download_cover', True) and art['actor'] in ('local', 'both'):
                            output_folder.mkdir(parents=True, exist_ok=True)
                            for item in portraits:
                                portrait_url = item.get('url') or ''
                                portrait_name = actor_image_rel(item.get('name', ''))
                                if not portrait_url or not portrait_name:
                                    item['saved'] = False
                                    continue
                                portrait_path = output_folder / portrait_name
                                portrait_path.parent.mkdir(parents=True, exist_ok=True)
                                item['file'] = portrait_name
                                update_job_status(message=f"🎭 Downloading portrait of {item.get('name', '')}...")
                                try:
                                    if portrait_url.endswith('.webp'):
                                        saved = await engine.download_and_convert_webp_to_jpg(portrait_url, str(portrait_path))
                                    else:
                                        saved = await engine.download_image(portrait_url, str(portrait_path))
                                except Exception as portrait_error:
                                    logging.error(f"❌ Portrait download failed for {item.get('name')}: {portrait_error}")
                                    saved = False
                                item['saved'] = bool(saved and portrait_path.exists())
                                if not item['saved']:
                                    item['url'] = ''
                                    logging.error(f"❌ Failed to save portrait {portrait_path}")
                                else:
                                    logging.info(f"✅ Saved portrait {portrait_path} ({portrait_path.stat().st_size} bytes)")

                            trailer_url = (metadata.get('detailed_metadata') or {}).get('trailer_url')
                            trailer_path = output_folder / 'Trailers' / 'Preview.mp4'
                            segments = (metadata.get('detailed_metadata') or {}).get('trailer_segments') or []
                            if ui_settings.get('download_trailer', True) and (segments or trailer_url):
                                update_job_status(message=f'🎬 Downloading trailer for {jav_code}...')
                                saved_name = ''
                                if segments:
                                    saved_name = engine.save_hls_preview(segments, output_folder)
                                elif await engine.download_trailer(trailer_url, str(trailer_path)):
                                    saved_name = 'Trailers/Preview.mp4'
                                if saved_name:
                                    metadata.setdefault('detailed_metadata', {})['trailer_file'] = saved_name
                                    logging.info(f"✅ Saved trailer {output_folder / saved_name}")
                                else:
                                    logging.warning(f"⚠️ Trailer file was not saved; movie.nfo will keep the preview address")
                        elif not ui_settings.get('download_cover', True):
                            for item in portraits:
                                item['saved'] = False

                        update_job_status(message=f'📄 Creating NFO file for {jav_code}...')
                        if auditing and not ui_settings.get('create_nfo', True):
                            logging.info(f"Audit left the existing NFO in place for {jav_code}")
                        else:
                            engine.create_nfo_file(metadata, str(nfo_path), media_server=media_server)
                        if nfo_path.exists():
                            logging.info(f"✅ NFO file created: {nfo_path} ({nfo_path.stat().st_size} bytes)")
                            update_job_status(message=f'✅ NFO file created ({nfo_path.stat().st_size} bytes)')
                        else:
                            update_job_status(message='❌ Failed to create NFO file')

                        results.append(metadata)
                        update_job_status(message=f'✅ Completed {jav_code} successfully')
                        logging.info(f"✅ ==== COMPLETED PROCESSING {jav_code} ====")
                        logging.info(f"✅ File: {file_info['file_path']}")
                        logging.info(f"✅ Source: {metadata.get('source', 'unknown')}")
                        logging.info(f"✅ Title: {metadata.get('title', 'N/A')}")
                        logging.info(f"✅ Actress: {metadata.get('detailed_metadata', {}).get('actress', 'N/A')}")
                        logging.info(f"✅ Output folder: {output_folder}")
                        logging.info(f"✅ NFO file: {nfo_path.exists()}")
                        logging.info(f"✅ Fanart: {fanart_path.exists() if 'fanart_path' in locals() else 'N/A'}")
                        logging.info(f"✅ Poster: {poster_path.exists() if 'poster_path' in locals() else 'N/A'}")
                        logging.info(f"✅ Portrait: {portrait_path.exists() if 'portrait_path' in locals() else 'N/A'}")
                        
                    except Exception as e:
                        logging.error(f"❌ ==== ERROR PROCESSING {jav_code} ====")
                        logging.error(f"❌ Error: {e}")
                        logging.error(f"❌ File: {file_info['file_path']}")
                        logging.error(f"❌ Exception type: {type(e).__name__}")
                        import traceback
                        logging.error(f"❌ Traceback: {traceback.format_exc()}")
                        update_job_status(error=f"Error processing {jav_code}: {str(e)}")
                        update_job_status(message=f'❌ Error processing {jav_code}: {str(e)}')
                        results.append({
                            'jav_code': jav_code,
                            'error': str(e),
                            'file_path': file_info['file_path']
                        })
                
                # Final job completion logging
                logging.info(f"🎉 ==== JOB COMPLETION SUMMARY ====")
                logging.info(f"🎉 Total files processed: {len(files)}")
                logging.info(f"🎉 Successful: {len([r for r in results if 'error' not in r])}")
                logging.info(f"🎉 Failed: {len([r for r in results if 'error' in r])}")
                logging.info(f"🎉 Results: {results}")

                update_job_status(results=results, progress=100, processed_files=len(files), current_file='Completed')
                update_job_status(message=f'🎉 Job completed! Processed {len(files)} files')

        except Exception as e:
            logging.error(f"❌ ==== JOB FAILURE ====")
            logging.error(f"❌ Error in scraping job: {e}")
            logging.error(f"❌ Exception type: {type(e).__name__}")
            import traceback
            logging.error(f"❌ Traceback: {traceback.format_exc()}")
            update_job_status(error=str(e), message=f'❌ Job failed: {str(e)}')
        finally:
            update_job_status(running=False)

    # Run async function in thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(async_scraping())
    loop.close()

@app.route('/api/job-status')
def get_job_status():
    """Get current job status (thread-safe)."""
    return jsonify(_get_job_status_copy())

@app.route('/api/stop-scraping', methods=['POST'])
def stop_scraping():
    """Stop the current scraping job (thread-safe)."""
    update_job_status(running=False)
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
    library_root = os.environ.get('LIBRARY_ROOT', '')
    locations = [
        library_root,
        os.path.expanduser("~/media/Others/JAV"),
        os.path.expanduser("~/Videos"),
        os.path.expanduser("~/Downloads"),
        os.path.expanduser("~/Desktop"),
        "/library",
        "/mnt",
        "/media",
        "./test_videos"
    ]
    
    for location in locations:
        if location and os.path.exists(location):
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
                        except (OSError, PermissionError):
                            # Directory not readable or inaccessible
                            pass

                        if video_count > 0:
                            common_paths.append({
                                'path': item_path,
                                'name': item,
                                'video_count': video_count
                            })
            except (OSError, PermissionError):
                # Location not accessible
                pass
    
    return jsonify({
        'success': True,
        'paths': common_paths
    })

def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _present_lookup(metadata, media_server='plex'):
    """Shape a scrape result for the browser. Leave the raw HTML behind."""
    detailed = metadata.get('detailed_metadata') or {}
    details = metadata.get('all_details') or {}
    sources = metadata.get('sources') or {}
    code = metadata.get('jav_code') or detailed.get('code') or ''
    source = metadata.get('source') or ''
    title = (
        detailed.get('full_title')
        or metadata.get('best_title')
        or ''
    )
    cover = (
        detailed.get('fanart_url')
        or detailed.get('large_cover_url')
        or detailed.get('poster_url')
        or metadata.get('best_cover')
        or ''
    )
    actress = detailed.get('actress') or details.get('Actress') or details.get('Actor') or ''
    studio = detailed.get('studio') or details.get('Studio') or ''
    release_date = detailed.get('release_date') or details.get('Release Date') or ''
    runtime = str(detailed.get('runtime') or detailed.get('duration') or details.get('Runtime') or '')
    genres = detailed.get('category') or detailed.get('categories') or details.get('Genre') or ''
    if isinstance(genres, list):
        genres = ', '.join(str(item) for item in genres if item)
    plot = detailed.get('plot') or details.get('Plot') or ''
    if len(plot) > 1200:
        plot = plot[:1200].rstrip() + '…'
    portraits = [
        {
            'name': item.get('name') or '',
            'url': item.get('url') or '',
            'file': item.get('file') or '',
            'local': actor_image_rel(item.get('name') or ''),
        }
        for item in (detailed.get('portraits') or [])
        if item.get('url') and item.get('file')
    ]
    profile = artwork_profile(media_server)
    placeholder_title = f'{code} - JAV Content'
    found = bool(title) and title != placeholder_title and source not in ('fallback', 'basic')
    nfo = ''
    if found:
        record = dict(metadata)
        record['jav_code'] = code
        record['source'] = source
        record['media_server'] = media_server
        rendered = JAVScraperEngine().create_nfo_file(record, media_server=media_server)
        nfo = rendered if isinstance(rendered, str) else ''
    return {
        'found': found,
        'jav_code': code,
        'title': title if found else '',
        'source': source if found else '',
        'cover_url': cover if found else '',
        'poster_url': (detailed.get('poster_url') or '') if found else '',
        'trailer_url': (detailed.get('trailer_url') or '') if found else '',
        'trailer_segments': (detailed.get('trailer_segments') or []) if found else [],
        'portraits': portraits if found else [],
        'actress': actress if found else '',
        'studio': studio if found else '',
        'release_date': release_date if found else '',
        'runtime': runtime if found else '',
        'genres': genres if found else '',
        'plot': plot if found else '',
        'nfo': nfo,
        'artwork': {
            'posters': list(profile['posters']),
            'backgrounds': list(profile['backgrounds']),
            'actor_local': profile['actor'] in ('local', 'both'),
            'remove': [] if (media_server or 'plex').strip().lower() == 'all' else [
                item for item in (
                    'poster.jpg', 'folder.jpg', 'cover.jpg',
                    'fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg',
                )
                if item not in set(profile['posters']) | set(profile['backgrounds'])
            ],
            'remove_actors': profile['actor'] == 'url',
        },
        'sources_tried': list(sources.keys()),
    }


@app.route('/api/capabilities')
def capabilities():
    """Tell the page which tools this process can actually perform."""
    return jsonify({
        'hosted': HOSTED,
        'local_files': not HOSTED,
        'version': __version__,
    })


@app.route('/api/lookup', methods=['POST'])
def lookup_code():
    """Look up one code or filename and return metadata plus an NFO document."""
    try:
        data = request.get_json(silent=True) or {}
        query = str(data.get('query') or '').strip()
        media_server = str(data.get('media_server') or 'plex')
        if not query or len(query) > 500:
            return jsonify({'error': 'Enter a code or a filename.'}), 400
        if str(data.get('library') or '') == 'hentai':
            from hentai_library import present_lookup
            filename = str(data.get('filename') or query).strip()
            payload = present_lookup(query, filename, media_server)
            payload['query'] = query
            return jsonify(payload)

        engine = JAVScraperEngine()
        code = engine.extract_jav_code(query)
        if not code:
            return jsonify({'error': f'No code found in "{query}".', 'query': query}), 400

        async def _lookup():
            async with JAVScraperEngine() as scraper:
                metadata = await scraper.scrape_all_sites(code, enhance=False)
                return await scraper.attach_library_artwork(metadata)

        metadata = _run_async(_lookup())
        payload = _present_lookup(metadata, media_server)
        payload['query'] = query
        return jsonify(payload)
    except Exception as e:
        logging.error(f"Lookup failed: {e}")
        return jsonify({'error': 'Lookup failed. Try the code again.'}), 500


def _image_host_allowed(host):
    host = (host or '').lower()
    if host in {
        'jav.guru',
        'cdn.javsts.com',
        'javtrailers.com',
        'images.javtrailers.com',
        'pics.dmm.co.jp',
        'awsimgsrc.dmm.co.jp',
        'www.javdatabase.com',
        'javdatabase.com',
    }:
        return True
    return (
        host.endswith('.javmost.com')
        or host.endswith('.dmm.co.jp')
        or host.endswith('.javsts.com')
        or host.endswith('.javmiku.com')
        or host == 'javmiku.com'
        or host.endswith('.jdbstatic.com')
        or host == 'jdbstatic.com'
        or host.endswith('.myanimelist.net')
        or host == 'myanimelist.net'
        or host.endswith('.anilist.co')
        or host == 'anilist.co'
    )


@app.route('/api/image')
def proxy_image():
    """Fetch a cover through this app so the browser is not blocked by hotlink rules."""
    import urllib.request
    from urllib.parse import urlparse
    from flask import Response

    url = request.args.get('url', '')
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in ('http', 'https') or not _image_host_allowed(host):
        return jsonify({'error': 'That image host is not allowed.'}), 400

    class _GuardRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            new_host = (urlparse(newurl).hostname or '').lower()
            if not _image_host_allowed(new_host):
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    try:
        req = urllib.request.Request(url, headers=image_request_headers(url))
        opener = urllib.request.build_opener(_GuardRedirects)
        with opener.open(req, timeout=20) as resp:
            body = resp.read(8_000_000)
            content_type = (resp.headers.get('Content-Type') or 'image/jpeg').split(';')[0]
        if not content_type.startswith('image/'):
            content_type = 'image/jpeg'
        return Response(body, mimetype=content_type)
    except Exception as e:
        logging.warning(f"Image proxy failed: {e}")
        return jsonify({'error': 'Could not load that image.'}), 502


def _trailer_url_allowed(url):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    path = parsed.path
    return (
        parsed.scheme == 'https'
        and host == 'media.javtrailers.com'
        and (
            (path.startswith('/litevideo/freepv/') and path.endswith('.mp4'))
            or (path.startswith('/hlsvideo/freepv/') and path.endswith(('.m3u8', '.ts')))
        )
    )


@app.route('/api/media')
def proxy_media():
    """Send one slice of a preview file. The browser stitches the slices together.

    A whole preview is about 25MB, which is larger than one hosted response,
    so the page asks for 2.5MB at a time.
    """
    import urllib.request
    from flask import Response

    url = request.args.get('url', '')
    if not _trailer_url_allowed(url):
        return jsonify({'error': 'That preview address is not allowed.'}), 400
    try:
        start = int(request.args.get('start', '0'))
    except ValueError:
        return jsonify({'error': 'Bad start position.'}), 400
    if start < 0:
        return jsonify({'error': 'Bad start position.'}), 400

    chunk = 2_500_000
    end = start + chunk - 1
    headers = image_request_headers(url)
    headers['Range'] = f'bytes={start}-{end}'
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = 0
            span = resp.headers.get('Content-Range', '')
            if '/' in span:
                total = int(span.rsplit('/', 1)[-1] or 0)
            body = resp.read(chunk)
        if len(body) > chunk:
            return jsonify({'error': 'Preview slice was too large.'}), 502
        response = Response(body, mimetype='video/mp4')
        response.headers['X-Total-Size'] = str(total or (start + len(body)))
        return response
    except Exception as error:
        logging.warning(f"Trailer proxy failed: {error}")
        return jsonify({'error': 'Could not load that preview.'}), 502


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 