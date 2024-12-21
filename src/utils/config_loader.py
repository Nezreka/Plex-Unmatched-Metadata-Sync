# src/utils/config_loader.py

import json
import os
from typing import Dict, Any

class ConfigError(Exception):
    """Custom exception for configuration errors"""
    pass

def load_config() -> Dict[str, Any]:
    """
    Load and validate the configuration file.
    Returns: Dict containing configuration
    Raises: ConfigError if configuration is invalid or missing
    """
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                              'config', 'config.json')
    
    # Check if config file exists
    if not os.path.exists(config_path):
        raise ConfigError(
            "\nConfiguration file not found!"
            "\nPlease ensure 'config.json' exists in the 'config' directory."
            "\nPath should be: " + config_path
        )

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        raise ConfigError(
            "\nInvalid JSON in configuration file!"
            "\nPlease check the syntax of your config.json file."
        )

    # Validate required fields
    required_configs = {
        'plex': ['base_url', 'token', 'library_name'],
        'spotify': ['client_id', 'client_secret'],
        'anthropic': ['api_key'],
        'matching': ['similarity_threshold', 'use_claude_fallback']
    }

    for section, fields in required_configs.items():
        if section not in config:
            raise ConfigError(f"\nMissing '{section}' section in config.json")
        
        for field in fields:
            if field not in config[section]:
                raise ConfigError(f"\nMissing '{field}' in {section} configuration")
            
            # Check for empty or default values
            if config[section][field] in ['your-plex-token', 'your-spotify-client-id', 
                                        'your-spotify-client-secret', 'your-claude-api-key', '']:
                raise ConfigError(
                    f"\nPlease update the {section}.{field} in config.json with your actual credentials."
                    f"\nCurrent value appears to be a placeholder or empty."
                )

    return config