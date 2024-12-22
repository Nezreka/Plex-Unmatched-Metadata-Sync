# src/review/reviewer.py

from typing import Dict, List, Optional, Tuple
from ..plex.connector import UnmatchedArtist
from ..spotify.connector import SpotifyConnector, SpotifyArtistInfo
from ..matching.matcher import MatchResult
import logging
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm
import os
import json
from datetime import datetime

class MatchReviewer:
    def __init__(self, spotify_connector: SpotifyConnector, logger: logging.Logger):
        self.spotify = spotify_connector
        self.logger = logger
        self.console = Console()
        self.decisions: Dict[str, Dict] = {}

    def _display_options(self, options: Dict[str, str]):
        """Display available options"""
        table = Table(show_header=False, box=None)
        for key, value in options.items():
            table.add_row(f"{key}.", value)
        self.console.print(table)

    def _review_single_automatic_match(self, match: MatchResult):
        """Review a single automatic match"""
        options = {
            "1": "Accept match",
            "2": "Search manually",
            "3": "Mark as no match",
            "4": "Skip"
        }
        
        self._display_options(options)
        choice = Prompt.ask("Select an option", choices=list(options.keys()))
        
        if choice == "1":
            self._accept_match(match)
        elif choice == "2":
            self._manual_search(match.plex_artist)
        elif choice == "3":
            self._mark_no_match(match)
        # choice 4 (skip) does nothing

    def _display_artist_details(self, artist: UnmatchedArtist):
        """Display details about an unmatched artist"""
        table = Table(title="Artist Details", box=True)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Plex Artist Name", artist.title)
        table.add_row("Rating Key", artist.rating_key)
        
        self.console.print(table)

    def _show_review_menu(self):
        """Display the review menu"""
        self.console.print("\n[bold blue]Review Options:[/bold blue]")
        menu = Table(show_header=False, box=None)
        menu.add_row("1.", "Review uncertain matches")
        menu.add_row("2.", "Review automatic matches")
        menu.add_row("3.", "Review no-match artists")
        menu.add_row("4.", "Batch review")
        menu.add_row("5.", "Save progress")
        menu.add_row("6.", "Show statistics")
        menu.add_row("7.", "Exit review")
        self.console.print(menu)

    def _auto_save(self):
        """Auto-save after certain number of decisions"""
        if len(self.decisions) % 10 == 0:  # Save every 10 decisions
            self._save_review_progress()
            self.console.print("[green]Progress auto-saved[/green]")

    def _add_decision(self, key: str, decision: Dict):
        """Helper method to add decisions with timestamp"""
        decision['timestamp'] = datetime.now().isoformat()
        self.decisions[key] = decision
        self._auto_save()

    def start_review_session(self, results: Dict[str, List]) -> Dict[str, Dict]:
        """Start an interactive review session"""
        # Try to load previous session
        previous_session = self.load_previous_session()
        if previous_session:
            self.decisions = previous_session
            self.console.print("[green]Loaded previous session[/green]")
            self._track_review_stats()  # Show current progress
        else:
            self.decisions = {}
        
        while True:
            try:
                self._show_review_menu()
                choice = Prompt.ask(
                    "Select an option",
                    choices=["1", "2", "3", "4", "5", "6", "7"],
                    default="1"
                )

                if choice == "1":
                    self.logger.debug(f"Starting uncertain matches review. Found {len(results['needs_review'])} matches.")
                    self._review_uncertain_matches(results['needs_review'])
                elif choice == "2":
                    self._review_automatic_matches(results['matched'])
                elif choice == "3":
                    self._review_no_matches(results['no_matches'])
                elif choice == "4":
                    self._batch_review_matches(results['needs_review'])
                elif choice == "5":
                    self._save_review_progress()
                elif choice == "6":
                    self._track_review_stats()
                elif choice == "7":
                    if self._confirm_exit():
                        break
                    
            except Exception as e:
                self.logger.error(f"Error in review session: {str(e)}")
                if Confirm.ask("Would you like to continue?"):
                    continue
                break

        return self.decisions

    def _review_uncertain_matches(self, matches: List[MatchResult]):
        """Review matches that need manual verification"""
        if not matches:
            self.console.print("[yellow]No uncertain matches to review.[/yellow]")
            return

        for match in matches:
            try:
                self._display_match_details(match)
                
                # Show options
                options = {
                    "1": "Accept primary match",
                    "2": "Choose alternative match",
                    "3": "Search manually",
                    "4": "Skip for now",
                    "5": "Mark as no match"
                }
                
                self._display_options(options)
                choice = Prompt.ask("Select an option", choices=list(options.keys()))
                
                if choice == "1":
                    self._accept_match(match)
                elif choice == "2":
                    self._choose_alternative(match)
                elif choice == "3":
                    self._manual_search(match.plex_artist)
                elif choice == "4":
                    continue
                elif choice == "5":
                    self._mark_no_match(match)
            except Exception as e:
                self.logger.error(f"Error processing match: {str(e)}")
                continue

    def _review_automatic_matches(self, matches: List[MatchResult]):
        """Review automatic matches"""
        if not matches:
            self.console.print("[yellow]No automatic matches to review.[/yellow]")
            return

        self.console.print(f"\n[bold]Total automatic matches: {len(matches)}[/bold]")
        
        while True:
            search_term = Prompt.ask(
                "\nEnter artist name to review (or 'exit' to return)",
                default="exit"
            )
            
            if search_term.lower() == 'exit':
                break
                
            # Find matching artists
            found_matches = [
                m for m in matches 
                if search_term.lower() in m.plex_artist.title.lower()
            ]
            
            if found_matches:
                for match in found_matches:
                    self._display_match_details(match)
                    if Confirm.ask("Would you like to review this match?"):
                        self._review_single_automatic_match(match)
            else:
                self.console.print("[yellow]No matching artists found.[/yellow]")

    def _review_no_matches(self, artists: List[UnmatchedArtist]):
        """Review artists with no matches"""
        if not artists:
            self.console.print("[yellow]No artists without matches to review.[/yellow]")
            return

        self.console.print(f"\n[bold]Total artists without matches: {len(artists)}[/bold]")
        
        while True:
            search_term = Prompt.ask(
                "\nEnter artist name to review (or 'exit' to return)",
                default="exit"
            )
            
            if search_term.lower() == 'exit':
                break
                
            # Find matching artists
            found_artists = [
                a for a in artists 
                if search_term.lower() in a.title.lower()
            ]
            
            if found_artists:
                for artist in found_artists:
                    self._display_artist_details(artist)
                    if Confirm.ask("Would you like to search for this artist?"):
                        self._manual_search(artist)
            else:
                self.console.print("[yellow]No matching artists found.[/yellow]")

    def _display_match_details(self, match: MatchResult):
        """Display detailed information about a match"""
        try:
            # Create basic table
            table = Table(title="Match Details")
            table.add_column("Field")
            table.add_column("Value")
            
            # Add basic info
            table.add_row("Plex Artist", str(match.plex_artist.title))
            
            if match.spotify_match:
                # Add Spotify match details
                table.add_row("Spotify Match", str(match.spotify_match.name))
                table.add_row("Confidence", "{:.2%}".format(match.confidence))
                table.add_row("Popularity", str(match.spotify_match.popularity) + "/100")
                
                # Add genres if available
                genres = ", ".join(match.spotify_match.genres[:3]) if match.spotify_match.genres else "None"
                table.add_row("Genres", genres)
                
                # Add followers
                followers = "{:,}".format(match.spotify_match.followers) if match.spotify_match.followers else "0"
                table.add_row("Followers", followers)
                
                # Add URL
                url = str(match.spotify_match.spotify_url) if match.spotify_match.spotify_url else "N/A"
                table.add_row("Spotify URL", url)
            
            self.console.print(table)
            
            # Display alternative matches if available
            if match.alternative_matches:
                alt_table = Table(title="Alternative Matches")
                alt_table.add_column("Option")
                alt_table.add_column("Artist")
                alt_table.add_column("Popularity")
                
                for i, alt in enumerate(match.alternative_matches, 1):
                    alt_table.add_row(
                        str(i),
                        str(alt.name),
                        str(alt.popularity) + "/100"
                    )
                
                self.console.print("\nAlternative Matches:")
                self.console.print(alt_table)
                
        except Exception as e:
            self.logger.error(f"Error displaying match details: {str(e)}")
            self.console.print("[red]Error displaying match details[/red]")

    def _spotify_artist_to_dict(self, artist: SpotifyArtistInfo) -> dict:
        """Convert SpotifyArtistInfo object to a dictionary"""
        if not artist:
            return None
        return {
            'id': artist.id,
            'name': artist.name,
            'genres': artist.genres,
            'popularity': artist.popularity,
            'followers': artist.followers,
            'spotify_url': artist.spotify_url,
            'images': artist.images
        }

    def _save_review_progress(self):
        """Save current review progress"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"review_decisions_{timestamp}.json"
        
        if not os.path.exists("results/reviews"):
            os.makedirs("results/reviews")
            
        filepath = os.path.join("results/reviews", filename)
        
        # Convert decisions for JSON serialization
        serializable_decisions = {}
        for key, decision in self.decisions.items():
            decision_copy = decision.copy()
            if 'spotify_data' in decision_copy:
                decision_copy['spotify_data'] = self._spotify_artist_to_dict(decision_copy['spotify_data'])
            serializable_decisions[key] = decision_copy
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(serializable_decisions, f, indent=2)
            
        self.console.print(f"[green]Review progress saved to: {filepath}[/green]")

    def _confirm_exit(self) -> bool:
        """Confirm exit from review session"""
        if self.decisions:
            if not Confirm.ask("Save progress before exiting?"):
                return True
            self._save_review_progress()
        return True

    def _accept_match(self, match: MatchResult):
        """Accept the primary match for an artist"""
        decision = {
            'action': 'accept_primary',
            'plex_artist': match.plex_artist.title,
            'spotify_id': match.spotify_match.id,
            'spotify_name': match.spotify_match.name,
            'confidence': match.confidence,
            'spotify_data': match.spotify_match  
        }
        self._add_decision(match.plex_artist.rating_key, decision)

    def _choose_alternative(self, match: MatchResult):
        """Choose an alternative match for an artist"""
        if not match.alternative_matches:
            self.console.print("[yellow]No alternative matches available.[/yellow]")
            return

        choice = Prompt.ask(
            "Select alternative match number",
            choices=[str(i) for i in range(1, len(match.alternative_matches) + 1)]
        )
        
        selected = match.alternative_matches[int(choice) - 1]
        decision = {
            'action': 'accept_alternative',
            'plex_artist': match.plex_artist.title,
            'spotify_id': selected.id,
            'spotify_name': selected.name,
            'original_confidence': match.confidence,
            'spotify_data': selected  
        }
        self._add_decision(match.plex_artist.rating_key, decision)

    def _mark_no_match(self, match: MatchResult):
        """Mark an artist as having no match"""
        decision = {
            'action': 'no_match',
            'plex_artist': match.plex_artist.title,
            'reason': 'manual_rejection'
        }
        self._add_decision(match.plex_artist.rating_key, decision)

    def _review_single_match(self, match: MatchResult):
        """Review a single match from a batch"""
        self._display_match_details(match)
        self._review_single_automatic_match(match)

    def _batch_review_matches(self, matches: List[MatchResult], batch_size: int = 5):
        """Review multiple matches at once"""
        if not matches:
            return
            
        start_idx = 0
        while start_idx < len(matches):
            batch = matches[start_idx:start_idx + batch_size]
            
            # Display batch summary
            self.console.print("\n[bold]Batch Review[/bold]")
            summary_table = Table(title=f"Reviewing {len(batch)} of {len(matches)} matches")
            summary_table.add_column("Index")
            summary_table.add_column("Plex Artist")
            summary_table.add_column("Spotify Match")
            summary_table.add_column("Confidence")
            
            for i, match in enumerate(batch, start_idx + 1):
                summary_table.add_row(
                    str(i),
                    match.plex_artist.title,
                    match.spotify_match.name if match.spotify_match else "No match",
                    f"{match.confidence:.2%}" if match.spotify_match else "N/A"
                )
                
            self.console.print(summary_table)
            
            # Batch actions
            options = {
                "1": "Accept all matches",
                "2": "Review individually",
                "3": "Skip batch",
                "4": "Exit batch review"
            }
            
            self._display_options(options)
            choice = Prompt.ask("Select action", choices=list(options.keys()))
            
            if choice == "1":
                for match in batch:
                    if match.spotify_match:
                        self._accept_match(match)
            elif choice == "2":
                for match in batch:
                    self._review_single_match(match)
            elif choice == "3":
                pass
            elif choice == "4":
                break
                
            start_idx += batch_size

    def _track_review_stats(self):
        """Track and display review statistics"""
        stats = {
            'total_reviewed': len(self.decisions),
            'accepted_primary': len([d for d in self.decisions.values() if d['action'] == 'accept_primary']),
            'accepted_alternative': len([d for d in self.decisions.values() if d['action'] == 'accept_alternative']),
            'manual_matches': len([d for d in self.decisions.values() if d['action'] == 'manual_match']),
            'no_matches': len([d for d in self.decisions.values() if d['action'] == 'no_match'])
        }
        
        table = Table(title="Review Statistics")
        table.add_column("Metric")
        table.add_column("Count")
        table.add_column("Percentage")
        
        for key, value in stats.items():
            percentage = (value / stats['total_reviewed'] * 100) if stats['total_reviewed'] > 0 else 0
            table.add_row(
                key.replace('_', ' ').title(),
                str(value),
                f"{percentage:.1f}%"
            )
            
        self.console.print("\n")
        self.console.print(table)

    def _dict_to_spotify_artist(self, data: dict) -> Optional[SpotifyArtistInfo]:
        """Convert dictionary back to SpotifyArtistInfo object"""
        if not data:
            return None
        return SpotifyArtistInfo(
            id=data['id'],
            name=data['name'],
            genres=data['genres'],
            popularity=data['popularity'],
            followers=data['followers'],
            spotify_url=data['spotify_url'],
            images=data['images']
        )

    def load_previous_session(self) -> Optional[Dict[str, Dict]]:
        """Load a previous review session"""
        try:
            reviews_dir = "results/reviews"
            if not os.path.exists(reviews_dir):
                return None
                
            # Get list of review files
            review_files = sorted([f for f in os.listdir(reviews_dir) if f.endswith('.json')], reverse=True)
            
            if not review_files:
                return None
                
            # Show available sessions
            self.console.print("\n[bold blue]Available Review Sessions:[/bold blue]")
            table = Table(show_header=True)
            table.add_column("Option")
            table.add_column("Filename")
            table.add_column("Date")
            
            for i, filename in enumerate(review_files[:5], 1):  # Show last 5 sessions
                date_str = filename.split('_')[2].split('.')[0]  # Extract date from filename
                table.add_row(str(i), filename, date_str)
                
            self.console.print(table)
            
            choice = Prompt.ask(
                "Select session to load (or '0' to start new)",
                choices=['0'] + [str(i) for i in range(1, len(review_files[:5]) + 1)]
            )
            
            if choice == '0':
                return None
                
            # Load selected session
            filepath = os.path.join(reviews_dir, review_files[int(choice) - 1])
            with open(filepath, 'r', encoding='utf-8') as f:
                loaded_decisions = json.load(f)
            
            # Reconstruct SpotifyArtistInfo objects
            reconstructed_decisions = {}
            for key, decision in loaded_decisions.items():
                decision_copy = decision.copy()
                if 'spotify_data' in decision_copy:
                    decision_copy['spotify_data'] = self._dict_to_spotify_artist(decision_copy['spotify_data'])
                reconstructed_decisions[key] = decision_copy
            
            return reconstructed_decisions
                
        except Exception as e:
            self.logger.error(f"Error loading previous session: {str(e)}")
            return None

    def _manual_search(self, artist: UnmatchedArtist):
        """Handle manual search for an artist"""
        while True:
            try:
                search_term = Prompt.ask("\nEnter search term (or 'exit' to cancel)")
                
                if search_term.lower() == 'exit':
                    break
                
                # Try exact match first
                exact_results = self.spotify.search_artist(search_term, exact_match=True)
                if exact_results:
                    self.console.print("[green]Found exact match:[/green]")
                    self._display_search_results(exact_results)
                    if Confirm.ask("Would you like to use this exact match?"):
                        selected = exact_results[0]
                        decision = {
                            'action': 'manual_match',
                            'plex_artist': artist.title,
                            'spotify_id': selected.id,
                            'spotify_name': selected.name,
                            'search_term': search_term,
                            'match_type': 'exact',
                            'spotify_data': selected  # Add the full SpotifyArtistInfo object
                        }
                        self._add_decision(artist.rating_key, decision)
                        break
                
                # Regular search
                regular_results = self.spotify.search_artist(search_term, exact_match=False)
                
                if regular_results:
                    self.console.print("\n[cyan]Search results:[/cyan]")
                    self._display_search_results(regular_results)
                    
                    # Add "No Match" option to choices
                    choices = ['0'] + [str(i) for i in range(1, len(regular_results) + 1)] + ['n']
                    choice = Prompt.ask(
                        "Select match number (0 to search again, 'n' for No Match on Spotify)",
                        choices=choices
                    )
                    
                    if choice == '0':
                        continue
                    elif choice == 'n':
                        if Confirm.ask("Mark this artist as not available on Spotify?"):
                            decision = {
                                'action': 'no_match',
                                'plex_artist': artist.title,
                                'reason': 'not_on_spotify',
                                'search_term': search_term
                            }
                            self._add_decision(artist.rating_key, decision)
                            break
                        continue
                        
                    selected = regular_results[int(choice) - 1]
                    decision = {
                        'action': 'manual_match',
                        'plex_artist': artist.title,
                        'spotify_id': selected.id,
                        'spotify_name': selected.name,
                        'search_term': search_term,
                        'match_type': 'manual',
                        'spotify_data': selected  # Add the full SpotifyArtistInfo object
                    }
                    self._add_decision(artist.rating_key, decision)
                    break
                else:
                    self.console.print("[yellow]No results found.[/yellow]")
                    if Confirm.ask("Would you like to mark this artist as not available on Spotify?"):
                        decision = {
                            'action': 'no_match',
                            'plex_artist': artist.title,
                            'reason': 'not_on_spotify',
                            'search_term': search_term
                        }
                        self._add_decision(artist.rating_key, decision)
                        break
                    
            except Exception as e:
                self.logger.error(f"Error during manual search: {str(e)}")
                self.console.print("[red]Error during search. Please try again.[/red]")
                if not Confirm.ask("Would you like to try another search?"):
                    break

    def _display_search_results(self, results: List[SpotifyArtistInfo]):
        """Display search results in a formatted table"""
        try:
            table = Table(title="Search Results")
            table.add_column("Option")
            table.add_column("Artist")
            table.add_column("Popularity")
            table.add_column("Genres")
            
            for i, result in enumerate(results, 1):
                # Convert all values to strings explicitly
                option = str(i)
                artist_name = str(result.name)
                popularity = f"{result.popularity}/100"
                genres = ", ".join(result.genres[:2]) if result.genres else "None"
                
                table.add_row(option, artist_name, popularity, genres)
                
            self.console.print(table)
            
        except Exception as e:
            self.logger.error(f"Error displaying search results: {str(e)}")
            self.console.print("[red]Error displaying search results[/red]")