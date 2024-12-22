# run.py

from src.utils.config_loader import load_config, ConfigError
from src.utils.logger import setup_logger
from src.plex.connector import PlexConnector
from src.spotify.connector import SpotifyConnector
from src.matching.matcher import ArtistMatcher
from src.utils.results_manager import ResultsManager
from src.review.reviewer import MatchReviewer
import sys
from typing import List
from src.plex.updater import PlexArtistUpdater

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
        
        # Initialize matcher and results manager
        matcher = ArtistMatcher(plex, spotify, config.get('matching', {}), logger)
        results_manager = ResultsManager()
        
        # Get unmatched artists
        logger.info("Scanning for unmatched artists...")
        unmatched_artists = plex.get_unmatched_artists()
        
        if not unmatched_artists:
            logger.info("No unmatched artists found")
            return 0
            
        logger.info(f"Found {len(unmatched_artists)} unmatched artists")
        
        # Process matches
        results = matcher.process_unmatched_artists(unmatched_artists)
        
        # Show detailed results
        if results['matched']:
            logger.info("\nAutomatic Matches:")
            logger.info("=" * 50)
            for i, match in enumerate(results['matched'][:5], 1):  # Show first 5
                logger.info(f"\nMatch {i}:")
                logger.info(matcher.get_match_details_string(match))
                
        if results['needs_review']:
            logger.info("\nMatches Needing Review:")
            logger.info("=" * 50)
            for i, match in enumerate(results['needs_review'][:5], 1):  # Show first 5
                logger.info(f"\nPotential Match {i}:")
                logger.info(matcher.get_match_details_string(match))
                
        if results['no_matches']:
            logger.info("\nNo Matches Found For:")
            logger.info("=" * 50)
            for i, artist in enumerate(results['no_matches'][:5], 1):  # Show first 5
                logger.info(f"{i}. {artist.title}")
        
        # Summary
        total_processed = len(unmatched_artists)
        automatic_matches = len(results['matched'])
        needs_review = len(results['needs_review'])
        no_matches = len(results['no_matches'])
        
        logger.info("\nProcessing Summary:")
        logger.info("=" * 50)
        logger.info(f"Total artists processed: {total_processed}")
        logger.info(f"Automatic matches: {automatic_matches} ({(automatic_matches/total_processed)*100:.1f}%)")
        logger.info(f"Needs review: {needs_review} ({(needs_review/total_processed)*100:.1f}%)")
        logger.info(f"No matches found: {no_matches} ({(no_matches/total_processed)*100:.1f}%)")
        
        
        if results['matched']:
            logger.info(f"\nFound {len(results['matched'])} automatic matches.")
            logger.info("Would you like to update these artists in Plex now? (y/n)")
            if input().lower().strip() == 'y':
                auto_match_decisions = {
                    match.plex_artist.rating_key: {
                        'action': 'accept_primary',
                        'plex_artist': match.plex_artist.title,
                        'spotify_id': match.spotify_match.id,
                        'spotify_data': match.spotify_match  # Store the full SpotifyArtistInfo object
                    }
                    for match in results['matched']
                }
                updater = PlexArtistUpdater(plex.server, spotify, logger)
                updater.apply_decisions(auto_match_decisions)
        
        # Handle user choices
        while True:
            logger.info("\nWould you like to:")
            logger.info("1. Review potential matches")
            logger.info("2. Apply updates to Plex")  # New option
            logger.info("3. Save results for later")
            logger.info("4. Exit")
            
            choice = input("\nEnter your choice (1-4): ").strip()
            
            if choice == "1":
                reviewer = MatchReviewer(spotify, logger)
                try:
                    decisions = reviewer.start_review_session(results)
                    if decisions:
                        logger.info(f"\nReview completed with {len(decisions)} decisions made.")
                        # Save the decisions along with the results
                        results['review_decisions'] = decisions
                        session_id = results_manager.save_results(results)
                        logger.info(f"Results and decisions saved with session ID: {session_id}")
                except Exception as e:
                    logger.error(f"Error during review process: {str(e)}")
                    logger.info("Your progress has been saved.")
                
            elif choice == "2":
                if 'review_decisions' not in results:
                    logger.info("No review decisions found. Please review matches first.")
                    continue
                    
                logger.info("Starting Plex updates...")
                updater = PlexArtistUpdater(plex.server, spotify, logger)
                try:
                    updater.apply_decisions(results['review_decisions'])
                    logger.info("Updates completed!")
                except Exception as e:
                    logger.error(f"Error during update process: {str(e)}")
                break
            elif choice == "3":
                session_id = results_manager.save_results(results)
                logger.info(f"\nResults saved successfully!")
                logger.info(f"Session ID: {session_id}")
                logger.info(f"You can find the results in the 'results' directory.")
                break
            elif choice == "4":
                logger.info("Exiting...")
                break
            else:
                logger.info("Invalid choice. Please enter 1, 2, 3, or 4.")
        
        return 0
            
    except ConfigError as e:
        logger.error(f"Configuration Error: {str(e)}")
        logger.info("Please update your configuration and try again.")
        return 1
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())