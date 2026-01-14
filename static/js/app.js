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
});



/**
 * Opens the folder browser dialog
 * @description Triggers the hidden file input to select a folder
 * @returns {void}
 */
function browseFolder() {
    // For web browsers, we'll use a simple input
    // In a real desktop app, you'd use a native file dialog
    const folderInput = document.getElementById('folderInput');
    folderInput.click();
}

// Show path helper
async function showPathHelper() {
    try {
        const response = await fetch('/api/common-paths');
        const data = await response.json();
        
        if (data.success && data.paths.length > 0) {
            let pathList = 'Found video folders:\n\n';
            data.paths.forEach(item => {
                pathList += `• ${item.path} (${item.video_count} videos)\n`;
            });
            
            pathList += '\n💡 Tip: Use the full path to the folder containing video files';
            
            alert(pathList);
        } else {
            alert('No video folders found automatically.\n\nTry these common paths:\n• test_videos\n• /home/joe/Videos');
        }
    } catch (error) {
        alert('Error finding paths. Try:\n• test_videos');
    }
}

// Quick path helper function removed - no more popup

// Handle folder selection
function selectFolder() {
    const folderInput = document.getElementById('folderInput');
    if (folderInput.files.length > 0) {
        // Get the folder name from the file object
        const file = folderInput.files[0];
        let folderName = '';
        
        // Extract folder name from the relative path
        if (file.webkitRelativePath) {
            const pathParts = file.webkitRelativePath.split('/');
            if (pathParts.length > 1) {
                folderName = pathParts[0];
            }
        }
        
        // Close the modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('folderModal'));
        modal.hide();
        
        // Show a dialog to get the full absolute path
        const fullPath = prompt(
            `You selected folder: "${folderName}"\n\nPlease enter the full absolute path to this folder:\n\nExample: /home/joe/media/Others/JAV/${folderName}`,
            `/home/joe/media/Others/JAV/${folderName}`
        );
        
        if (fullPath && fullPath.trim()) {
            document.getElementById('folderPath').value = fullPath.trim();
            currentFolder = fullPath.trim();
            showNotification('Folder path set: ' + fullPath.trim(), 'success');
        } else {
            showNotification('No path entered. Please enter the path manually.', 'warning');
        }
    }
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
            body: JSON.stringify({ folder_path: folderPath })
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

            // Enable start button
            document.getElementById('startBtn').disabled = false;
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
                No JAV files found in the selected folder
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
async function startScraping() {
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
        const organizeFiles = document.getElementById('organizeFiles').checked;

        addDebugLog(`⚙️ UI Settings:`, 'info');
        addDebugLog(`   - Create NFO: ${createNfo}`, 'info');
        addDebugLog(`   - Download Cover: ${downloadCover}`, 'info');
        addDebugLog(`   - Organize Files: ${organizeFiles}`, 'info');

        const response = await fetch('/api/start-scraping', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                folder_path: folderPath,
                create_nfo: createNfo,
                download_cover: downloadCover,
                organize_files: organizeFiles
            })
        });

        const data = await response.json();

        if (data.success) {
            addDebugLog(`✅ Scraping job started successfully`, 'success');
            showNotification('Scraping started successfully', 'success');
            document.getElementById('startBtn').style.display = 'none';
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
                No JAV files found in the selected folder
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
    }
}

// Show notification toast
function showNotification(message, type = 'info') {
    const toast = document.getElementById('notificationToast');
    const toastMessage = document.getElementById('toastMessage');
    
    // Set message and type
    toastMessage.textContent = message;
    toast.className = `toast ${type === 'error' ? 'bg-danger' : type === 'success' ? 'bg-success' : 'bg-info'}`;
    
    // Show toast
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
}

// Debug logging functions
function addDebugLog(message, type = 'info') {
    const debugLog = document.getElementById('debugLog');
    if (!debugLog) return;
    
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    logEntry.innerHTML = `<span class="timestamp">[${timestamp}]</span> ${message}`;
    
    debugLog.appendChild(logEntry);
    debugLog.scrollTop = debugLog.scrollHeight;
}

function showDebugSection(show = true) {
    const debugSection = document.getElementById('debugSection');
    if (debugSection) {
        debugSection.style.display = show ? 'block' : 'none';
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
        'test_videos',
        '/home/joe/media/Others/JAV',
        '/home/joe/Videos',
        '/home/joe/Downloads'
    ];
    
    // Add placeholder with suggestions
    folderPathInput.placeholder = 'Enter folder path (e.g., test_videos, /home/joe/media/Others/JAV/...)';
    
    // Add a small help text below the input
    const helpText = document.createElement('small');
    helpText.className = 'text-muted mt-1 d-block';
            helpText.innerHTML = '💡 Tip: Use absolute paths like <code>/home/user/videos</code>';
    folderPathInput.parentNode.appendChild(helpText);
}

// Initialize path suggestions when page loads
document.addEventListener('DOMContentLoaded', function() {
    addPathSuggestions();
});

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