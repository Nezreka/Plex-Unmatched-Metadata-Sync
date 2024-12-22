# src/matching/matcher.py

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from ..plex.connector import UnmatchedArtist
from ..spotify.connector import SpotifyArtistInfo
import logging
from tqdm import tqdm
import time

@dataclass
class MatchResult:
    """Data class to store matching results"""
    plex_artist: UnmatchedArtist
    spotify_match: Optional[SpotifyArtistInfo]
    confidence: float
    needs_review: bool
    alternative_matches: List[SpotifyArtistInfo]
    match_details: Dict[str, Any]

    def __post_init__(self):
        """Initialize default values for optional fields"""
        if self.alternative_matches is None:
            self.alternative_matches = []
        if self.match_details is None:
            self.match_details = {}

class ArtistMatcher:
    def __init__(self, plex_connector, spotify_connector, config: dict, logger: logging.Logger):
        """
        Initialize the matching system
        
        Args:
            plex_connector: Initialized PlexConnector instance
            spotify_connector: Initialized SpotifyConnector instance
            config: Matching configuration
            logger: Logger instance
        """
        self.plex = plex_connector
        self.spotify = spotify_connector
        self.config = config
        self.logger = logger
        
        # Confidence thresholds
        self.auto_match_threshold = config.get('auto_match_threshold', 0.95)
        self.review_threshold = config.get('review_threshold', 0.80)
        self.min_confidence = self.review_threshold
        
        # Processing settings
        self.timeout_threshold = config.get('timeout_threshold', 25)
        self.max_alternatives = config.get('max_alternatives', 5)
        
        # Results storage
        self.matched: List[MatchResult] = []
        self.needs_review: List[MatchResult] = []
        self.no_matches: List[UnmatchedArtist] = []

    def process_unmatched_artists(self, artists: List[UnmatchedArtist]) -> Dict[str, List]:
        """Process a list of unmatched artists and attempt to find matches"""
        results = {
            'matched': [],
            'needs_review': [],
            'no_matches': []
        }
        
        total = len(artists)
        self.logger.info("Starting artist matching process...")
        
        with tqdm(total=total, desc="Matching artists") as pbar:
            for artist in artists:
                try:
                    start_time = time.time()
                    match_result = self._process_single_artist(artist)
                    processing_time = time.time() - start_time
                    
                    # Check for timeout
                    if processing_time > self.timeout_threshold:
                        self.logger.warning(
                            f"Matching timed out for artist: {artist.title} "
                            f"(took {processing_time:.1f}s, threshold: {self.timeout_threshold}s)"
                        )
                        # Still try to use the result if we got one
                        if match_result and match_result.spotify_match:
                            self.logger.info(f"Got result despite timeout for: {artist.title}")
                            if match_result.confidence >= self.min_confidence:
                                results['matched'].append(match_result)
                            else:
                                results['needs_review'].append(match_result)
                        else:
                            results['no_matches'].append(artist)
                        continue
                    
                    if match_result.spotify_match:
                        if match_result.confidence >= self.min_confidence:
                            results['matched'].append(match_result)
                        else:
                            results['needs_review'].append(match_result)
                    else:
                        results['no_matches'].append(artist)
                    
                    # Add a small delay between requests to avoid rate limiting
                    time.sleep(0.3)
                    
                except Exception as e:
                    self.logger.error(f"Error processing artist {artist.title}: {str(e)}")
                    results['no_matches'].append(artist)
                finally:
                    pbar.update(1)
        
        self._log_results_summary(results, total)
        return results

    def _process_single_artist(self, artist: UnmatchedArtist) -> MatchResult:
        """Process a single artist and find potential matches"""
        # Try exact match first
        exact_results = self.spotify.search_artist(artist.title, exact_match=True)
        
        if exact_results:
            # Use the exact match with high confidence
            return MatchResult(
                plex_artist=artist,
                spotify_match=exact_results[0],
                confidence=1.0,
                needs_review=False,
                alternative_matches=exact_results[1:self.max_alternatives] if len(exact_results) > 1 else [],
                match_details={
                    'match_type': 'exact',
                    **self._get_match_details(artist, exact_results[0], 1.0)
                }
            )
        
        # If no exact match, try regular search
        search_results = self.spotify.search_artist(artist.title)
        
        if not search_results:
            return MatchResult(
                plex_artist=artist,
                spotify_match=None,
                confidence=0.0,
                needs_review=False,
                alternative_matches=[],
                match_details={'reason': 'no_matches_found'}
            )
        
        # Calculate match scores for all results
        scored_matches = []
        for result in search_results:
            confidence = self._calculate_match_confidence(artist, result)
            scored_matches.append((result, confidence))
        
        # Sort by confidence score
        scored_matches.sort(key=lambda x: x[1], reverse=True)
        
        # Get best match and alternatives
        best_match = scored_matches[0]
        alternatives = [m[0] for m in scored_matches[1:self.max_alternatives]]
        
        return MatchResult(
            plex_artist=artist,
            spotify_match=best_match[0],
            confidence=best_match[1],
            needs_review=best_match[1] < self.auto_match_threshold,
            alternative_matches=alternatives,
            match_details={
                'match_type': 'fuzzy',
                **self._get_match_details(artist, best_match[0], best_match[1])
            }
        )

    def _calculate_match_confidence(self, plex_artist: UnmatchedArtist, 
                                  spotify_artist: SpotifyArtistInfo) -> float:
        """Calculate confidence score for a potential match"""
        base_similarity, is_exact = self.spotify._calculate_similarity_score(
            plex_artist.title, 
            spotify_artist.name
        )
        
        if is_exact:
            return 1.0
            
        confidence_factors = []
        
        # Popularity factor
        popularity_weight = 0.1
        popularity_factor = (spotify_artist.popularity / 100.0) * popularity_weight
        confidence_factors.append(popularity_factor)
        
        # Metadata completeness factor
        metadata_status = self.spotify.get_artist_metadata_status(spotify_artist)
        completeness = sum(1 for v in metadata_status.values() if v) / len(metadata_status)
        metadata_weight = 0.1
        metadata_factor = completeness * metadata_weight
        confidence_factors.append(metadata_factor)
        
        final_confidence = base_similarity + sum(confidence_factors)
        return min(max(final_confidence, 0.0), 1.0)

    def _get_match_details(self, plex_artist: UnmatchedArtist, 
                          spotify_artist: SpotifyArtistInfo, 
                          confidence: float) -> Dict:
        """Generate detailed information about the match"""
        return {
            'confidence': confidence,
            'name_comparison': {
                'plex_name': plex_artist.title,
                'spotify_name': spotify_artist.name,
                'normalized_plex': self.spotify._normalize_artist_name(plex_artist.title),
                'normalized_spotify': self.spotify._normalize_artist_name(spotify_artist.name)
            },
            'spotify_metadata': self.spotify.get_artist_metadata_status(spotify_artist),
            'match_level': 'automatic' if confidence >= self.auto_match_threshold else 'review'
        }

    def _log_results_summary(self, results: Dict[str, List], total: int) -> None:
        """Log a summary of the matching results"""
        self.logger.info("=" * 50)
        self.logger.info(f"Total artists processed: {total}")
        self.logger.info(f"Automatic matches: {len(results['matched'])} ({(len(results['matched'])/total)*100:.1f}%)")
        self.logger.info(f"Needs review: {len(results['needs_review'])} ({(len(results['needs_review'])/total)*100:.1f}%)")
        self.logger.info(f"No matches found: {len(results['no_matches'])} ({(len(results['no_matches'])/total)*100:.1f}%)")

    def get_match_details_string(self, match_result: MatchResult) -> str:
        """Generate a human-readable string of match details"""
        if not match_result.spotify_match:
            return f"No match found for: {match_result.plex_artist.title}"
            
        details = []
        details.append(f"Plex Artist: {match_result.plex_artist.title}")
        details.append(f"Spotify Match: {match_result.spotify_match.name}")
        details.append(f"Confidence: {match_result.confidence:.2%}")
        details.append(f"Match Type: {match_result.match_details.get('match_type', 'unknown')}")
        details.append(f"Popularity: {match_result.spotify_match.popularity}/100")
        
        if match_result.spotify_match.genres:
            details.append(f"Genres: {', '.join(match_result.spotify_match.genres[:3])}")
            
        if match_result.alternative_matches:
            details.append("\nAlternative matches:")
            for i, alt in enumerate(match_result.alternative_matches, 1):
                details.append(f"  {i}. {alt.name} (Popularity: {alt.popularity}/100)")
                
        return "\n".join(details)