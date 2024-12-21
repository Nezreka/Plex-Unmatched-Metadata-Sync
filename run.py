# run.py

from src.utils.config_loader import load_config, ConfigError
from src.utils.logger import setup_logger
from src.plex.connector import PlexConnector
from src.spotify.connector import SpotifyConnector
from typing import List
import sys

def test_spotify_search(spotify: SpotifyConnector, artist_names: List[str]) -> None:
    """Test Spotify search with some sample artists"""
    for artist_name in artist_names:
        print(f"\nSearching for: {artist_name}")
        results = spotify.search_artist(artist_name)
        if results:
            print(f"Found {len(results)} potential matches:")
            for i, artist in enumerate(results, 1):
                print(f"  {i}. {artist.name}")
                
                # Show available metadata
                metadata_status = spotify.get_artist_metadata_status(artist)
                print("     Available metadata:")
                for key, has_data in metadata_status.items():
                    status = "✓" if has_data else "✗"
                    print(f"       {key}: {status}")
                
                if artist.genres:
                    print(f"     Genres: {', '.join(artist.genres[:3])}")
                else:
                    print(f"     Genres: No genres assigned")
                print(f"     Popularity: {artist.popularity}/100")
                print(f"     Followers: {artist.followers:,}")
                print(f"     Spotify URL: {artist.spotify_url}")
        else:
            print("No matches found")

def main():
    logger = setup_logger()
    
    try:
        logger.info("Loading configuration...")
        config = load_config()
        logger.info("Configuration loaded successfully!")
        
        # Initialize Spotify connection
        logger.info("Initializing Spotify connection...")
        spotify = SpotifyConnector(config['spotify'], logger)
        if not spotify.test_connection():
            logger.error("Failed to establish Spotify connection")
            return 1
        
        # Initialize and test Plex connection
        logger.info("Initializing Plex connection...")
        plex = PlexConnector(config['plex'], logger)
        if not plex.test_connection():
            logger.error("Failed to establish Plex connection")
            return 1
            
        # Get unmatched artists
        unmatched_artists = plex.get_unmatched_artists()
        
        if unmatched_artists:
            logger.info(f"\nFound {len(unmatched_artists)} unmatched artists")
            
            # Test Spotify search with first few unmatched artists
            test_artists = [artist.title for artist in unmatched_artists[:5]]
            test_spotify_search(spotify, test_artists)
            
        else:
            logger.info("No unmatched artists found")
            
    except ConfigError as e:
        logger.error(f"Configuration Error: {str(e)}")
        logger.info("Please update your configuration and try again.")
        return 1
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())