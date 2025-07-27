# 🔧 Troubleshooting Guide - JAV Scraper

## 🚨 Common Issues and Solutions

### ❌ "Invalid folder path" Error

**Problem**: You're getting a 400 error when trying to scan a folder.

**Solutions**:

1. **Test your folder path first**:
   ```bash
   python test_folder.py "/path/to/your/videos"
   ```

2. **Use absolute paths**:
   - ❌ `videos` (relative path)
   - ✅ `/home/user/videos` (absolute path)
   - ✅ `/mnt/drive/videos` (absolute path)

3. **Check folder permissions**:
   ```bash
   ls -la /path/to/your/videos
   ```

4. **Common path issues**:
   - **Windows paths**: Use forward slashes or escape backslashes
     - ✅ `C:/Users/Name/Videos`
     - ✅ `C:\\Users\\Name\\Videos`
   - **Spaces in paths**: Use quotes
     - ✅ `"/home/user/My Videos"`
   - **Special characters**: Avoid if possible

### ❌ "No JAV files found" Error

**Problem**: Folder scans but finds no JAV files.

**Solutions**:

1. **Check file naming**:
   - ✅ `ABC-1234.mp4`
   - ✅ `DEF-567.avi`
   - ✅ `GHI-890.mkv`
   - ❌ `movie.mp4` (no JAV code)
   - ❌ `ABC123.mp4` (too short)

2. **Supported file extensions**:
   - `.mp4`, `.avi`, `.mkv`, `.wmv`, `.mov`

3. **Test with sample files**:
   ```bash
   # Create test files
   mkdir test_videos
   cd test_videos
   touch "ABC-1234.mp4" "DEF-567.avi" "GHI-890.mkv"
   
   # Test the scraper
   python test_folder.py test_videos
   ```

### ❌ "Scraping fails" Error

**Problem**: Files are found but scraping doesn't work.

**Solutions**:

1. **Test connection**:
   - Click "Test Connection" button in the UI
   - Check internet connection
   - Try different network if possible

2. **Check logs**:
   ```bash
   tail -f scraper.log
   ```

3. **Reduce threads**:
   Edit `config.yml`:
   ```yaml
   scraper:
     max_threads: 2  # Reduce from 5 to 2
   ```

### ❌ "Application won't start" Error

**Problem**: Can't start the Flask application.

**Solutions**:

1. **Check dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Check port availability**:
   ```bash
   # Check if port 5000 is in use
   lsof -i :5000
   
   # Kill process if needed
   pkill -f "python.*app.py"
   ```

3. **Use different port**:
   Edit `app.py`:
   ```python
   app.run(debug=True, host='0.0.0.0', port=5001)
   ```

### ❌ "Permission denied" Error

**Problem**: Can't access folders or create files.

**Solutions**:

1. **Check folder permissions**:
   ```bash
   ls -la /path/to/folder
   ```

2. **Fix permissions**:
   ```bash
   chmod 755 /path/to/folder
   ```

3. **Run with proper user**:
   ```bash
   # Don't run as root unless necessary
   sudo -u your_username python run.py
   ```

## 🔍 Debugging Steps

### Step 1: Test Folder Path
```bash
python test_folder.py "/your/folder/path"
```

### Step 2: Check Application Logs
```bash
tail -f scraper.log
```

### Step 3: Test Individual Components
```bash
python test_scraper.py
```

### Step 4: Manual API Testing
```bash
# Test scan folder API
curl -X POST http://localhost:5000/api/scan-folder \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "/path/to/your/videos"}'
```

## 📋 Common Folder Path Examples

### Linux/Mac:
```bash
# Home directory
/home/username/Videos

# External drive
/mnt/external/videos

# Current directory
./videos
```

### Windows:
```bash
# C drive
C:/Users/Username/Videos

# D drive
D:/Videos

# Network drive
//server/share/videos
```

## 🎯 Quick Fixes

### 1. Reset Everything
```bash
# Stop the application
pkill -f "python.*app.py"

# Clear logs
rm -f scraper.log

# Restart
python run.py
```

### 2. Test with Sample Data
```bash
# Create test folder
mkdir -p test_videos
cd test_videos
touch "ABC-1234.mp4" "DEF-567.avi"

# Test
python test_folder.py test_videos
```

### 3. Check Configuration
```bash
# Verify config file
cat config.yml

# Test configuration loading
python -c "import yaml; print(yaml.safe_load(open('config.yml')))"
```

## 📞 Getting Help

If you're still having issues:

1. **Check the logs**: `tail -f scraper.log`
2. **Test your folder**: `python test_folder.py /your/path`
3. **Run the test suite**: `python test_scraper.py`
4. **Check the README**: `cat README.md`

## 🎉 Success Indicators

You'll know everything is working when:

- ✅ `python test_folder.py /your/path` shows "✅ Folder path is valid"
- ✅ `python test_scraper.py` shows "🎉 All tests passed"
- ✅ Web interface loads at `http://localhost:5000`
- ✅ "Test Connection" button works
- ✅ Folder scanning finds your JAV files
- ✅ Scraping completes successfully

---

**Remember**: The most common issue is incorrect folder paths. Always test your path first with `python test_folder.py /your/path`! 