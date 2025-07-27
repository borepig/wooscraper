# JAV Scraper - Professional Metadata Tool

A modern web-based JAV metadata scraper with a beautiful UI, inspired by the [JavSP project](https://github.com/Yuukiy/JavSP). This tool automatically extracts JAV codes from filenames and scrapes metadata from multiple sources.

## Features

### 🎯 Core Features
- **Smart JAV Code Detection**: Automatically extracts JAV codes (XXXX-NNNN format) from filenames
- **Multi-Source Scraping**: Scrapes metadata from JavBus, JavLibrary, and JavDB
- **Modern Web UI**: Beautiful, responsive interface with real-time progress tracking
- **NFO Generation**: Creates NFO files compatible with Emby, Jellyfin, and Kodi
- **Cover Download**: Automatically downloads high-quality cover images
- **Metadata Export**: Saves comprehensive metadata in JSON format

### 🎨 UI Features
- **Dark Theme**: Modern dark interface with smooth animations
- **Real-time Progress**: Live progress bar and status updates
- **File Preview**: Visual preview of detected JAV files
- **Results Display**: Detailed results with success/error status
- **Responsive Design**: Works on desktop and mobile devices

### 🔧 Technical Features
- **Async Processing**: Multi-threaded scraping for fast performance
- **Error Handling**: Robust error handling with detailed logging
- **Configurable**: YAML-based configuration system
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Quick Start

1. **Clone or download the project**
   ```bash
   git clone <repository-url>
   cd wooscraper
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

4. **Open your browser**
   Navigate to `http://localhost:5000`

## Usage

### Step 1: Select a Folder
1. Enter the path to your JAV video folder in the input field
2. Click "Scan Folder" to detect JAV files
3. Review the detected files in the list

### Step 2: Configure Settings
- **Create NFO files**: Generate NFO files for media servers
- **Download covers**: Download cover images for each title
- **Organize files**: Create organized folder structure

### Step 3: Start Scraping
1. Click "Start Scraping" to begin the process
2. Monitor progress in real-time
3. View results when complete

### Supported File Formats
- Video: `.mp4`, `.avi`, `.mkv`, `.wmv`, `.mov`
- JAV Code Patterns: `ABC-1234`, `ABC1234`, `ABC_1234`

## Configuration

Edit `config.yml` to customize the scraper behavior:

```yaml
scraper:
  sites:
    - name: "javbus"
      url: "https://www.javbus.com"
      enabled: true
    - name: "javlibrary"
      url: "https://www.javlibrary.com"
      enabled: true
    - name: "javdb"
      url: "https://javdb.com"
      enabled: true
  
  max_threads: 5
  timeout: 30
  
  video_extensions: [".mp4", ".avi", ".mkv", ".wmv", ".mov"]
  
  create_nfo: true
  download_cover: true
  translate_title: true
  language: "en"
```

## Output Structure

For each JAV file, the scraper creates:

```
📁 JAV_CODE/
├── 📄 JAV_CODE.nfo          # NFO file for media servers
├── 🖼️ JAV_CODE-poster.jpg   # Cover image
├── 📄 JAV_CODE-metadata.json # Complete metadata
└── 🎬 Original video file
```

## API Endpoints

- `GET /` - Main application interface
- `POST /api/scan-folder` - Scan folder for JAV files
- `POST /api/start-scraping` - Start scraping process
- `GET /api/job-status` - Get current job status
- `POST /api/stop-scraping` - Stop scraping process
- `GET /api/test-connection` - Test scraping site connections
- `GET /api/config` - Get current configuration

## Troubleshooting

### Common Issues

1. **No files detected**
   - Ensure files follow JAV naming convention (XXXX-NNNN)
   - Check file extensions are supported
   - Verify folder path is correct

2. **Scraping fails**
   - Test connection to scraping sites
   - Check internet connection
   - Review log files for detailed errors

3. **Slow performance**
   - Reduce `max_threads` in config
   - Check network connection
   - Close other applications

### Log Files
- Application logs: `scraper.log`
- Check logs for detailed error information

## Legal Notice

⚠️ **Important**: This software is for educational and personal use only.

- **Educational Purpose**: Designed for learning Python and web scraping techniques
- **Personal Use**: Intended for personal media organization only
- **Legal Compliance**: Users must comply with local laws and regulations
- **No Commercial Use**: Commercial use is strictly prohibited
- **Privacy**: Respect website terms of service and robots.txt

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the GPL-3.0 License. See the LICENSE file for details.

## Acknowledgments

- Inspired by [JavSP](https://github.com/Yuukiy/JavSP) project
- Built with Flask, Bootstrap, and modern web technologies
- Uses BeautifulSoup for web scraping

## Support

If you encounter issues or have questions:

1. Check the troubleshooting section above
2. Review the log files for error details
3. Open an issue on the project repository
4. Provide detailed information about your setup and the problem

---

**Disclaimer**: This tool is provided as-is for educational purposes. Users are responsible for ensuring compliance with applicable laws and website terms of service. 