#!/usr/bin/env python3
"""Scrape a whole library folder without the web page.

Trailers are saved beside the videos on this machine. A repeat run skips a
title that already has its NFO, cover, and trailer, so the large preview
files are not downloaded again.
"""

import argparse
import signal
import sys

from app import _get_job_status_copy, reset_job_status, run_scraping_job, update_job_status


def _settings(folder, args):
    return {
        'create_nfo': not args.no_nfo,
        'download_cover': not args.no_cover,
        'download_trailer': not args.no_trailer,
        'organize_files': bool(args.organize) and not args.audit,
        'audit': bool(args.audit),
        'media_server': args.media_server,
        'library': args.library,
        'skip_complete': not args.force,
        'folder_path': folder,
    }


def _stop(signum, frame):
    update_job_status(running=False, message='Stopping after the current title')
    print('Stopping after the current title.', flush=True)


def run_folder(folder, args):
    reset_job_status()
    update_job_status(running=True, message=f'Starting {folder}')
    print(f'Scraping {folder}', flush=True)
    run_scraping_job(folder, _settings(folder, args))
    status = _get_job_status_copy()
    print(status.get('message') or 'Finished.', flush=True)
    if status.get('error'):
        print(status['error'], file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Scrape every title in a library folder and write the files beside the videos.'
    )
    parser.add_argument(
        'folders',
        nargs='+',
        help='Folder on this machine. Inside the QNAP container that is /library.',
    )
    parser.add_argument('--library', choices=('jav', 'hentai'), default='jav')
    parser.add_argument(
        '--media-server',
        default='plex',
        choices=('plex', 'all', 'jellyfin', 'emby', 'kodi'),
    )
    parser.add_argument('--no-nfo', action='store_true', help='Do not write NFO files.')
    parser.add_argument('--no-cover', action='store_true', help='Do not download covers.')
    parser.add_argument('--no-trailer', action='store_true', help='Do not download trailers.')
    parser.add_argument(
        '--organize',
        action='store_true',
        help='Move videos into the organized layout. Off by default, so an existing library stays where it is.',
    )
    parser.add_argument(
        '--audit',
        action='store_true',
        help='Refresh artwork and trailers beside each video. Videos are not moved.',
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Redo titles that already have an NFO, cover, and trailer.',
    )
    args = parser.parse_args(argv)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    failed = 0
    try:
        for folder in args.folders:
            failed += run_folder(folder, args)
    except KeyboardInterrupt:
        update_job_status(running=False)
        print('Stopped.', flush=True)
        return 130
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
