/**
 * Read and write a folder on the device running the browser.
 * Chrome and Edge on Windows and Ubuntu can save files into the folder.
 * iPhone, iPad, and Firefox cannot, so those download a zip instead.
 */
(function () {
    const VIDEO_EXT = ['.mp4', '.avi', '.mkv', '.wmv', '.mov'];
    let mode = null;
    let rootHandle = null;
    let picked = [];
    let cancelled = false;

    function libraryKind() {
        const choice = document.getElementById('libraryKind');
        return choice && choice.value === 'hentai' ? 'hentai' : 'jav';
    }

    function extractJavCode(filename) {
        const base = filename.replace(/\.[^.]+$/, '');
        const upper = base.toUpperCase();
        const fc2ppv = upper.match(/FC2[-_]?PPV[-_]?(\d{4,7})/);
        if (fc2ppv) {
            return 'FC2PPV-' + fc2ppv[1];
        }
        const fc2 = upper.match(/FC2[-_](\d{4,7})/);
        if (fc2) {
            return 'FC2PPV-' + fc2[1];
        }
        const patterns = [
            /([A-Z]{2,7})-?(\d{2,5})/,
            /([A-Z]{2,7})[-_](\d{2,5})/,
            /([A-Z]{2,7})(\d{2,5})/
        ];
        for (const pattern of patterns) {
            const match = upper.match(pattern);
            if (match) {
                return match[1] + '-' + match[2];
            }
        }
        return null;
    }

    function canWriteFolder() {
        return typeof window.showDirectoryPicker === 'function';
    }

    function clearSelection() {
        mode = null;
        rootHandle = null;
        picked = [];
        cancelled = false;
    }

    async function listDirectory(dirHandle, parentParts) {
        const found = [];
        for await (const [name, handle] of dirHandle.entries()) {
            if (handle.kind === 'directory') {
                const nested = await listDirectory(handle, parentParts.concat(name));
                found.push(...nested);
            } else if (VIDEO_EXT.some((ext) => name.toLowerCase().endsWith(ext))) {
                const hentai = libraryKind() === 'hentai';
                const code = extractJavCode(name);
                if (hentai && (parentParts.indexOf('Trailers') !== -1 || name.indexOf('.audit-') !== -1)) {
                    continue;
                }
                if (hentai || code) {
                    let parentName = parentParts[parentParts.length - 1] || name;
                    // Season 01 folders use the show folder name for AniList lookup.
                    if (hentai && /^Season \d+$/i.test(parentName) && parentParts.length >= 2) {
                        parentName = parentParts[parentParts.length - 2];
                    }
                    found.push({
                        name,
                        handle,
                        parent: dirHandle,
                        parentName,
                        relative: parentParts.concat(name).join('/'),
                        javCode: hentai ? parentName : code
                    });
                }
            }
        }
        return found;
    }

    function showPicked() {
        const files = picked.map((item) => ({
            jav_code: item.javCode,
            filename: item.name,
            file_path: item.relative
        }));
        if (typeof displayFiles === 'function') {
            displayFiles(files);
        }
        const start = document.getElementById('startBtn');
        const auditButton = document.getElementById('auditBtn');
        if (start) {
            start.disabled = files.length === 0;
        }
        if (auditButton) {
            auditButton.disabled = files.length === 0;
        }
        const path = document.getElementById('folderPath');
        if (path) {
            path.value = mode === 'write'
                ? '(this device) ' + (rootHandle.name || 'folder')
                : '(this device) selected files';
        }
    }

    function folderLabelFromFiles(files) {
        for (const file of files) {
            const relative = file.webkitRelativePath || file.name;
            const parts = relative.split('/').filter(Boolean);
            if (parts.length > 1) {
                return parts[0];
            }
        }
        return '';
    }

    function confirmNasPath(folderLabel) {
        const library = libraryKind() === 'hentai' ? 'hentai' : 'jav';
        const current = (document.getElementById('folderPath') && document.getElementById('folderPath').value || '').trim();
        const suggested = current && !current.startsWith('(this device)')
            ? current
            : '/library/' + library + (folderLabel ? '/' + folderLabel : '');
        const message = folderLabel
            ? 'You selected “‘ + folderLabel + '”.\n\nEnter the path on the NAS for that folder so scraping writes there (not an upload):'
            : 'Enter the path on the NAS for the folder you selected:';
        const fullPath = window.prompt(message, suggested);
        if (!fullPath || !fullPath.trim()) {
            return null;
        }
        return fullPath.trim();
    }

    async function choose() {
        cancelled = false;
        try {
            // Prefer the real system folder picker with write access when the browser allows it.
            if (canWriteFolder() && window.isSecureContext) {
                try {
                    rootHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
                } catch (error) {
                    if (error && error.name === 'AbortError') {
                        return;
                    }
                    document.getElementById('clientFilePicker').click();
                    return;
                }
                mode = 'write';
                picked = await listDirectory(rootHandle, []);
                showPicked();
                const message = picked.length
                    ? 'Found ' + picked.length + ' video' + (picked.length === 1 ? '' : 's') + ' — Start writes into this folder'
                    : (libraryKind() === 'hentai' ? 'No videos found in that folder' : 'No JAV videos found in that folder');
                if (typeof showNotification === 'function') {
                    showNotification(message, picked.length ? 'success' : 'warning');
                }
                return;
            }
            // Same system folder dialog via <input webkitdirectory>.
            document.getElementById('clientFilePicker').click();
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return;
            }
            if (typeof showNotification === 'function') {
                showNotification(error.message || 'Could not open that folder', 'error');
            }
        }
    }

    function onFileInput(event) {
        const files = Array.from(event.target.files || []);
        const folderLabel = folderLabelFromFiles(files);
        const hentai = libraryKind() === 'hentai';

        // On the NAS app: system picker only identifies the folder. Scraping uses the
        // server path so files are written in place — never upload/zip.
        if (window.serverHasLibrary) {
            clearSelection();
            const fullPath = confirmNasPath(folderLabel);
            event.target.value = '';
            if (!fullPath) {
                return;
            }
            const path = document.getElementById('folderPath');
            if (path) {
                path.value = fullPath;
            }
            if (typeof currentFolder !== 'undefined') {
                currentFolder = fullPath;
            }
            try {
                localStorage.setItem('lastFolderPath', fullPath);
            } catch (error) {
                /* ignore */
            }
            if (typeof showNotification === 'function') {
                showNotification('Folder path set: ' + fullPath + '. Click Scan Folder, then Start Scraping.', 'success');
            }
            return;
        }

        mode = 'download';
        rootHandle = null;
        picked = [];
        files.forEach((file) => {
            const relative = file.webkitRelativePath || file.name;
            const parts = relative.split('/').filter(Boolean);
            const code = extractJavCode(file.name);
            let parentName = parts.length > 1 ? parts[parts.length - 2] : file.name;
            if (hentai && /^Season \d+$/i.test(parentName) && parts.length >= 3) {
                parentName = parts[parts.length - 3];
            }
            if (hentai || code) {
                picked.push({
                    name: file.name,
                    handle: null,
                    parent: null,
                    parentName: parentName,
                    relative: relative,
                    javCode: hentai ? parentName : code
                });
            }
        });
        showPicked();
        const path = document.getElementById('folderPath');
        if (path && folderLabel) {
            path.value = '(this device) ' + folderLabel;
        }
        if (typeof showNotification === 'function') {
            showNotification(
                picked.length
                    ? 'Found ' + picked.length + ' video' + (picked.length === 1 ? '' : 's') +
                        (folderLabel ? ' in ' + folderLabel : '') + '. Start Scraping downloads a zip.'
                    : (hentai ? 'No videos in that folder' : 'No JAV videos in that selection'),
                picked.length ? 'success' : 'warning'
            );
        }
        event.target.value = '';
    }

    function progress(percent, text) {
        const section = document.getElementById('progressSection');
        const bar = document.getElementById('progressBar');
        const label = document.getElementById('progressText');
        if (section) {
            section.style.display = 'block';
        }
        if (bar) {
            bar.style.width = percent + '%';
            bar.textContent = percent + '%';
        }
        if (label) {
            label.textContent = text;
        }
    }

    async function lookup(filename, fileLabel) {
        const response = await fetch('/api/lookup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
            query: filename,
            filename: fileLabel || filename,
            media_server: (document.getElementById('mediaServer') || {}).value || 'plex',
            library: libraryKind()
        })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Lookup failed');
        }
        return data;
    }

    function isPreviewName(filename) {
        const lower = String(filename || '').toLowerCase();
        return lower === 'preview.mp4' || lower === 'preview.ts';
    }

    async function writeBytes(dirHandle, filename, bytes) {
        const lower = String(filename || '').toLowerCase();
        if (!isPreviewName(lower) && VIDEO_EXT.some((ext) => lower.endsWith(ext))) {
            throw new Error('Refusing to write a video file');
        }
        const fileHandle = await dirHandle.getFileHandle(filename, { create: true });
        const writable = await fileHandle.createWritable();
        await writable.write(bytes);
        await writable.close();
    }

    async function directoryFor(item, data, organize) {
        if (mode !== 'write') {
            return null;
        }
        if (!organize) {
            return item.parent;
        }
        const actress = ((data.actress || 'UNKNOWN').split(',')[0] || 'UNKNOWN')
            .replace(/[<>:"/\\|?*]/g, '')
            .trim() || 'UNKNOWN';
        const videos = await rootHandle.getDirectoryHandle('videos', { create: true });
        const actressDir = await videos.getDirectoryHandle(actress, { create: true });
        return actressDir.getDirectoryHandle(item.javCode, { create: true });
    }

    async function moveVideo(item, targetDir) {
        if (!item.handle || !item.handle.move || targetDir === item.parent) {
            return false;
        }
        const nextName = item.javCode + item.name.slice(item.name.lastIndexOf('.'));
        try {
            await item.handle.move(targetDir, nextName);
            return true;
        } catch (error) {
            return false;
        }
    }

    async function cropPoster(bytes) {
        try {
            const bitmap = await createImageBitmap(new Blob([bytes]));
            const cropWidth = Math.round(bitmap.width * 0.47125);
            const canvas = document.createElement('canvas');
            canvas.width = cropWidth;
            canvas.height = bitmap.height;
            const context = canvas.getContext('2d');
            context.drawImage(
                bitmap,
                bitmap.width - cropWidth,
                0,
                cropWidth,
                bitmap.height,
                0,
                0,
                cropWidth,
                bitmap.height
            );
            const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.95));
            return blob ? new Uint8Array(await blob.arrayBuffer()) : null;
        } catch (error) {
            return null;
        }
    }

    async function proxyImage(url) {
        const response = await fetch('/api/image?url=' + encodeURIComponent(url));
        if (!response.ok) {
            return null;
        }
        return new Uint8Array(await response.arrayBuffer());
    }

    async function proxyTrailer(url, onProgress) {
        const chunks = [];
        let start = 0;
        let total = 0;
        while (!total || start < total) {
            let response = null;
            for (let attempt = 0; attempt < 3; attempt += 1) {
                response = await fetch('/api/media?url=' + encodeURIComponent(url) + '&start=' + start);
                if (response.ok) {
                    break;
                }
            }
            if (!response || !response.ok) {
                return null;
            }
            const reported = Number(response.headers.get('X-Total-Size'));
            if (reported) {
                total = reported;
            }
            const piece = new Uint8Array(await response.arrayBuffer());
            if (!piece.length) {
                break;
            }
            chunks.push(piece);
            start += piece.length;
            if (typeof onProgress === 'function') {
                onProgress(start, total || start);
            }
            if (!total) {
                break;
            }
        }
        if (!chunks.length) {
            return null;
        }
        const joined = new Uint8Array(start);
        let offset = 0;
        chunks.forEach((piece) => {
            joined.set(piece, offset);
            offset += piece.length;
        });
        return joined;
    }

    function isVideoUrl(url) {
        const path = String(url || '').split('?')[0].toLowerCase();
        return path.endsWith('.ts') || path.endsWith('.mp4') || path.endsWith('.m3u8');
    }

    async function directBytes(url, onProgress) {
        if (typeof window.wooscraperDirect === 'function') {
            for (let attempt = 0; attempt < 3; attempt += 1) {
                const bytes = await window.wooscraperDirect(url);
                if (bytes && bytes.length) {
                    if (typeof onProgress === 'function') {
                        onProgress(bytes.length, bytes.length);
                    }
                    return bytes;
                }
            }
        }
        if (isVideoUrl(url)) {
            return proxyTrailer(url, onProgress);
        }
        return proxyImage(url);
    }

    function coverBytes(url) {
        return directBytes(url);
    }

    function trailerBytes(url, onProgress) {
        return directBytes(url, onProgress);
    }

    async function storeTrailer(target, zipEntries, folderName, filename, bytes) {
        if (!bytes) {
            return false;
        }
        if (target) {
            const extras = await target.getDirectoryHandle('Trailers', { create: true });
            await writeBytes(extras, filename, bytes);
        } else {
            zipEntries.push({ name: folderName + '/Trailers/' + filename, data: bytes });
        }
        return true;
    }

    async function storeFile(target, zipEntries, folderName, filename, bytes) {
        if (!bytes) {
            return false;
        }
        if (target) {
            await writeBytes(target, filename, bytes);
        } else {
            zipEntries.push({ name: folderName + '/' + filename, data: bytes });
        }
        return true;
    }

    function crc32(bytes) {
        let crc = -1;
        for (let i = 0; i < bytes.length; i += 1) {
            crc ^= bytes[i];
            for (let bit = 0; bit < 8; bit += 1) {
                const mask = -(crc & 1);
                crc = (crc >>> 1) ^ (0xedb88320 & mask);
            }
        }
        return (crc ^ -1) >>> 0;
    }

    function makeZip(entries) {
        const encoder = new TextEncoder();
        const parts = [];
        const central = [];
        let offset = 0;
        entries.forEach((entry) => {
            const name = encoder.encode(entry.name);
            const data = entry.data;
            const crc = crc32(data);
            const local = new DataView(new ArrayBuffer(30));
            local.setUint32(0, 0x04034b50, true);
            local.setUint16(4, 20, true);
            local.setUint16(6, 0x0800, true);
            local.setUint16(8, 0, true);
            local.setUint32(14, crc, true);
            local.setUint32(18, data.length, true);
            local.setUint32(22, data.length, true);
            local.setUint16(26, name.length, true);
            parts.push(new Uint8Array(local.buffer), name, data);
            const header = new DataView(new ArrayBuffer(46));
            header.setUint32(0, 0x02014b50, true);
            header.setUint16(4, 20, true);
            header.setUint16(6, 20, true);
            header.setUint16(8, 0x0800, true);
            header.setUint32(16, crc, true);
            header.setUint32(20, data.length, true);
            header.setUint32(24, data.length, true);
            header.setUint16(28, name.length, true);
            header.setUint32(42, offset, true);
            central.push(new Uint8Array(header.buffer), name);
            offset += 30 + name.length + data.length;
        });
        const centralSize = central.reduce((sum, part) => sum + part.length, 0);
        const end = new DataView(new ArrayBuffer(22));
        end.setUint32(0, 0x06054b50, true);
        end.setUint16(8, entries.length, true);
        end.setUint16(10, entries.length, true);
        end.setUint32(12, centralSize, true);
        end.setUint32(16, offset, true);
        const blobParts = parts.concat(central, [new Uint8Array(end.buffer)]);
        return new Blob(blobParts, { type: 'application/zip' });
    }

    function downloadBlob(blob, filename) {
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    async function readNamed(dir, name) {
        try {
            const handle = await dir.getFileHandle(name);
            const file = await handle.getFile();
            return new Uint8Array(await file.arrayBuffer());
        } catch (error) {
            return null;
        }
    }

    async function pixelsOf(bytes) {
        const bitmap = await createImageBitmap(new Blob([bytes]));
        const result = { pixels: bitmap.width * bitmap.height, width: bitmap.width };
        if (bitmap.close) {
            bitmap.close();
        }
        return result;
    }

    async function storeNested(target, zipEntries, folderName, relativePath, bytes) {
        const parts = String(relativePath || '').split('/').filter(Boolean);
        if (!parts.length || !bytes) {
            return false;
        }
        if (target) {
            let dir = target;
            for (let index = 0; index < parts.length - 1; index += 1) {
                dir = await dir.getDirectoryHandle(parts[index], { create: true });
            }
            await writeBytes(dir, parts[parts.length - 1], bytes);
            return true;
        }
        zipEntries.push({ name: [folderName].concat(parts).join('/'), data: bytes });
        return true;
    }

    async function readNested(dir, relativePath) {
        const parts = String(relativePath || '').split('/').filter(Boolean);
        if (!dir || parts.length < 2) {
            return parts.length === 1 ? readNamed(dir, parts[0]) : null;
        }
        let current = dir;
        for (let index = 0; index < parts.length - 1; index += 1) {
            try {
                current = await current.getDirectoryHandle(parts[index]);
            } catch (error) {
                return null;
            }
        }
        return readNamed(current, parts[parts.length - 1]);
    }

    async function chooseArtworkBytes(target, names, incoming) {
        let best = incoming || null;
        let bestPixels = -1;
        if (best) {
            try {
                bestPixels = (await pixelsOf(best)).pixels;
            } catch (error) {
                bestPixels = 0;
            }
        }
        if (!target) {
            return best;
        }
        for (let index = 0; index < names.length; index += 1) {
            const bytes = await readNamed(target, names[index]);
            if (!bytes) {
                continue;
            }
            try {
                const info = await pixelsOf(bytes);
                if (info.pixels > bestPixels) {
                    best = bytes;
                    bestPixels = info.pixels;
                }
            } catch (error) {
                if (!best) {
                    best = bytes;
                }
            }
        }
        return best;
    }

    async function fileReady(target, names) {
        for (let index = 0; index < names.length; index += 1) {
            if (await readNamed(target, names[index])) {
                return true;
            }
        }
        return false;
    }

    async function pruneArtwork(target, artwork) {
        if (!target || !artwork) {
            return;
        }
        const backgrounds = artwork.backgrounds || [];
        const posters = artwork.posters || [];
        const backgroundReady = await fileReady(target, backgrounds);
        const posterReady = await fileReady(target, posters);
        const backgroundNames = { 'fanart.jpg': true, 'background.jpg': true, 'backdrop.jpg': true, 'art.jpg': true };
        const posterNames = { 'poster.jpg': true, 'folder.jpg': true, 'cover.jpg': true };
        const remove = artwork.remove || [];
        for (let index = 0; index < remove.length; index += 1) {
            const name = remove[index];
            if (backgroundNames[name] && !backgroundReady) {
                continue;
            }
            if (posterNames[name] && !posterReady) {
                continue;
            }
            try {
                await target.removeEntry(name);
            } catch (error) {
                // The extra name was already absent.
            }
        }
        if (!artwork.remove_actors) {
            return;
        }
        const entries = [];
        for await (const [name, handle] of target.entries()) {
            entries.push([name, handle]);
        }
        for (let index = 0; index < entries.length; index += 1) {
            const name = entries[index][0];
            const handle = entries[index][1];
            if (handle.kind === 'file' && name.endsWith('_portrait.jpg')) {
                try {
                    await target.removeEntry(name);
                } catch (error) {
                    // Already gone.
                }
            }
        }
        try {
            await target.removeEntry('.actors', { recursive: true });
        } catch (error) {
            // No .actors folder.
        }
    }

    async function saveArtwork(target, zipEntries, folderName, image, artwork, audit) {
        const backgrounds = (artwork && artwork.backgrounds) || ['background.jpg'];
        const posters = (artwork && artwork.posters) || ['poster.jpg'];
        let source = image;
        let replaced = true;
        if (audit) {
            source = await chooseArtworkBytes(
                target,
                ['fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg'],
                image
            );
            replaced = true;
            if (!source) {
                return;
            }
        }
        for (let nameIndex = 0; nameIndex < backgrounds.length; nameIndex += 1) {
            const name = backgrounds[nameIndex];
            if (audit && name === backgrounds[0] && !replaced) {
                continue;
            }
            if (audit && name !== backgrounds[0] && target && !replaced && await readNamed(target, name)) {
                continue;
            }
            await storeFile(target, zipEntries, folderName, name, source);
        }
        const poster = target ? await readNamed(target, posters[0]) : null;
        let posterWidth = 0;
        if (poster) {
            try {
                posterWidth = (await pixelsOf(poster)).width;
            } catch (error) {
                posterWidth = 0;
            }
        }
        const needPoster = !audit || replaced || !poster || posterWidth <= 200;
        const cropped = (needPoster || posters.length > 1) ? await cropPoster(source) : null;
        for (let nameIndex = 0; nameIndex < posters.length; nameIndex += 1) {
            const name = posters[nameIndex];
            if (!needPoster && target && await readNamed(target, name)) {
                continue;
            }
            if (cropped) {
                await storeFile(target, zipEntries, folderName, name, cropped);
            }
        }
    }

    async function upgradeImage(target, filename, incoming) {
        if (!incoming) {
            return { bytes: null, write: false, width: 0 };
        }
        if (!target) {
            return { bytes: incoming, write: true, width: 0 };
        }
        const existing = await readNamed(target, filename);
        if (!existing) {
            return { bytes: incoming, write: true, width: 0 };
        }
        try {
            const next = await pixelsOf(incoming);
            const current = await pixelsOf(existing);
            if (next.pixels > current.pixels) {
                return { bytes: incoming, write: true, width: next.width };
            }
            return { bytes: existing, write: false, width: current.width };
        } catch (error) {
            return { bytes: incoming, write: true, width: 0 };
        }
    }

    async function fileExists(dir, name) {
        try {
            await dir.getFileHandle(name);
            return true;
        } catch (error) {
            return false;
        }
    }

    async function settleTrailers(target) {
        let extras = null;
        try {
            extras = await target.getDirectoryHandle('Trailers');
        } catch (error) {
            extras = null;
        }
        let have = '';
        if (extras && await fileExists(extras, 'Preview.mp4')) {
            have = 'Trailers/Preview.mp4';
        } else if (extras && await fileExists(extras, 'Preview.ts')) {
            have = 'Trailers/Preview.ts';
        }
        const sidecars = [['trailer.mp4', 'Preview.mp4'], ['trailer.ts', 'Preview.ts']];
        for (let index = 0; index < sidecars.length; index += 1) {
            const source = sidecars[index][0];
            const dest = sidecars[index][1];
            let handle = null;
            try {
                handle = await target.getFileHandle(source);
            } catch (error) {
                continue;
            }
            if (have) {
                await handle.remove();
                continue;
            }
            extras = await target.getDirectoryHandle('Trailers', { create: true });
            if (!handle.move) {
                continue;
            }
            await handle.move(extras, dest);
            have = 'Trailers/' + dest;
        }
        return have;
    }

    async function removeStrayAuditCopy(item) {
        if (!item.parent || !item.name) {
            return;
        }
        let original = null;
        try {
            original = await item.parent.getFileHandle(item.name);
        } catch (error) {
            return;
        }
        if (!original) {
            return;
        }
        const extras = [
            item.name + '.audit-tmp',
            item.name + '.audit-bak',
            item.name + '.audit-tmp.mp4',
            item.name + '.audit-tmp.mkv',
            item.name + '.audit-tmp.m4v',
            item.name + '.audit-tmp.mov'
        ];
        for (let index = 0; index < extras.length; index += 1) {
            try {
                const handle = await item.parent.getFileHandle(extras[index]);
                await handle.remove();
            } catch (error) {
                // The extra copy is already gone.
            }
        }
    }

    async function promoteHentaiThumb(sourceDir, episodeDir, originalStem, episodeFile) {
        if (!sourceDir || !episodeDir || !originalStem || !episodeFile) {
            return;
        }
        const episodeBase = episodeFile.replace(/\.[^.]+$/, '');
        const thumbName = episodeBase + '-thumb.jpg';
        const baseStem = originalStem.replace(/\s*\(\d+\)$/, '').trim();
        let bestHandle = null;
        let bestSize = -1;
        const extras = [];
        for await (const [name, handle] of sourceDir.entries()) {
            if (handle.kind !== 'file') {
                continue;
            }
            const lower = name.toLowerCase();
            if (!/\.(jpe?g|png|webp)$/i.test(name)) {
                continue;
            }
            if (['poster.jpg', 'folder.jpg', 'cover.jpg', 'fanart.jpg', 'background.jpg', 'backdrop.jpg', 'art.jpg'].indexOf(lower) !== -1) {
                continue;
            }
            if (/-thumb\./i.test(name)) {
                continue;
            }
            const stem = name.replace(/\.[^.]+$/, '');
            const stemBase = stem.replace(/\s*\(\d+\)$/, '').trim();
            if (stem !== originalStem && stemBase !== baseStem && stem.indexOf(baseStem) !== 0) {
                continue;
            }
            try {
                const file = await handle.getFile();
                if (file.size > bestSize) {
                    if (bestHandle) {
                        extras.push(bestHandle);
                    }
                    bestHandle = handle;
                    bestSize = file.size;
                } else {
                    extras.push(handle);
                }
            } catch (error) {
                // Ignore unreadable sidecars.
            }
        }
        if (!bestHandle) {
            return;
        }
        try {
            const file = await bestHandle.getFile();
            const bytes = new Uint8Array(await file.arrayBuffer());
            await writeBytes(episodeDir, thumbName, bytes);
            try {
                await bestHandle.remove();
            } catch (error) {
                // Source may already be gone after a move.
            }
            for (let index = 0; index < extras.length; index += 1) {
                try {
                    await extras[index].remove();
                } catch (error) {
                    // Ignore duplicate cleanup failures.
                }
            }
        } catch (error) {
            // Thumb promotion is best-effort on the client path.
        }
    }

    async function runHentai(options) {
        const audit = Boolean(options && options.audit);
        if (!picked.length) {
            if (typeof showNotification === 'function') {
                showNotification('Choose a folder on this device first', 'error');
            }
            return;
        }
        if (audit && mode !== 'write') {
            if (typeof showNotification === 'function') {
                showNotification('Audit needs Chrome or Edge so it can update the files already next to each video.', 'error');
            }
            return;
        }
        cancelled = false;
        const createNfo = document.getElementById('createNfo').checked;
        const downloadCover = document.getElementById('downloadCover').checked;
        // Hentai audit still organizes into Season 01 when the checkbox is on.
        const organizeFiles = document.getElementById('organizeFiles').checked && mode === 'write';
        const zipEntries = [];
        const start = document.getElementById('startBtn');
        const auditButton = document.getElementById('auditBtn');
        const stop = document.getElementById('stopBtn');
        if (start) {
            start.disabled = true;
        }
        if (auditButton) {
            auditButton.disabled = true;
        }
        if (stop) {
            stop.style.display = 'inline-block';
        }
        let saved = 0;
        const seenShows = {};
        for (let index = 0; index < picked.length; index += 1) {
            if (cancelled) {
                break;
            }
            const item = picked[index];
            if (audit) {
                await removeStrayAuditCopy(item);
            }
            const label = item.parentName || item.name;
            progress(Math.round((index / picked.length) * 100), 'Looking up ' + label);
            try {
                const data = await lookup(label, item.name);
                if (!data || data.library !== 'hentai') {
                    continue;
                }
                let showDir = item.parent;
                let episodeDir = item.parent;
                const originalStem = item.name.replace(/\.[^.]+$/, '');
                if (organizeFiles && rootHandle && data.show_folder && item.handle && item.handle.move && data.episode_file) {
                    const nextShow = await rootHandle.getDirectoryHandle(data.show_folder, { create: true });
                    const nextSeason = await nextShow.getDirectoryHandle('Season 01', { create: true });
                    try {
                        await item.handle.move(nextSeason, data.episode_file);
                        showDir = nextShow;
                        episodeDir = nextSeason;
                        await promoteHentaiThumb(item.parent, episodeDir, originalStem, data.episode_file);
                    } catch (error) {
                        progress(Math.round((index / picked.length) * 100), 'Left the video in place');
                    }
                }
                const showKey = (data.show_folder || item.parentName || label);
                if (!seenShows[showKey]) {
                    seenShows[showKey] = true;
                    if (downloadCover && data.cover_url) {
                        const poster = await coverBytes(data.cover_url);
                        const posters = (data.artwork && data.artwork.posters) || ['poster.jpg'];
                        if (poster && showDir) {
                            for (let nameIndex = 0; nameIndex < posters.length; nameIndex += 1) {
                                await writeBytes(showDir, posters[nameIndex], poster);
                            }
                        } else if (poster) {
                            posters.forEach((name) => {
                                zipEntries.push({ name: data.show_folder + '/' + name, data: poster });
                            });
                        }
                    }
                    if (downloadCover && data.fanart_url) {
                        const fanart = await coverBytes(data.fanart_url);
                        const backgrounds = (data.artwork && data.artwork.backgrounds) || ['background.jpg'];
                        if (fanart && showDir) {
                            for (let nameIndex = 0; nameIndex < backgrounds.length; nameIndex += 1) {
                                await writeBytes(showDir, backgrounds[nameIndex], fanart);
                            }
                        } else if (fanart) {
                            backgrounds.forEach((name) => {
                                zipEntries.push({ name: data.show_folder + '/' + name, data: fanart });
                            });
                        }
                    }
                    if (showDir && data.artwork) {
                        await pruneArtwork(showDir, data.artwork);
                    }
                    if (createNfo && data.show_nfo) {
                        const showBytes = new TextEncoder().encode(data.show_nfo);
                        if (showDir) {
                            await writeBytes(showDir, 'tvshow.nfo', showBytes);
                        } else {
                            zipEntries.push({ name: data.show_folder + '/tvshow.nfo', data: showBytes });
                        }
                    }
                }
                if (createNfo && data.episode_nfo) {
                    const episodeBase = (data.episode_file || item.name).replace(/\.[^.]+$/, '');
                    const episodeBytes = new TextEncoder().encode(data.episode_nfo);
                    if (episodeDir) {
                        await writeBytes(episodeDir, episodeBase + '.nfo', episodeBytes);
                    } else {
                        zipEntries.push({ name: data.show_folder + '/Season 01/' + episodeBase + '.nfo', data: episodeBytes });
                    }
                }
                saved += 1;
            } catch (error) {
                progress(Math.round((index / picked.length) * 100), label + ': ' + error.message);
            }
        }
        if (mode === 'download' && zipEntries.length) {
            downloadBlob(makeZip(zipEntries), 'wooscraper-metadata.zip');
        }
        progress(100, cancelled ? 'Stopped' : (audit ? 'Audited ' : 'Saved ') + saved + ' of ' + picked.length);
        if (start) {
            start.disabled = false;
        }
        if (auditButton) {
            auditButton.disabled = false;
        }
        if (stop) {
            stop.style.display = 'none';
        }
        if (typeof showNotification === 'function') {
            showNotification((audit ? 'Audited ' : 'Saved ') + saved + ' title' + (saved === 1 ? '' : 's'), 'success');
        }
    }

    async function run(options) {
        if (libraryKind() === 'hentai') {
            return runHentai(options);
        }
        const audit = Boolean(options && options.audit);
        if (!picked.length) {
            if (typeof showNotification === 'function') {
                showNotification('Choose a folder on this device first', 'error');
            }
            return;
        }
        if (audit && mode !== 'write') {
            if (typeof showNotification === 'function') {
                showNotification('Audit needs Chrome or Edge so it can update the files already next to each video.', 'error');
            }
            return;
        }
        cancelled = false;
        const createNfo = document.getElementById('createNfo').checked;
        const downloadCover = document.getElementById('downloadCover').checked;
        const trailerBox = document.getElementById('downloadTrailer');
        const downloadTrailer = trailerBox ? trailerBox.checked : true;
        const organizeFiles = !audit && document.getElementById('organizeFiles').checked && mode === 'write';
        const zipEntries = [];
        const start = document.getElementById('startBtn');
        const auditButton = document.getElementById('auditBtn');
        const stop = document.getElementById('stopBtn');
        if (start) {
            start.disabled = true;
        }
        if (auditButton) {
            auditButton.disabled = true;
        }
        if (stop) {
            stop.style.display = 'inline-block';
        }
        let saved = 0;
        for (let index = 0; index < picked.length; index += 1) {
            if (cancelled) {
                break;
            }
            const item = picked[index];
            if (audit) {
                await removeStrayAuditCopy(item);
            }
            progress(Math.round((index / picked.length) * 100), 'Looking up ' + item.javCode);
            try {
                const data = await lookup(item.name);
                if (!data.found) {
                    continue;
                }
                const folderName = item.javCode;
                const target = await directoryFor(item, data, organizeFiles);
                if (downloadCover && data.cover_url) {
                    progress(Math.round((index / picked.length) * 100), 'Saving cover for ' + item.javCode);
                    const image = await coverBytes(data.cover_url);
                    if (image) {
                        await saveArtwork(target, zipEntries, folderName, image, data.artwork, audit);
                    }
                }
                if (audit && target) {
                    await pruneArtwork(target, data.artwork);
                }
                if (downloadCover && data.artwork && data.artwork.actor_local && Array.isArray(data.portraits)) {
                    for (let portraitIndex = 0; portraitIndex < data.portraits.length; portraitIndex += 1) {
                        const portrait = data.portraits[portraitIndex];
                        if (!portrait.url || !portrait.local) {
                            continue;
                        }
                        progress(Math.round((index / picked.length) * 100), 'Saving portrait for ' + portrait.name);
                        const portraitBytes = await coverBytes(portrait.url);
                        if (!portraitBytes) {
                            continue;
                        }
                        if (audit && target) {
                            const existing = await readNested(target, portrait.local);
                            if (existing) {
                                try {
                                    const next = await pixelsOf(portraitBytes);
                                    const current = await pixelsOf(existing);
                                    if (next.pixels <= current.pixels) {
                                        progress(Math.round((index / picked.length) * 100), 'Portrait kept for ' + portrait.name);
                                        continue;
                                    }
                                } catch (error) {
                                    // A broken existing file is replaced below.
                                }
                            }
                        }
                        await storeNested(target, zipEntries, folderName, portrait.local, portraitBytes);
                    }
                }
                let nfoText = data.nfo || '';
                const segments = Array.isArray(data.trailer_segments) ? data.trailer_segments : [];
                let trailerRel = '';
                if (audit && target) {
                    trailerRel = await settleTrailers(target);
                    if (trailerRel) {
                        progress(Math.round((index / picked.length) * 100), 'Trailer for ' + item.javCode + ' is already in Trailers/');
                    }
                }
                if (!trailerRel && downloadTrailer && segments.length) {
                    const pieces = [];
                    let failed = false;
                    for (let pieceIndex = 0; pieceIndex < segments.length; pieceIndex += 1) {
                        progress(
                            Math.round((index / picked.length) * 100),
                            'Saving trailer ' + (pieceIndex + 1) + '/' + segments.length
                        );
                        const piece = await trailerBytes(segments[pieceIndex]);
                        if (!piece || !piece.length) {
                            failed = true;
                            break;
                        }
                        pieces.push(piece);
                    }
                    if (!failed && pieces.length) {
                        const size = pieces.reduce((sum, piece) => sum + piece.length, 0);
                        const joined = new Uint8Array(size);
                        let offset = 0;
                        pieces.forEach((piece) => {
                            joined.set(piece, offset);
                            offset += piece.length;
                        });
                        if (await storeTrailer(target, zipEntries, folderName, 'Preview.ts', joined)) {
                            trailerRel = 'Trailers/Preview.ts';
                        }
                    } else if (typeof showNotification === 'function') {
                        showNotification('Trailer for ' + item.javCode + ' could not be saved', 'error');
                    }
                } else if (!trailerRel && downloadTrailer && data.trailer_url) {
                    progress(Math.round((index / picked.length) * 100), 'Saving trailer for ' + item.javCode);
                    const preview = await trailerBytes(data.trailer_url, (loaded, total) => {
                        const done = Math.max(1, Math.round(loaded / 1048576));
                        const whole = Math.max(done, Math.round(total / 1048576));
                        progress(Math.round((index / picked.length) * 100), 'Saving trailer ' + done + '/' + whole + ' MB');
                    });
                    if (await storeTrailer(target, zipEntries, folderName, 'Preview.mp4', preview)) {
                        trailerRel = 'Trailers/Preview.mp4';
                    } else if (typeof showNotification === 'function') {
                        showNotification('Trailer for ' + item.javCode + ' could not be saved', 'error');
                    }
                } else if (!trailerRel && downloadTrailer) {
                    progress(Math.round((index / picked.length) * 100), 'No trailer published for ' + item.javCode);
                }
                if (trailerRel && data.trailer_url) {
                    nfoText = nfoText.split(data.trailer_url).join(trailerRel);
                }
                if (createNfo && nfoText) {
                    await storeFile(target, zipEntries, folderName, 'movie.nfo', new TextEncoder().encode(nfoText));
                }
                if (target && organizeFiles) {
                    await moveVideo(item, target);
                }
                saved += 1;
            } catch (error) {
                progress(Math.round((index / picked.length) * 100), item.javCode + ': ' + error.message);
            }
        }
        if (mode === 'download' && zipEntries.length) {
            downloadBlob(makeZip(zipEntries), 'wooscraper-metadata.zip');
        }
        progress(100, cancelled ? 'Stopped' : (audit ? 'Audited ' : 'Saved ') + saved + ' of ' + picked.length);
        if (start) {
            start.disabled = false;
        }
        if (auditButton) {
            auditButton.disabled = false;
        }
        if (stop) {
            stop.style.display = 'none';
        }
        if (typeof showNotification === 'function') {
            const where = audit
                ? 'in the current folders'
                : (mode === 'write' ? 'into the folder on this device' : 'as wooscraper-metadata.zip');
            showNotification((audit ? 'Audited ' : 'Saved ') + saved + ' title' + (saved === 1 ? '' : 's') + ' ' + where, 'success');
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const input = document.getElementById('clientFilePicker');
        if (input) {
            input.addEventListener('change', onFileInput);
        }
        // On the NAS, app.js owns the Choose folder button (server paths).
        // Elsewhere bindChooser wires the browser folder picker.
    });

    window.clientFolder = {
        isActive: function () {
            return Boolean(mode && picked.length);
        },
        clear: clearSelection,
        bindChooser: function (button) {
            if (!button) {
                return;
            }
            button.innerHTML = '<i class="fas fa-folder-open"></i> Choose folder';
            button.addEventListener('click', choose);
        },
        run: run,
        cancel: function () {
            cancelled = true;
        },
        extractJavCode: extractJavCode
    };
})();
