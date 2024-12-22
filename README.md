# Plex Unmatched Metadata Sync

## Description
This application enhances your Plex music library by automatically updating artist metadata using Spotify's API. It adds accurate artist information including genres, biographies, popularity data, and profile images, with a focus on previously unmatched artists.

## Features
- Automatically matches Plex artists with Spotify artists
- Updates artist metadata:
  - Genres
  - Custom biography based on Spotify data
  - Profile images
  - Popularity and follower statistics
- Interactive review process for artist matches
- Detailed logging and progress tracking
- Rich console interface with progress bars
- Rate limiting to respect API constraints

## Prerequisites
- Python 3.7+
- Plex Media Server
- Spotify Developer Account
- Plex server with write permissions

## Installation
1. Clone the repository:
```bash
git clone https://github.com/Nezreka/Plex-Unmatched-Metadata-Sync.git
cd Plex-Unmatched-Metadata-Sync
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Edit the `config.json` file in the `config` folder:
```json
{
    "plex": {
        "base_url": "http://localhost:32400",
        "token": "your-plex-token-here",
        "library_name": "Music"
    },
    "spotify": {
        "client_id": "your-spotify-client-id-here",
        "client_secret": "your-spotify-client-secret-here"
    },
    "anthropic": {
        "api_key": "your-claude-api-key-here OPTIONAL"
    },
    "matching": {
        "similarity_threshold": 0.85,
        "use_claude_fallback": true
    }
}
```

## Configuration
### Getting Plex Token
1. Sign in to Plex web app
2. Check your browser's cookies for 'X-Plex-Token'
   - Or use the [Plex Token tool](https://github.com/Arcanemagus/plex-api-token-generator)

### Getting Spotify Credentials
1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new application
3. Get your Client ID and Client Secret

## Usage
1. Run the script:
```bash
python run.py
```

2. Follow the interactive prompts:
   - Select your music library
   - Review artist matches
   - Confirm updates

3. The app will:
   - Search for each artist on Spotify
   - Present potential matches for review
   - Apply approved updates to your Plex library

## Update Process
1. **Artist Matching**
   - Searches Spotify for each Plex artist
   - Uses name matching algorithms for accuracy
   - Presents matches for review

2. **Metadata Updates**
   - Genres from Spotify
   - Custom biography including:
     - Genre information
     - Popularity status
     - Follower count
   - Profile images
   - Basic artist information

3. **Progress Tracking**
   - Real-time progress bars
   - Detailed success/failure statistics
   - Complete summary after updates

## Console Output
The application provides rich console output including:
- Progress bars for overall process
- Color-coded status messages
- Detailed summary statistics
- Error reporting

## Logging
Detailed logs are maintained for:
- API interactions
- Metadata updates
- Errors and warnings
- Match decisions

## Error Handling
- Robust error handling for API failures
- Rate limiting protection
- Detailed error logging
- Graceful failure recovery

## Statistics
After completion, displays:
- Total artists processed
- Successful updates
- Failed updates
- Skipped artists
- Images updated
- Biographies updated
- Total duration

## Known Limitations
- Spotify API rate limits (handled automatically)
- Genre information may be limited for lesser-known artists
- API dependency on Spotify and Plex services

## Contributing
Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License
MIT License

Copyright (c) 2023 Nezreka

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Support
For issues and feature requests, please use the GitHub issues page.

## Acknowledgments
- Spotify Web API
- Plex Media Server
- PlexAPI Python Library
- Spotipy Library
