# src/spotify/connector.py

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Dict, Optional, List, Any, Tuple
import time
import logging
from dataclasses import dataclass
from urllib.parse import quote
import re
from difflib import SequenceMatcher

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

class SpotifyConnector:
    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initialize Spotify connector with rate limiting and caching
        
        Args:
            config: Dictionary containing Spotify credentials
            logger: Logger instance
        """
        self.logger = logger
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.spotify = None
        self._connect()
        
        # Rate limiting parameters
        self.last_request_time = 0
        self.min_request_interval = 0.05  # 50ms between requests
        self.request_count = 0
        self.request_limit = 25  # requests per window
        self.window_size = 30  # seconds
        self.window_start = time.time()
        
        # Cache for artist searches
        self.cache = {}

    def _connect(self) -> None:
        """Establish connection to Spotify API"""
        try:
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            self.spotify = spotipy.Spotify(auth_manager=auth_manager)
            self.logger.info("Successfully connected to Spotify API")
        except Exception as e:
            self.logger.error(f"Failed to connect to Spotify API: {str(e)}")
            raise

    def _handle_rate_limit(self) -> None:
        """Handle rate limiting for Spotify API requests"""
        current_time = time.time()
        
        # Reset window if needed
        if current_time - self.window_start > self.window_size:
            self.window_start = current_time
            self.request_count = 0
        
        # Check if we need to wait
        if self.request_count >= self.request_limit:
            sleep_time = self.window_size - (current_time - self.window_start)
            if sleep_time > 0:
                self.logger.debug(f"Rate limit reached, waiting {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                self.window_start = time.time()
                self.request_count = 0
        
        # Ensure minimum interval between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()
        self.request_count += 1

    def _normalize_artist_name(self, name: str) -> str:
        """
        Normalize artist name for comparison
        - Convert to lowercase
        - Remove special characters
        - Remove extra spaces
        - Remove common prefixes/suffixes
        """
        # Convert to lowercase
        name = name.lower()
        
        # Remove common prefixes/suffixes in parentheses or brackets
        name = re.sub(r'\([^)]*\)', '', name)
        name = re.sub(r'\[[^]]*\]', '', name)
        
        # Remove special characters but keep hyphen and period
        name = re.sub(r'[^a-z0-9\-\.]', ' ', name)
        
        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)
        
        # Remove spaces around hyphens
        name = re.sub(r'\s*-\s*', '-', name)
        
        # Strip leading/trailing spaces
        name = name.strip()
        
        return name

    def _calculate_similarity_score(self, name1: str, name2: str) -> Tuple[float, bool]:
        """
        Calculate similarity between two artist names
        Returns: (similarity_score, is_exact_match)
        """
        norm1 = self._normalize_artist_name(name1)
        norm2 = self._normalize_artist_name(name2)
        
        # Check for exact match after normalization
        if norm1 == norm2:
            return (1.0, True)
        
        # Initialize similarity score
        similarity = 0.0
        
        # Use SequenceMatcher for fuzzy matching
        sequence_similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Check for contained names (e.g., "The Beatles" vs "Beatles")
        if norm1 in norm2 or norm2 in norm1:
            contained_similarity = len(min(norm1, norm2, key=len)) / len(max(norm1, norm2, key=len))
            similarity = max(sequence_similarity, contained_similarity)
        else:
            similarity = sequence_similarity
        
        return (similarity, False)

    def search_artist(self, artist_name: str) -> List[SpotifyArtistInfo]:
        """
        Search for an artist on Spotify with enhanced matching
        """
        cache_key = self._normalize_artist_name(artist_name)
        if cache_key in self.cache:
            self.logger.debug(f"Cache hit for artist: {artist_name}")
            return self.cache[cache_key]

        try:
            self._handle_rate_limit()
            
            # First try exact artist search
            exact_results = self.spotify.search(
                q=f"artist:\"{quote(artist_name)}\"",
                type='artist',
                limit=20  # Increased limit to find more potential matches
            )

            candidates = []
            seen_ids = set()

            # Process all results and calculate similarity scores
            for item in exact_results['artists']['items']:
                if item['id'] not in seen_ids:
                    seen_ids.add(item['id'])
                    similarity_score, is_exact = self._calculate_similarity_score(
                        artist_name, item['name']
                    )
                    
                    # Only consider results with good similarity
                    if similarity_score > 0.8:  # Adjust threshold as needed
                        full_artist = self.spotify.artist(item['id'])
                        artist_info = SpotifyArtistInfo(
                            id=full_artist['id'],
                            name=full_artist['name'],
                            genres=full_artist['genres'],
                            popularity=full_artist['popularity'],
                            followers=full_artist['followers']['total'],
                            images=full_artist['images'],
                            spotify_url=full_artist['external_urls']['spotify']
                        )
                        candidates.append((artist_info, similarity_score, is_exact))

            # Sort candidates by:
            # 1. Exact match
            # 2. Similarity score
            # 3. Popularity
            candidates.sort(key=lambda x: (
                x[2],  # is_exact
                x[1],  # similarity_score
                x[0].popularity
            ), reverse=True)

            # If we have multiple exact matches, choose the one with highest popularity
            final_results = []
            exact_matches = [c for c in candidates if c[2]]  # Get all exact matches
            
            if exact_matches:
                # Take the most popular exact match
                best_match = max(exact_matches, key=lambda x: x[0].popularity)
                final_results.append(best_match[0])
            else:
                # Take top 3 close matches
                final_results.extend(c[0] for c in candidates[:3])

            # Cache results
            self.cache[cache_key] = final_results
            return final_results

        except Exception as e:
            self.logger.error(f"Error searching for artist '{artist_name}': {str(e)}")
            return []

    def get_artist_metadata_status(self, artist: SpotifyArtistInfo) -> Dict[str, bool]:
        """
        Check what metadata is available for an artist
        """
        return {
            'has_genres': len(artist.genres) > 0,
            'has_images': len(artist.images) > 0,
            'has_popularity': artist.popularity > 0,
            'has_followers': artist.followers > 0
        }

    def get_artist_details(self, artist_id: str) -> Optional[SpotifyArtistInfo]:
        """
        Get detailed information for a specific artist
        
        Args:
            artist_id: Spotify artist ID
            
        Returns:
            Detailed artist information or None if not found
        """
        try:
            self._handle_rate_limit()
            
            artist = self.spotify.artist(artist_id)
            
            return SpotifyArtistInfo(
                id=artist['id'],
                name=artist['name'],
                genres=artist['genres'],
                popularity=artist['popularity'],
                followers=artist['followers']['total'],
                images=artist['images'],
                spotify_url=artist['external_urls']['spotify']
            )

        except Exception as e:
            self.logger.error(f"Error fetching artist details for ID '{artist_id}': {str(e)}")
            return None

    def test_connection(self) -> bool:
        """Test the Spotify API connection"""
        try:
            # Try to search for a common artist as a test
            test_result = self.search_artist("The Beatles")
            return len(test_result) > 0
        except Exception as e:
            self.logger.error(f"Spotify connection test failed: {str(e)}")
            return False