# src/spotify/connector.py

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Dict, Optional, List, Any, Tuple
import time
import logging
from urllib.parse import quote
import re
from difflib import SequenceMatcher
from .models import SpotifyArtistInfo
from functools import lru_cache

class SpotifyConnector:
    def __init__(self, config: dict, logger: logging.Logger):
        self.logger = logger
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.spotify = None
        self._connect()
        
        # Rate limiting parameters 
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Increased from 0.05
        self.request_count = 0
        self.request_limit = 20  # Decreased from 25
        self.window_size = 30
        self.window_start = time.time()
        
        # Cache settings (leave these unchanged)
        self.cache = {}
        self.cache_timeout = config.get('cache_timeout', 3600)  # 1 hour default
        self.cache_max_size = config.get('cache_max_size', 1000)

    def _connect(self) -> None:
        """Establish connection to Spotify API"""
        try:
            auth_manager = SpotifyClientCredentials(
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            # Create client with custom settings
            self.spotify = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=10,
                retries=3
            )
            self.logger.info("Successfully connected to Spotify API")
        except Exception as e:
            self.logger.error(f"Failed to connect to Spotify API: {str(e)}")
            raise

    def _handle_rate_limit(self) -> None:
        """Handle rate limiting for Spotify API requests"""
        current_time = time.time()
        
        # Debug logging for rate limit status
        self.logger.debug(
            f"Rate limit status: {self.request_count}/{self.request_limit} "
            f"requests in current window, "
            f"window expires in {self.window_size - (current_time - self.window_start):.1f}s"
        )
        
        # Reset window if needed
        if current_time - self.window_start > self.window_size:
            self.window_start = current_time
            self.request_count = 0
        
        # If well under limit, proceed without delay
        if self.request_count < (self.request_limit * 0.8):
            self.request_count += 1
            return
        
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

    def _check_cache(self, cache_key: str) -> Optional[List[SpotifyArtistInfo]]:
        """Check cache with expiry"""
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            cache_time = cache_entry.get('time', 0)
            if time.time() - cache_time < self.cache_timeout:
                self.logger.debug(f"Cache hit for: {cache_key}")
                return cache_entry.get('data')
            else:
                # Remove expired entry
                del self.cache[cache_key]
        return None

    def _update_cache(self, cache_key: str, data: List[SpotifyArtistInfo]) -> None:
        """Update cache with timestamp"""
        self.cache[cache_key] = {
            'time': time.time(),
            'data': data
        }
        self._cleanup_cache()

    def _cleanup_cache(self) -> None:
        """Remove oldest entries if cache exceeds max size"""
        if len(self.cache) > self.cache_max_size:
            # Sort by timestamp and keep newest entries
            sorted_cache = sorted(self.cache.items(), 
                                key=lambda x: x[1]['time'], 
                                reverse=True)
            self.cache = dict(sorted_cache[:self.cache_max_size])

    def _normalize_artist_name(self, name: str) -> str:
        """Normalize artist name for comparison"""
        if not name:
            return ""
            
        # Convert to lowercase
        name = name.lower()
        
        # Remove common prefixes/suffixes in parentheses or brackets
        name = re.sub(r'\([^)]*\)', '', name)
        name = re.sub(r'\[[^]]*\]', '', name)
        
        # Handle special characters but preserve important ones
        name = re.sub(r'[^\w\s\-]', '', name)
        
        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)
        
        # Strip leading/trailing spaces
        name = name.strip()
        
        self.logger.debug(f"Normalized name: '{name}'")
        return name

    def _process_complex_artist_name(self, artist_name: str) -> Optional[List[SpotifyArtistInfo]]:
        """Handle artists with multiple names or special characters"""
        # Split on common separators
        separators = ['&', ',', 'and', 'feat.', 'ft.', '+']
        parts = artist_name
        for sep in separators:
            parts = parts.replace(sep, '|')
        artists = [a.strip() for a in parts.split('|') if a.strip()]
        
        self.logger.debug(f"Processing complex name: '{artist_name}' -> {artists}")
        
        # Search for primary artist (first name)
        if artists:
            primary_results = self.search_artist(artists[0], exact_match=True)
            if primary_results:
                return primary_results
            
            # Try the longest name segment as backup
            longest_name = max(artists, key=len)
            if longest_name != artists[0]:
                return self.search_artist(longest_name, exact_match=True)
        
        return None

    def _calculate_similarity_score(self, name1: str, name2: str) -> Tuple[float, bool]:
        """Calculate similarity between two artist names"""
        norm1 = self._normalize_artist_name(name1)
        norm2 = self._normalize_artist_name(name2)
        
        # Check for exact match after normalization
        if norm1 == norm2:
            return (1.0, True)
        
        # Initialize similarity score
        similarity = 0.0
        
        # Use SequenceMatcher for fuzzy matching
        sequence_similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Check for contained names
        if norm1 in norm2 or norm2 in norm1:
            contained_similarity = len(min(norm1, norm2, key=len)) / len(max(norm1, norm2, key=len))
            similarity = max(sequence_similarity, contained_similarity)
        else:
            similarity = sequence_similarity
        
        return (similarity, False)

    def _validate_artist_data(self, artist_data: Dict) -> bool:
        """Validate required fields in artist data"""
        required_fields = ['id', 'name']
        return all(field in artist_data for field in required_fields)
    
    def get_artist_by_id(self, spotify_id: str) -> Optional[SpotifyArtistInfo]:
        """Fetch artist data by Spotify ID"""
        try:
            self.logger.info(f"Starting Spotify API request for ID: {spotify_id}")
            self._handle_rate_limit()  # Make sure we're not rate limited
            
            # Add timing debug
            start_time = time.time()
            self.logger.debug(f"Making Spotify API call at {start_time}")
            
            # Force a new token if needed
            if not self.spotify.auth_manager.get_access_token():
                self.logger.info("Refreshing Spotify access token")
                self._connect()
            
            artist = self.spotify.artist(spotify_id)
            
            end_time = time.time()
            self.logger.debug(f"Spotify API call completed in {end_time - start_time:.2f} seconds")
            
            if not artist:
                self.logger.error(f"No artist data returned for ID: {spotify_id}")
                return None
                
            self.logger.info("Successfully fetched artist data from Spotify")
            
            return SpotifyArtistInfo(
                id=artist['id'],
                name=artist['name'],
                popularity=artist['popularity'],
                genres=artist['genres'],
                followers=artist['followers']['total'],
                spotify_url=artist['external_urls']['spotify'],
                images=artist['images']
            )
        except spotipy.exceptions.SpotifyException as e:
            self.logger.error(f"Spotify API error for ID {spotify_id}: {str(e)}")
            if e.http_status == 429:  # Rate limiting
                retry_after = int(e.headers.get('Retry-After', 5))
                self.logger.warning(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
            return None
        except Exception as e:
            self.logger.error(f"Error fetching artist by ID {spotify_id}: {str(e)}")
            return None

    def _create_artist_info(self, artist_data: Dict) -> Optional[SpotifyArtistInfo]:
        """Create SpotifyArtistInfo object with validation"""
        if not self._validate_artist_data(artist_data):
            self.logger.warning(f"Invalid artist data received: {artist_data}")
            return None
            
        return SpotifyArtistInfo(
            id=artist_data['id'],
            name=artist_data['name'],
            genres=artist_data.get('genres', []),
            popularity=artist_data.get('popularity', 0),
            followers=artist_data.get('followers', {}).get('total', 0),
            images=artist_data.get('images', []),
            spotify_url=artist_data.get('external_urls', {}).get('spotify', '')
        )
    
    def get_artist_bio(self, artist_id: str) -> Optional[str]:
        """Generate artist biography from available data"""
        try:
            # Use the artist data we already have from the cache
            artist = self.get_artist_by_id(artist_id)
            if not artist:
                return None
            
            # Construct bio from available data
            bio_parts = []
            
            # Add name and genres
            if artist.genres:
                genres_text = ", ".join(artist.genres)
                bio_parts.append(f"{artist.name} is an artist known for their work in {genres_text}.")
            else:
                bio_parts.append(f"{artist.name} is a recording artist.")
            
            # Add popularity and followers info
            if artist.popularity > 0:
                popularity_text = "rising" if artist.popularity < 40 else "popular" if artist.popularity < 70 else "highly popular"
                bio_parts.append(f"They are a {popularity_text} artist on Spotify")
                
                if artist.followers > 0:
                    bio_parts[-1] += f" with {artist.followers:,} followers."
                else:
                    bio_parts[-1] += "."
            
            # Combine all parts
            bio = " ".join(bio_parts)
            
            return bio
            
        except Exception as e:
            self.logger.error(f"Error generating artist bio: {str(e)}")
            return None

    def search_artist(self, artist_name: str, max_retries: int = 3, retry_delay: float = 1.0, exact_match: bool = False) -> Optional[List[SpotifyArtistInfo]]:
        """Search for an artist on Spotify"""
        if not artist_name:
            self.logger.warning("Empty artist name provided")
            return None

        # Check cache first
        cache_key = f"{artist_name}_{exact_match}"
        cached_result = self._check_cache(cache_key)
        if cached_result is not None:
            return cached_result

        # Clean up artist name for search
        search_name = artist_name.strip()
        normalized_search = self._normalize_artist_name(search_name)
        
        self.logger.debug(f"Searching for: '{search_name}' (normalized: '{normalized_search}')")
        
        # Check if this is a complex artist name
        if any(sep in search_name for sep in ['&', ',', 'and', 'feat.', 'ft.', '+']):
            complex_results = self._process_complex_artist_name(search_name)
            if complex_results:
                self._update_cache(cache_key, complex_results)
                return complex_results

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(retry_delay)

                self._handle_rate_limit()
                results = self.spotify.search(q=search_name, type='artist', limit=20)
                
                if not results or 'artists' not in results or 'items' not in results['artists']:
                    self.logger.debug(f"No valid results found for '{search_name}'")
                    return None

                artists = []
                for artist in results['artists']['items']:
                    try:
                        artist_info = self._create_artist_info(artist)
                        if artist_info:
                            normalized_result = self._normalize_artist_name(artist_info.name)
                            self.logger.debug(f"Comparing: '{normalized_result}' with '{normalized_search}'")
                            
                            if exact_match:
                                if normalized_result == normalized_search:
                                    self.logger.debug(f"Found exact match: {artist_info.name}")
                                    artists.append(artist_info)
                            else:
                                artists.append(artist_info)
                    except Exception as e:
                        self.logger.warning(f"Error processing artist result: {str(e)}")
                        continue

                if artists:
                    self._update_cache(cache_key, artists)
                return artists if artists else None

            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', retry_delay))
                    self.logger.warning(f"Rate limited, waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                elif attempt == max_retries - 1:
                    self.logger.error(f"Spotify API error: {str(e)}")
                    return None
                
            except Exception as e:
                if attempt == max_retries - 1:
                    self.logger.error(f"Failed to search for artist '{search_name}' after {max_retries} attempts: {str(e)}")
                    return None
                self.logger.warning(f"Search attempt {attempt + 1} failed, retrying in {retry_delay} seconds...")
                continue

        return None

    def get_artist_metadata_status(self, artist: SpotifyArtistInfo) -> Dict[str, bool]:
        """Check what metadata is available for an artist"""
        return {
            'has_genres': len(artist.genres) > 0,
            'has_images': len(artist.images) > 0,
            'has_popularity': artist.popularity > 0,
            'has_followers': artist.followers > 0
        }

    @lru_cache(maxsize=1000)
    def get_artist_details(self, artist_id: str) -> Optional[SpotifyArtistInfo]:
        """Get detailed information for a specific artist"""
        try:
            self._handle_rate_limit()
            artist = self.spotify.artist(artist_id)
            return self._create_artist_info(artist)
        except Exception as e:
            self.logger.error(f"Error fetching artist details for ID '{artist_id}': {str(e)}")
            return None

    def test_connection(self) -> bool:
        """Test the Spotify API connection"""
        try:
            test_result = self.search_artist("The Beatles")
            return test_result is not None and len(test_result) > 0
        except Exception as e:
            self.logger.error(f"Spotify connection test failed: {str(e)}")
            return False