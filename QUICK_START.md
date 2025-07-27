# 🚀 Quick Start Guide - JAV Scraper

## ⚡ Get Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python run.py
```

### 3. Open Your Browser
Navigate to: **http://localhost:5000**

---

## 🎯 How to Use

### Step 1: Select Your Folder
1. Enter the path to your JAV video folder
2. Click "Scan Folder" to detect JAV files
3. Review the detected files in the list

### Step 2: Configure Settings
- ✅ **Create NFO files** - For Emby/Jellyfin/Kodi
- ✅ **Download covers** - High-quality poster images
- ✅ **Organize files** - Clean folder structure

### Step 3: Start Scraping
1. Click "Start Scraping"
2. Watch real-time progress
3. View results when complete

---

## 📁 Supported File Formats

**Video Files:**
- `.mp4`, `.avi`, `.mkv`, `.wmv`, `.mov`

**JAV Code Patterns:**
- `ABC-1234` (standard format)
- `ABC1234` (no dash)
- `ABC_1234` (underscore)

---

## 🎨 Features

### ✨ Modern UI
- **Dark Theme** - Easy on the eyes
- **Real-time Progress** - Live updates
- **Responsive Design** - Works on all devices
- **Beautiful Animations** - Smooth interactions

### 🔧 Smart Scraping
- **Multi-Source** - JavBus, JavLibrary, JavDB
- **Async Processing** - Fast and efficient
- **Error Handling** - Robust and reliable
- **Metadata Export** - JSON and NFO files

### 📊 Output Structure
```
📁 JAV_CODE/
├── 📄 JAV_CODE.nfo          # Media server metadata
├── 🖼️ JAV_CODE-poster.jpg   # Cover image
├── 📄 JAV_CODE-metadata.json # Complete data
└── 🎬 Original video file
```

---

## 🛠️ Troubleshooting

### Common Issues:

**❌ "No files detected"**
- Check file naming: `ABC-1234.mp4`
- Verify supported extensions
- Ensure folder path is correct

**❌ "Scraping fails"**
- Click "Test Connection" button
- Check internet connection
- Review `scraper.log` for details

**❌ "Slow performance"**
- Reduce threads in `config.yml`
- Close other applications
- Check network speed

---

## 🔧 Configuration

Edit `config.yml` to customize:

```yaml
scraper:
  max_threads: 5          # Number of parallel requests
  timeout: 30             # Request timeout (seconds)
  create_nfo: true        # Generate NFO files
  download_cover: true    # Download poster images
```

---

## 📝 Examples

### File Naming Examples:
```
✅ ABC-1234.mp4
✅ DEF-567.avi  
✅ GHI-890.mkv
❌ movie.mp4 (no JAV code)
❌ ABC123.mp4 (too short)
```

### Folder Structure:
```
📁 Your Videos/
├── 📁 ABC-1234/
│   ├── 📄 ABC-1234.nfo
│   ├── 🖼️ ABC-1234-poster.jpg
│   ├── 📄 ABC-1234-metadata.json
│   └── 🎬 ABC-1234.mp4
└── 📁 DEF-567/
    ├── 📄 DEF-567.nfo
    ├── 🖼️ DEF-567-poster.jpg
    ├── 📄 DEF-567-metadata.json
    └── 🎬 DEF-567.avi
```

---

## 🎉 Success!

Your JAV scraper is now ready to organize your media collection with professional metadata!

**Need help?** Check the full README.md for detailed documentation.

---

## ⚠️ Legal Notice

This tool is for **educational and personal use only**:
- ✅ Learning Python and web scraping
- ✅ Personal media organization
- ❌ Commercial use prohibited
- ❌ Public distribution not allowed

Users must comply with local laws and website terms of service. 