# src/utils/results_manager.py

import json
import os
from datetime import datetime
from typing import Dict, List
from dataclasses import asdict
import pickle

class ResultsManager:
    def __init__(self, base_dir: str = "results"):
        """Initialize results manager with base directory"""
        self.base_dir = base_dir
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist"""
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "json"), exist_ok=True)
        os.makedirs(os.path.join(self.base_dir, "pickle"), exist_ok=True)

    def save_results(self, results: Dict[str, List], session_id: str = None) -> str:
        """
        Save matching results in both JSON and pickle format
        
        Args:
            results: Dictionary containing matching results
            session_id: Optional session identifier
            
        Returns:
            str: Session ID of saved results
        """
        if not session_id:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save as pickle (preserves all object information)
        pickle_path = os.path.join(self.base_dir, "pickle", f"match_results_{session_id}.pkl")
        with open(pickle_path, 'wb') as f:
            pickle.dump(results, f)

        # Save as JSON (human-readable)
        json_results = self._convert_to_json_serializable(results)
        json_path = os.path.join(self.base_dir, "json", f"match_results_{session_id}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_results, f, indent=2, ensure_ascii=False)

        return session_id

    def load_results(self, session_id: str) -> Dict[str, List]:
        """
        Load results from a previous session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dict containing matching results
        """
        pickle_path = os.path.join(self.base_dir, "pickle", f"match_results_{session_id}.pkl")
        with open(pickle_path, 'rb') as f:
            return pickle.load(f)

    def _convert_to_json_serializable(self, results: Dict) -> Dict:
        """Convert results to JSON-serializable format"""
        json_results = {
            'matched': [],
            'needs_review': [],
            'no_matches': [],
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_processed': sum(len(v) for v in results.values()),
                'statistics': {
                    'automatic_matches': len(results['matched']),
                    'needs_review': len(results['needs_review']),
                    'no_matches': len(results['no_matches'])
                }
            }
        }

        # Convert matched and needs_review results
        for category in ['matched', 'needs_review']:
            for match_result in results[category]:
                result_dict = {
                    'plex_artist': {
                        'title': match_result.plex_artist.title,
                        'rating_key': match_result.plex_artist.rating_key
                    },
                    'confidence': match_result.confidence,
                    'spotify_match': None,
                    'alternative_matches': []
                }
                
                if match_result.spotify_match:
                    result_dict['spotify_match'] = {
                        'name': match_result.spotify_match.name,
                        'id': match_result.spotify_match.id,
                        'genres': match_result.spotify_match.genres,
                        'popularity': match_result.spotify_match.popularity,
                        'followers': match_result.spotify_match.followers,
                        'spotify_url': match_result.spotify_match.spotify_url
                    }
                
                for alt_match in match_result.alternative_matches:
                    result_dict['alternative_matches'].append({
                        'name': alt_match.name,
                        'id': alt_match.id,
                        'popularity': alt_match.popularity,
                        'spotify_url': alt_match.spotify_url
                    })
                
                json_results[category].append(result_dict)

        # Convert no_matches results
        for artist in results['no_matches']:
            json_results['no_matches'].append({
                'title': artist.title,
                'rating_key': artist.rating_key
            })

        return json_results

    def list_saved_sessions(self) -> List[Dict[str, str]]:
        """
        List all saved sessions with their timestamps
        
        Returns:
            List of dictionaries containing session info
        """
        sessions = []
        json_dir = os.path.join(self.base_dir, "json")
        
        for filename in os.listdir(json_dir):
            if filename.startswith("match_results_") and filename.endswith(".json"):
                session_id = filename[13:-5]  # Remove prefix and extension
                file_path = os.path.join(json_dir, filename)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                sessions.append({
                    'session_id': session_id,
                    'timestamp': data['metadata']['timestamp'],
                    'total_processed': data['metadata']['total_processed'],
                    'automatic_matches': data['metadata']['statistics']['automatic_matches'],
                    'needs_review': data['metadata']['statistics']['needs_review'],
                    'no_matches': data['metadata']['statistics']['no_matches']
                })
                
        return sorted(sessions, key=lambda x: x['timestamp'], reverse=True)