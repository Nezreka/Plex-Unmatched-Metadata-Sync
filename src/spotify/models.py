# src/spotify/models.py

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class SpotifyArtistInfo:
    """Data class to store fetched Spotify artist information"""
    id: str
    name: str
    genres: List[str]
    popularity: int
    followers: int
    images: List[Dict[str, Any]]  # URLs of different sized images
    spotify_url: str
    bio: Optional[str] = None