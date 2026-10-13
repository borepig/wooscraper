"""Serve the web UI on HTTP and HTTPS.

HTTPS is required for the browser's real folder picker
(window.showDirectoryPicker). Without it Chrome only offers
<input type=file>, which shows an "Upload files to this site?" prompt.
"""
from __future__ import annotations

import os
import ssl
import threading
from pathlib import Path

from werkzeug.serving import make_server

from app import app


def _ensure_certs(cert_dir: Path) -> tuple[Path, Path]:
    cert = cert_dir / 'cert.pem'
    key = cert_dir / 'key.pem'
    if cert.is_file() and key.is_file():
        return cert, key
    # Image build should have created these; fall back to /tmp if needed.
    fallback = Path('/tmp/wooscraper-certs')
    fallback.mkdir(parents=True, exist_ok=True)
    cert = fallback / 'cert.pem'
    key = fallback / 'key.pem'
    if cert.is_file() and key.is_file():
        return cert, key
    import subprocess

    subprocess.run(
        [
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
            '-keyout', str(key), '-out', str(cert),
            '-days', '3650', '-nodes',
            '-subj', '/CN=wooscraper',
        ],
        check=True,
        capture_output=True,
    )
    return cert, key


def main() -> None:
    http_port = int(os.environ.get('PORT', '5000'))
    https_port = int(os.environ.get('HTTPS_PORT', '5443'))
    cert_dir = Path(os.environ.get('CERT_DIR', '/app/certs'))

    http_server = make_server('0.0.0.0', http_port, app, threaded=True)
    threading.Thread(target=http_server.serve_forever, daemon=True, name='http').start()
    print(f'HTTP  on :{http_port}', flush=True)

    try:
        cert, key = _ensure_certs(cert_dir)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        https_server = make_server('0.0.0.0', https_port, app, threaded=True, ssl_context=context)
        print(f'HTTPS on :{https_port} (use this for the system folder picker)', flush=True)
        https_server.serve_forever()
    except FileNotFoundError:
        print('openssl not found — HTTPS disabled; folder picker will ask for a path', flush=True)
        http_server.serve_forever()
    except Exception as error:
        print(f'HTTPS failed ({error}) — continuing on HTTP only', flush=True)
        http_server.serve_forever()


if __name__ == '__main__':
    main()
