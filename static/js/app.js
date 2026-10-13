/**
 * JAV Scraper Frontend JavaScript
 * @description Main JavaScript file for the JAV metadata scraper web interface
 * @author JAV Scraper Team
 * @version 1.0
 */

// Global variables for the application
let currentFolder = localStorage.getItem('lastFolderPath') || '';
let scannedFiles = [];
let jobStatusInterval = null;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    console.log('JAV Scraper initialized');

    // Load saved folder path
    if (currentFolder) {
        document.getElementById('folderPath').value = currentFolder;
    }

    updateStatus('Ready to scan');

    // Initialize path suggestions
    addPathSuggestions();
    setupFolderButton();

    // Initialize theme from localStorage
    try {
        const savedTheme = localStorage.getItem('theme');
        const themeToggle = document.getElementById('themeToggle');

        if (themeToggle) {
            if (savedTheme === 'light') {
                document.body.classList.add('light-theme');
                themeToggle.checked = true;
            } else {
                document.body.classList.remove('light-theme');
                themeToggle.checked = false;
            }
        }
    } catch (error) {
        console.warn('Failed to initialize theme:', error.message);
    }
});

let browsePath = '';
let serverHasLibrary = false;

async function setupFolderButton() {
    const button = document.getElementById('chooseFolderBtn');
    const help = document.getElementById('folderHelp');
    const useBtn = document.getElementById('browseUseFolderBtn');
    if (useBtn) {
        useBtn.addEventListener('click', useBrowseFolder);
    }
    try {
        const response = await fetch('/api/capabilities');
        const data = await response.json();
        serverHasLibrary = Boolean(data.local_files);
        if (data.library_root && !document.getElementById('folderPath').value) {
            document.getElementById('folderPath').placeholder = data.library_root;
        }
    } catch (error) {
        serverHasLibrary = false;
    }
    if (!button) {
        return;
    }
    const goBtn = document.getElementById('browseGoBtn');
    const pathInput = document.getElementById('browsePathInput');
    if (goBtn) {
        goBtn.addEventListener('click', () => {
            const typed = (pathInput && pathInput.value || '').trim();
            loadBrowsePath(typed);
        });
    }
    if (pathInput) {
        pathInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                loadBrowsePath((pathInput.value || '').trim());
            }
        });
    }
    if (serverHasLibrary) {
        // QNAP / local server: pick a folder the server can write into.
        button.innerHTML = '<i class="fas fa-folder-open"></i> Choose folder';
        if (help) {
            help.textContent = 'Type any server path above, or browse. Scan and Start write into that folder — nothing is uploaded.';
        }
        button.addEventListener('click', openServerFolderBrowser);
    } else if (window.clientFolder && typeof window.clientFolder.bindChooser === 'function') {
        // Hosted / no server disk: browser picks a folder on this PC.
        window.clientFolder.bindChooser(button);
        if (help) {
            help.textContent = 'Choose a folder on this computer. Chrome or Edge can write into it; otherwise you get a zip download.';
        }
    }
}

async function openServerFolderBrowser() {
    const start = (document.getElementById('folderPath').value || '').trim();
    const pathInput = document.getElementById('browsePathInput');
    if (pathInput) {
        pathInput.value = start;
    }
    await loadBrowsePath(start);
    bootstrap.Modal.getOrCreateInstance(document.getElementById('folderModal')).show();
}

async function loadBrowsePath(path) {
    const list = document.getElementById('browseFolderList');
    const pathInput = document.getElementById('browsePathInput');
    if (list) {
        list.innerHTML = '<div class="list-group-item bg-dark text-muted">Loading…</div>';
    }
    const query = path ? ('?path=' + encodeURIComponent(path)) : '';
    const response = await fetch('/api/browse' + query);
    const data = await response.json();
    if (!response.ok) {
        if (list) {
            list.innerHTML = '<div class="list-group-item bg-dark text-danger">' +
                (data.error || 'Could not open folder') + '</div>';
        }
        return;
    }
    browsePath = data.path || '';
    if (pathInput) {
        pathInput.value = browsePath;
    }
    if (!list) {
        return;
    }
    list.innerHTML = '';
    if (data.parent) {
        const up = document.createElement('button');
        up.type = 'button';
        up.className = 'list-group-item list-group-item-action bg-dark text-light';
        up.innerHTML = '<i class="fas fa-level-up-alt me-2"></i>..';
        up.addEventListener('click', () => loadBrowsePath(data.parent));
        list.appendChild(up);
    }
    (data.entries || []).forEach((entry) => {
        const row = document.createElement('button');
        row.type = 'button';
        row.className = 'list-group-item list-group-item-action bg-dark text-light';
        row.innerHTML = '<i class="fas fa-folder me-2 text-warning"></i>' + entry.name;
        row.addEventListener('click', () => loadBrowsePath(entry.path));
        list.appendChild(row);
    });
    if (!(data.entries || []).length) {
        const empty = document.createElement('div');
        empty.className = 'list-group-item bg-dark text-muted';
        empty.textContent = 'No subfolders — you can use this folder.';
        list.appendChild(empty);
    }
}

function useBrowseFolder() {
    if (!browsePath) {
        showNotification('No folder selected', 'warning');
        return;
    }
    if (window.clientFolder && typeof window.clientFolder.clear === 'function') {
        window.clientFolder.clear();
    }
    document.getElementById('folderPath').value = browsePath;
    currentFolder = browsePath;
    localStorage.setItem('lastFolderPath', browsePath);
    const modal = bootstrap.Modal.getInstance(document.getElementById('folderModal'));
    if (modal) {
        modal.hide();
    }
    showNotification('Folder set: ' + browsePath + '. Click Scan Folder, then Start Scraping.', 'success');
}

// Convert relative path to absolute path
function convertToAbsolutePath(path) {
    // If it's already an absolute path, return as is
    if (path.startsWith('/')) {
        return path;
    }
    
    // If it's a relative path, try to resolve it
    // For now, we'll use the current working directory
    // In a real implementation, you might want to use a file dialog
    if (path === '.' || path === './') {
        return process.cwd ? process.cwd() : '/';
    }
    
    // For relative paths, we'll try to resolve them
    // This is a simplified approach - in a real app you'd use a proper file dialog
    return path;
}

/**
 * Scans a folder for JAV files and displays the results
 * @description Sends a request to the backend API to scan a folder for JAV video files
 * @param {string} folderPath - The path of the folder to scan
 * @returns {Promise<void>}
 */
async function scanFolder() {
    if (window.clientFolder && clientFolder.isActive()) {
        showNotification('That folder is on this device. Press Start Scraping to save into it.', 'info');
        return;
    }
    const folderPath = document.getElementById('folderPath').value.trim();

    if (!folderPath) {
        showNotification('Please enter a folder path', 'error');
        return;
    }

    // Save folder path to localStorage
    localStorage.setItem('lastFolderPath', folderPath);
    currentFolder = folderPath;

    updateStatus('Scanning folder...');
    showLoading(true);
    clearDebugLog();
    showDebugSection(true);
    addDebugLog(`🔍 Starting folder scan: ${folderPath}`, 'info');

    try {
        const response = await fetch('/api/scan-folder', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                folder_path: folderPath,
                library: (document.getElementById('libraryKind') || {}).value || 'jav'
            })
        });

        const data = await response.json();

        if (data.success) {
            scannedFiles = data.files;
            currentFolder = data.resolved_path || folderPath;

            // Update the input with the resolved path
            document.getElementById('folderPath').value = currentFolder;

            addDebugLog(`✅ Found ${data.count} JAV files`, 'success');
            addDebugLog(`📁 Resolved path: ${currentFolder}`, 'info');

            displayFiles(data.files);
            showNotification(`Found ${data.count} JAV files`, 'success');
            updateStatus(`Found ${data.count} JAV files in ${currentFolder}`);

            document.getElementById('startBtn').disabled = false;
            const auditButton = document.getElementById('auditBtn');
            if (auditButton) {
                auditButton.disabled = false;
            }
        } else {
            const errorMsg = data.error || 'Failed to scan folder';
            addDebugLog(`❌ Scan failed: ${errorMsg}`, 'error');
            showNotification(errorMsg, 'error');
            updateStatus('Scan failed');
        }
    } catch (error) {
        addDebugLog(`❌ Error scanning folder: ${error.message}`, 'error');
        showNotification('Error scanning folder: ' + error.message, 'error');
        updateStatus('Scan failed');
    } finally {
        showLoading(false);
    }
}

// Display scanned files
function displayFiles(files) {
    const fileList = document.getElementById('fileList');
    
    if (files.length === 0) {
        fileList.innerHTML = `
            <p class="text-muted text-center py-4">
                <i class="fas fa-exclamation-triangle fa-3x mb-3"></i><br>
                No videos found in the selected folder
            </p>
        `;
        return;
    }
    
    let html = '<div class="row">';
    
    files.forEach((file, index) => {
        const fileExtension = file.filename.split('.').pop().toLowerCase();
        const fileIcon = getFileIcon(fileExtension);
        
        html += `
            <div class="col-md-6 col-lg-4 mb-3">
                <div class="file-item" data-jav-code="${file.jav_code}">
                    <div class="d-flex align-items-start">
                        <i class="fas ${fileIcon} file-icon"></i>
                        <div class="flex-grow-1">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div class="flex-grow-1">
                                    <strong>${file.jav_code}</strong>
                                    <br>
                                    <small class="text-muted">${file.filename}</small>
                                </div>
                                <span class="jav-code">${file.jav_code}</span>
                            </div>
                            <div>
                                <small class="text-muted">${file.file_path}</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    fileList.innerHTML = html;
}

// Get file icon based on extension
function getFileIcon(extension) {
    const iconMap = {
        'mp4': 'fa-file-video',
        'avi': 'fa-file-video',
        'mkv': 'fa-file-video',
        'wmv': 'fa-file-video',
        'mov': 'fa-file-video',
        'flv': 'fa-file-video'
    };
    
    return iconMap[extension] || 'fa-file';
}

/**
 * Starts the scraping process for JAV files
 * @description Sends a request to the backend API to start scraping metadata for JAV files in the selected folder
 * @param {string} folderPath - The path of the folder containing JAV files
 * @returns {Promise<void>}
 */
async function auditLibrary() {
    return startScraping(true);
}

async function startScraping(audit) {
    const auditing = audit === true;
    if (window.clientFolder && clientFolder.isActive()) {
        return clientFolder.run(auditing ? { audit: true } : undefined);
    }
    const folderPath = document.getElementById('folderPath').value.trim();

    if (!folderPath) {
        showNotification('Please select a folder first', 'error');
        return;
    }

    addDebugLog(`🚀 Starting scraping process for: ${folderPath}`, 'info');
    addDebugLog(`📁 Files to process: ${scannedFiles.length}`, 'info');

    try {
        // Get UI settings
        const createNfo = document.getElementById('createNfo').checked;
        const downloadCover = document.getElementById('downloadCover').checked;
        const downloadTrailer = document.getElementById('downloadTrailer').checked;
        const library = (document.getElementById('libraryKind') || {}).value || 'jav';
        // Hentai audit still organizes into Season 01; JAV audit stays artwork-only.
        const organizeFiles = (auditing && library !== 'hentai')
            ? false
            : document.getElementById('organizeFiles').checked;
        const skipComplete = document.getElementById('skipComplete')
            ? document.getElementById('skipComplete').checked
            : false;

        addDebugLog(`⚙️ UI Settings:`, 'info');
        addDebugLog(`   - Create NFO: ${createNfo}`, 'info');
        addDebugLog(`   - Download Cover: ${downloadCover}`, 'info');
        addDebugLog(`   - Organize Files: ${organizeFiles}`, 'info');
        addDebugLog(`   - Audit: ${auditing}`, 'info');

        const response = await fetch('/api/start-scraping', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                folder_path: folderPath,
                create_nfo: createNfo,
                download_cover: downloadCover,
                download_trailer: downloadTrailer,
                organize_files: organizeFiles,
                audit: auditing,
                skip_complete: skipComplete,
                media_server: (document.getElementById('mediaServer') || {}).value || 'plex',
                library: library
            })
        });

        const data = await response.json();

        if (data.success) {
            addDebugLog(`✅ Scraping job started successfully`, 'success');
            showNotification('Scraping started successfully', 'success');
            document.getElementById('startBtn').style.display = 'none';
            const auditButton = document.getElementById('auditBtn');
            if (auditButton) {
                auditButton.style.display = 'none';
            }
            document.getElementById('stopBtn').style.display = 'inline-block';
            document.getElementById('progressSection').style.display = 'block';

            // Start monitoring job status
            startJobStatusMonitoring();
        } else {
            addDebugLog(`❌ Failed to start scraping: ${data.error}`, 'error');
            showNotification(data.error || 'Failed to start scraping', 'error');
        }
    } catch (error) {
        addDebugLog(`❌ Error starting scraping: ${error.message}`, 'error');
        showNotification('Error starting scraping: ' + error.message, 'error');
    }
}

// Stop scraping process
async function stopScraping() {
    if (window.clientFolder) {
        clientFolder.cancel();
    }
    try {
        const response = await fetch('/api/stop-scraping', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Scraping stopped', 'warning');
            stopJobStatusMonitoring();
            resetUI();
        }
    } catch (error) {
        console.error('Error stopping scraping:', error);
        showNotification('Error stopping scraping: ' + error.message, 'error');
    }
}

// Start monitoring job status
function startJobStatusMonitoring() {
    if (jobStatusInterval) {
        clearInterval(jobStatusInterval);
    }
    
    jobStatusInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/job-status');
            const status = await response.json();
            
            updateProgress(status);
            
            // Add debug logging for job status
            if (status.current_file) {
                addDebugLog(`🔄 Processing: ${status.current_file}`, 'info');
            }
            if (status.progress) {
                addDebugLog(`📊 Progress: ${status.progress}%`, 'info');
            }
            if (status.message) {
                addDebugLog(`💬 ${status.message}`, 'info');
            }
            
            if (!status.running) {
                stopJobStatusMonitoring();
                if (status.error) {
                    addDebugLog(`❌ Scraping failed: ${status.error}`, 'error');
                    showNotification('Scraping failed: ' + status.error, 'error');
                } else {
                    addDebugLog(`✅ Scraping completed successfully`, 'success');
                    addDebugLog(`📁 Results: ${status.results ? status.results.length : 0} files processed`, 'success');
                    showNotification('Scraping completed successfully', 'success');
                    displayResults(status.results);
                }
                resetUI();
            }
        } catch (error) {
            addDebugLog(`❌ Error fetching job status: ${error.message}`, 'error');
        }
    }, 1000);
}

// Stop monitoring job status
function stopJobStatusMonitoring() {
    if (jobStatusInterval) {
        clearInterval(jobStatusInterval);
        jobStatusInterval = null;
    }
}

// Update progress bar and status
function updateProgress(status) {
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');

    if (status.total_files > 0) {
        const progress = Math.round((status.processed_files / status.total_files) * 100);
        progressBar.style.width = progress + '%';
        progressBar.textContent = progress + '%';

        progressText.textContent = `${status.current_file} (${status.processed_files}/${status.total_files})`;
    }

    updateStatus(status.current_file || 'Processing...');
}

// Efficient file listing display for large folders
function displayFilesEfficiently(files) {
    const fileList = document.getElementById('fileList');

    if (files.length === 0) {
        fileList.innerHTML = `
            <p class="text-muted text-center py-4">
                <i class="fas fa-exclamation-triangle fa-3x mb-3"></i><br>
                No videos found in the selected folder
            </p>
        `;
        return;
    }

    // For large lists, use virtual scrolling or pagination to improve performance
    if (files.length > 50) {
        fileList.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i> Large folder detected (${files.length} files).
                Showing first 50 files for performance reasons.
            </div>
        `;

        // Display only first 50 files
        const displayFiles = files.slice(0, 50);
        renderFileList(displayFiles);
    } else {
        renderFileList(files);
    }
}

// Helper function to render file list
function renderFileList(files) {
    const fileList = document.getElementById('fileList');

    let html = '<div class="row">';

    files.forEach((file, index) => {
        const fileExtension = file.filename.split('.').pop().toLowerCase();
        const fileIcon = getFileIcon(fileExtension);

        html += `
            <div class="col-md-6 col-lg-4 mb-3">
                <div class="file-item" data-jav-code="${file.jav_code}">
                    <div class="d-flex align-items-start">
                        <i class="fas ${fileIcon} file-icon"></i>
                        <div class="flex-grow-1">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <div class="flex-grow-1">
                                    <strong>${file.jav_code}</strong>
                                    <br>
                                    <small class="text-muted">${file.filename}</small>
                                </div>
                                <span class="jav-code">${file.jav_code}</span>
                            </div>
                            <div>
                                <small class="text-muted">${file.file_path}</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    html += '</div>';
    fileList.innerHTML = html;
}

// Display results
function displayResults(results) {
    const resultsSection = document.getElementById('resultsSection');
    const resultsList = document.getElementById('resultsList');

    if (!results || results.length === 0) {
        resultsList.innerHTML = '<p class="text-muted text-center">No results to display</p>';
        resultsSection.style.display = 'block';
        return;
    }

    // For large result sets, show only the first 50 items for performance
    const displayResults = results.length > 50 ? results.slice(0, 50) : results;

    let html = '<div class="row">';

    displayResults.forEach((result, index) => {
        const statusClass = result.error ? 'error' : 'success';
        const statusText = result.error ? 'Error' : 'Success';
        const statusIcon = result.error ? 'fa-exclamation-triangle' : 'fa-check-circle';

        html += `
            <div class="col-md-6 col-lg-4 mb-3">
                <div class="result-item ${statusClass}">
                    <div class="d-flex justify-content-between align-items-start mb-2">
                        <strong class="title">${result.jav_code}</strong>
                        <span class="status-badge status-${statusClass}">
                            <i class="fas ${statusIcon}"></i> ${statusText}
                        </span>
                    </div>
                    ${result.best_title ? `<div class="metadata">Title: ${result.best_title}</div>` : ''}
                    ${result.error ? `<div class="metadata text-danger">Error: ${result.error}</div>` : ''}
                    <div class="metadata">File: ${result.filename}</div>
                    ${result.best_cover ? '<div class="metadata">Cover downloaded</div>' : ''}
                </div>
            </div>
        `;
    });

    // Add a notice if results were truncated
    if (results.length > 50) {
        html += `
            <div class="col-12">
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                    Showing first 50 of ${results.length} results for performance reasons.
                </div>
            </div>
        `;
    }

    html += '</div>';
    resultsList.innerHTML = html;
    resultsSection.style.display = 'block';
}

// Test connection to scraping sites
async function testConnection() {
    try {
        updateStatus('Testing connection...');
        showLoading(true);
        
        const response = await fetch('/api/test-connection');
        const data = await response.json();
        
        if (data.success) {
            showNotification('Connection test successful', 'success');
            updateStatus('Connection test passed');
        } else {
            showNotification('Connection test failed: ' + data.error, 'error');
            updateStatus('Connection test failed');
        }
    } catch (error) {
        console.error('Error testing connection:', error);
        showNotification('Error testing connection: ' + error.message, 'error');
        updateStatus('Connection test failed');
    } finally {
        showLoading(false);
    }
}

// Reset UI to initial state
function resetUI() {
    document.getElementById('startBtn').style.display = 'inline-block';
    const auditButton = document.getElementById('auditBtn');
    if (auditButton) {
        auditButton.style.display = 'inline-block';
    }
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('progressSection').style.display = 'none';
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressBar').textContent = '0%';
    document.getElementById('progressText').textContent = 'Ready to start...';
}

// Update status display
function updateStatus(message) {
    const statusInfo = document.getElementById('statusInfo');
    statusInfo.innerHTML = `<p class="text-muted">${message}</p>`;
}

// Show loading state
function showLoading(show) {
    const buttons = document.querySelectorAll('button');
    buttons.forEach(button => {
        if (show) {
            button.disabled = true;
        } else {
            button.disabled = false;
        }
    });
    
    // Re-enable start button if files are scanned
    if (!show && scannedFiles.length > 0) {
        document.getElementById('startBtn').disabled = false;
        const auditButton = document.getElementById('auditBtn');
        if (auditButton) {
            auditButton.disabled = false;
        }
    }
}


// Show notification toast
function showNotification(message, type = 'info') {
    try {
        const toast = document.getElementById('notificationToast');
        const toastMessage = document.getElementById('toastMessage');
        
        if (!toast || !toastMessage) {
            console.warn('Notification elements not found:', message);
            return;
        }
        
        // Set message and type
        toastMessage.textContent = message;
        toast.className = `toast ${type === 'error' ? 'bg-danger' : type === 'success' ? 'bg-success' : 'bg-info'}`;
        
        // Show toast
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    } catch (error) {
        console.warn('Failed to show notification:', error.message);
    }
}
// Debug logging functions
function addDebugLog(message, type = 'info') {
    try {
        const debugLog = document.getElementById('debugLog');
        if (!debugLog) return;
        
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry log-${type}`;
        logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
        
        debugLog.appendChild(logEntry);
        debugLog.scrollTop = debugLog.scrollHeight;
        
        // Apply theme to the new entry if needed
        const isLightTheme = document.body.classList.contains('light-theme');
        if (isLightTheme) {
            logEntry.classList.add('light-theme');
        }
    } catch (error) {
        console.warn('Failed to add debug log entry:', error.message);
    }
}

function showDebugSection(show = true) {
    const debugSection = document.getElementById('debugSection');
    if (debugSection) {
        debugSection.style.display = show ? 'block' : 'none';
        if (show) {
            updateDebugTheme();
        }
    }
}

// Update theme when debug section visibility changes
function updateDebugTheme() {
    try {
        const debugSection = document.getElementById('debugSection');
        if (debugSection) {
            const isLightTheme = document.body.classList.contains('light-theme');
            const debugLog = document.getElementById('debugLog');
            
            if (debugLog && debugSection.style.display !== 'none') {
                // Apply theme to debug log when it's visible
                if (isLightTheme) {
                    debugLog.classList.add('light-theme');
                } else {
                    debugLog.classList.remove('light-theme');
                }
            }
        }
    } catch (error) {
        console.warn('Failed to update debug theme:', error.message);
    }
}

function clearDebugLog() {
    const debugLog = document.getElementById('debugLog');
    if (debugLog) {
        debugLog.innerHTML = '';
    }
}

// Handle folder input change
document.getElementById('folderInput').addEventListener('change', function() {
    if (this.files.length > 0) {
        const filePath = this.files[0].webkitRelativePath;
        const folderPath = filePath.split('/')[0];
        document.getElementById('folderPath').value = folderPath;
        currentFolder = folderPath;
    }
});

// Add common path suggestions
function addPathSuggestions() {
    const folderPathInput = document.getElementById('folderPath');
    const suggestions = [
        '/library',
        'test_videos',
        '/home/joe/media/Others/JAV',
        '/home/joe/Videos',
        '/home/joe/Downloads'
    ];

    folderPathInput.placeholder = 'Any folder path the server can read, e.g. /library/hentai';
}

// Handle Enter key in folder path input
document.getElementById('folderPath').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
        scanFolder();
    }
});

// Right-click context menu removed - no more popup

// High contrast mode toggle
document.getElementById('highContrast').addEventListener('change', function() {
    const body = document.body;
    if (this.checked) {
        body.classList.add('high-contrast');
        showNotification('High contrast mode enabled', 'info');
    } else {
        body.classList.remove('high-contrast');
        showNotification('High contrast mode disabled', 'info');
    }
});

// Theme toggle
const themeToggle = document.getElementById('themeToggle');
if (themeToggle) {
    themeToggle.addEventListener('change', function() {
        const body = document.body;
        if (this.checked) {
            body.classList.add('light-theme');
            showNotification('Light theme enabled', 'info');
            localStorage.setItem('theme', 'light');
        } else {
            body.classList.remove('light-theme');
            showNotification('Dark theme enabled', 'info');
            localStorage.setItem('theme', 'dark');
        }
    });
}