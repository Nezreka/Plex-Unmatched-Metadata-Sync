from typing import Dict, List, Optional, Any
from ..spotify.connector import SpotifyArtistInfo, SpotifyConnector
import logging
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, BarColumn, TextColumn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from plexapi.server import PlexServer
from datetime import datetime
import time

class PlexArtistUpdater:
    def __init__(self, plex_server: PlexServer, spotify_connector: SpotifyConnector, logger: logging.Logger):
        self.plex = plex_server
        self.spotify = spotify_connector
        self.logger = logger
        self.console = Console()
        self.stats = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'image_updated': 0,
            'metadata_updated': 0,
            'bios_updated': 0,  # New stat for bios
            'started_at': None,
            'completed_at': None
        }

    def apply_decisions(self, decisions: Dict[str, Dict]):
            """Apply the review decisions to Plex with detailed progress reporting"""
            try:
                self.stats['started_at'] = datetime.now()
                update_candidates = [d for d in decisions.values() 
                                if d['action'] in ['accept_primary', 'accept_alternative', 'manual_match']]
                self.stats['total'] = len(update_candidates)

                self.logger.info(f"Starting updates for {len(update_candidates)} artists")
                self.console.print(Panel(f"Starting updates for {len(update_candidates)} artists", 
                                    style="bold blue"))

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeElapsedColumn(),
                    console=self.console
                ) as progress:
                    overall_task = progress.add_task(
                        "[cyan]Overall progress", 
                        total=len(update_candidates)
                    )
                    
                    for rating_key, decision in decisions.items():
                        if decision['action'] not in ['accept_primary', 'accept_alternative', 'manual_match']:
                            self.logger.info(f"Skipping {decision['plex_artist']} - action: {decision['action']}")
                            self.stats['skipped'] += 1
                            continue

                        artist_name = decision['plex_artist']
                        self.logger.info(f"Processing {artist_name}")
                        progress.update(overall_task, description=f"[cyan]Processing {artist_name}")

                        try:
                            # Use stored Spotify data instead of fetching it again
                            spotify_data = decision.get('spotify_data')
                            if spotify_data:
                                self.logger.info(f"Updating Plex metadata for {artist_name}")
                                success = self._update_artist_metadata(rating_key, spotify_data)
                                
                                if success:
                                    self.logger.info(f"Successfully updated {artist_name}")
                                    self.stats['successful'] += 1
                                    progress.update(overall_task, advance=1)
                                else:
                                    self.logger.error(f"Failed to update {artist_name}")
                                    self.stats['failed'] += 1
                            else:
                                self.logger.error(f"No Spotify data available for {artist_name}")
                                self.stats['failed'] += 1

                        except Exception as e:
                            self.logger.error(f"Error processing {artist_name}: {str(e)}")
                            self.stats['failed'] += 1

            except KeyboardInterrupt:
                self.logger.info("\nUpdate process interrupted by user")
                self.stats['completed_at'] = datetime.now()
                self._display_update_summary()
                return
            except Exception as e:
                self.logger.error(f"Error during update process: {str(e)}")
                self.stats['completed_at'] = datetime.now()
                self._display_update_summary()
                return

            self.stats['completed_at'] = datetime.now()
            self._display_update_summary()

    def _update_artist_metadata(self, rating_key: str, spotify_data: SpotifyArtistInfo) -> bool:
        """Update a single artist's metadata in Plex"""
        try:
            self.logger.info(f"Fetching Plex item for rating key: {rating_key}")
            artist = self.plex.fetchItem(rating_key)
            
            # Debug genre information before update
            self.logger.info(f"Current Plex genres for {spotify_data.name}: {artist.genres}")
            self.logger.info(f"Spotify genres for {spotify_data.name}: {spotify_data.genres}")
            self.logger.info(f"Spotify genres type: {type(spotify_data.genres)}")
            
            # Update basic metadata
            self.logger.info(f"Updating metadata for: {spotify_data.name}")
            
            # Handle genres properly for Plex
            metadata_updates = {
                "title.value": spotify_data.name,
            }
            
            if spotify_data.genres:
                # Ensure genres is a list of strings
                genres_list = spotify_data.genres if isinstance(spotify_data.genres, list) else [spotify_data.genres]
                self.logger.info(f"Processed genres list: {genres_list}")
                
                # Try updating genres directly on the artist object first
                try:
                    self.logger.info("Attempting to update genres directly on artist object")
                    artist.genres = genres_list
                    self.logger.info(f"Direct genre update result: {artist.genres}")
                except Exception as e:
                    self.logger.warning(f"Direct genre update failed: {str(e)}")
                
                # Try different genre field names that Plex might accept
                genre_updates = {
                    "genre.value": genres_list,
                    "genre[]": genres_list,
                    "genre": genres_list,
                    "genres": genres_list,
                    "genre.locked": 1,  # Try locking the genre field
                    "genre[].locked": 1
                }
                # Add all possible genre field formats
                metadata_updates.update(genre_updates)
                self.logger.info(f"Attempting to set genres with multiple field names: {genre_updates}")
                
                # Try individual genre updates
                for genre in genres_list:
                    try:
                        self.logger.info(f"Attempting to add single genre: {genre}")
                        artist.addGenre(genre)
                    except Exception as e:
                        self.logger.warning(f"Failed to add individual genre {genre}: {str(e)}")
            
            # Generate bio directly from spotify_data
            try:
                self.logger.info(f"Generating bio for: {spotify_data.name}")
                bio_parts = []
                
                # Add name and genres
                if spotify_data.genres:
                    genres_text = ", ".join(spotify_data.genres)
                    bio_parts.append(f"{spotify_data.name} is an artist known for their work in {genres_text}.")
                else:
                    bio_parts.append(f"{spotify_data.name} is a recording artist.")
                
                # Add popularity and followers info
                if spotify_data.popularity > 0:
                    popularity_text = "rising" if spotify_data.popularity < 40 else "popular" if spotify_data.popularity < 70 else "highly popular"
                    bio_parts.append(f"They are a {popularity_text} artist on Spotify")
                    
                    if spotify_data.followers > 0:
                        bio_parts[-1] += f" with {spotify_data.followers:,} followers."
                    else:
                        bio_parts[-1] += "."
                
                # Combine all parts
                if bio_parts:
                    bio = " ".join(bio_parts)
                    metadata_updates["summary.value"] = bio
                    self.stats['bios_updated'] = self.stats.get('bios_updated', 0) + 1
                    self.logger.info("Bio generated and added to metadata updates")
                
            except Exception as bio_error:
                self.logger.warning(f"Bio generation failed for {spotify_data.name}, continuing without bio: {str(bio_error)}")
            
            # Debug metadata updates
            self.logger.info(f"Final metadata updates for {spotify_data.name}: {metadata_updates}")
            
            # Apply metadata updates
            self.logger.info("Applying metadata updates")
            artist.edit(**metadata_updates)
            self.stats['metadata_updated'] += 1
            
            # Verify genre update
            artist.reload()  # Reload to get updated data
            self.logger.info(f"Genres after update for {spotify_data.name}: {artist.genres}")
            
            # Update artist image if available
            if spotify_data.images:
                self.logger.info("Updating artist image")
                image_url = spotify_data.images[0]['url']
                try:
                    artist.uploadPoster(url=image_url)
                    self.stats['image_updated'] += 1
                    self.logger.info("Image update successful")
                except Exception as e:
                    self.logger.error(f"Failed to update image for {spotify_data.name}: {str(e)}")
            else:
                self.logger.info("No images available for artist")
            
            self.logger.info(f"Successfully updated {spotify_data.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating metadata for {rating_key}: {str(e)}")
            return False

    def _display_update_summary(self):
        """Display a detailed summary of the update process"""
        duration = self.stats['completed_at'] - self.stats['started_at']
        
        # Create summary table
        table = Table(title="Update Summary", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        # Add statistics
        table.add_row("Total Artists Processed", str(self.stats['total']))
        table.add_row("Successfully Updated", str(self.stats['successful']))
        table.add_row("Failed Updates", str(self.stats['failed']))
        table.add_row("Skipped Artists", str(self.stats['skipped']))
        table.add_row("Images Updated", str(self.stats['image_updated']))
        table.add_row("Metadata Updated", str(self.stats['metadata_updated']))
        table.add_row("Biographies Updated", str(self.stats.get('bios_updated', 0)))
        table.add_row("Total Duration", str(duration).split('.')[0])  # Remove microseconds
        
        # Calculate success rate
        if self.stats['total'] > 0:
            success_rate = (self.stats['successful'] / self.stats['total']) * 100
            table.add_row("Success Rate", f"{success_rate:.1f}%")
        
        self.console.print("\n")
        self.console.print(table)
        
        # Display errors if any
        if self.stats['failed'] > 0:
            self.console.print("\n[yellow]Note: Check the log file for details about failed updates.[/yellow]")