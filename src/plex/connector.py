# src/plex/connector.py

from plexapi.server import PlexServer
from plexapi.exceptions import NotFound, Unauthorized
from typing import List, Optional
import time
from dataclasses import dataclass
import logging
from tqdm import tqdm

@dataclass
class UnmatchedArtist:
    """Data class to store unmatched artist information"""
    title: str
    library_section_id: int
    rating_key: str
    guid: str
    original_title: Optional[str] = None
    section_title: Optional[str] = None

class PlexConnector:
    def __init__(self, config: dict, logger: logging.Logger):
        """
        Initialize Plex connector
        
        Args:
            config: Dictionary containing Plex configuration
            logger: Logger instance
        """
        self.logger = logger
        self.base_url = config['base_url']
        self.token = config['token']
        self.library_name = config['library_name']
        self.server = None
        self.music_section = None

    def connect(self) -> bool:
        """
        Establish connection to Plex server
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.logger.info(f"Connecting to Plex server at {self.base_url}...")
            self.server = PlexServer(self.base_url, self.token)
            self.logger.info(f"Successfully connected to Plex server: {self.server.friendlyName}")
            
            # Get music library section
            try:
                self.music_section = self.server.library.section(self.library_name)
                self.logger.info(f"Successfully connected to music library: {self.library_name}")
                return True
            except NotFound:
                self.logger.error(f"Music library '{self.library_name}' not found!")
                self.logger.info("Available libraries:")
                for section in self.server.library.sections():
                    self.logger.info(f"  - {section.title}")
                return False
                
        except Unauthorized:
            self.logger.error("Failed to connect: Invalid Plex token")
            return False
        except Exception as e:
            self.logger.error(f"Failed to connect to Plex server: {str(e)}")
            return False

# src/plex/connector.py

    def get_unmatched_artists(self) -> List[UnmatchedArtist]:
            """
            Retrieve all unmatched artists from the music library.
            An artist is considered unmatched if:
            - It has no metadata agent guid (local guid only)
            - It's marked as unmatched by Plex
            
            Returns:
                List[UnmatchedArtist]: List of unmatched artists
            """
            if not self.music_section:
                self.logger.error("No music library connection available")
                return []

            try:
                self.logger.info("Scanning for unmatched artists...")
                
                # Get all artists
                all_artists = self.music_section.all(libtype='artist')
                total_artists = len(all_artists)
                
                self.logger.info(f"Scanning {total_artists} total artists...")
                unmatched = []
                
                # Create progress bar
                with tqdm(total=total_artists, desc="Scanning artists", unit="artist") as pbar:
                    for artist in all_artists:
                        is_unmatched = False
                        
                        # Check if artist has only a local guid or no guid
                        if not artist.guid or 'local://' in artist.guid:
                            is_unmatched = True
                        
                        # Additional check for Plex's internal matching status
                        try:
                            if hasattr(artist, 'matchedMetadata') and not artist.matchedMetadata:
                                is_unmatched = True
                        except:
                            pass

                        # Check the preferences to see if it's been matched
                        try:
                            if hasattr(artist, 'preferences'):
                                for pref in artist.preferences():
                                    if pref.id == 'matchAgency' and not pref.value:
                                        is_unmatched = True
                                        break
                        except:
                            pass

                        if is_unmatched:
                            unmatched.append(UnmatchedArtist(
                                title=artist.title,
                                library_section_id=artist.librarySectionID,
                                rating_key=artist.ratingKey,
                                guid=artist.guid,
                                original_title=getattr(artist, 'originalTitle', None),
                                section_title=self.music_section.title
                            ))
                            # Output unmatched artists in real-time (debug level)
                            self.logger.debug(f"Found unmatched: {artist.title}")
                        
                        pbar.update(1)

                self.logger.info(f"\nFound {len(unmatched)} unmatched artists")
                
                # Debug logging for verification
                self.logger.debug("First few unmatched artists for verification:")
                for i, artist in enumerate(unmatched[:5], 1):
                    self.logger.debug(f"  {i}. {artist.title} (GUID: {artist.guid})")

                return unmatched

            except Exception as e:
                self.logger.error(f"Error scanning for unmatched artists: {str(e)}")
                return []

    def verify_unmatched_status(self, artist) -> bool:
        """
        Helper method to verify if an artist is truly unmatched
        """
        try:
            # Get detailed metadata
            metadata = artist.item.fetchItem()
            
            # Check various indicators of matching status
            is_unmatched = (
                not metadata.guid or
                'local://' in metadata.guid or
                (hasattr(metadata, 'matchedMetadata') and not metadata.matchedMetadata)
            )
            
            return is_unmatched
        except:
            return False

    def test_connection(self) -> bool:
        """
        Test the Plex connection and library access
        
        Returns:
            bool: True if all tests pass, False otherwise
        """
        if not self.connect():
            return False

        try:
            # Test basic server info
            self.logger.info(f"Plex Server Version: {self.server.version}")
            
            # Test music library access
            artist_count = len(self.music_section.search(libtype='artist', limit=1))
            self.logger.info(f"Successfully accessed music library")
            
            return True

        except Exception as e:
            self.logger.error(f"Connection test failed: {str(e)}")
            return False