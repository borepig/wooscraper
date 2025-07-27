#!/usr/bin/env python3
"""
Test script for NFO file creation from metadata
"""

import tempfile
from pathlib import Path
from scraper_engine import JAVScraperEngine

def test_nfo_creation_from_metadata():
    """Test creating NFO file directly from metadata structure."""
    
    # Sample metadata with detailed_metadata section
    test_metadata = {
        "jav_code": "DASS-695",
        "sources": {
            "javguru": {
                "title": "[DASS-695] Everyone Who Has A Grudge Against This Arrogant Woman, Gather Here! A Super Creepy Guy's Persistent Torture Leads To A Mental Breakdown! Creampie Urinal Birth Sex! Nia",
                "cover_url": "https://cdn.javsts.com/wp-content/uploads/2025/07/dass695pl-550x374.jpg",
                "detail_url": "https://jav.guru/700867/dass-695-everyone-who-has-a-grudge-against-this-arrogant-woman-gather-here-a-super-creepy-guys-persistent-trture-leads-to-a-mental-breakdown-creampie-urinal-birth-sex/"
            }
        },
        "best_title": "[DASS-695] Everyone Who Has A Grudge Against This Arrogant Woman, Gather Here! A Super Creepy Guy's Persistent Torture Leads To A Mental Breakdown! Creampie Urinal Birth Sex! Nia",
        "best_cover": "https://cdn.javsts.com/wp-content/uploads/2025/07/dass695pl-550x374.jpg",
        "detailed_metadata": {
            "code": "DASS-695",
            "full_title": "[DASS-695] Everyone Who Has A Grudge Against This Arrogant Woman, Gather Here! A Super Creepy Guy's Persistent Torture Leads To A Mental Breakdown! Creampie Urinal Birth Sex! Nia",
            "plot": "A person finally lands a job at a new company, but quickly becomes suspicious of a female coworker who seems favored, possibly the boss mistress. One day, they begrudged employees catch her secretly stealing money from the company safe and decide to use this as leverage to get revenge. They rally everyone who were mistreated by her, seeking payback.",
            "release_date": "2025-07-08",
            "director": "Koharu Hiyori",
            "studio": "Das !",
            "label": "DASS",
            "category": "3P, 4P, abuse, Creampie, Urinal, Birth Sex",
            "actor": "Goro, Miuraya Sukeroku, Toy Boy Aizawa",
            "actress": "Itou Meru",
            "tags": "3P, 4P, abuse, Creampie, Urinal, Birth Sex, Mental Breakdown, Revenge, Office, Coworker",
            "fanart_url": "https://cdn.javsts.com/wp-content/uploads/2025/07/dass695pl.jpg",
            "large_cover_url": "https://cdn.javsts.com/wp-content/uploads/2025/07/dass695pl.jpg"
        }
    }
    
    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create NFO file directly from metadata
        nfo_path = temp_path / "movie.nfo"
        
        # Initialize scraper engine
        engine = JAVScraperEngine()
        
        # Create NFO file from metadata
        success = engine.create_nfo_file(test_metadata, str(nfo_path))
        
        if success:
            print("✅ NFO file created successfully!")
            print(f"📁 Location: {nfo_path}")
            
            # Read and display the NFO content
            with open(nfo_path, 'r', encoding='utf-8') as f:
                nfo_content = f.read()
            
            print("\n📄 NFO Content:")
            print("=" * 50)
            print(nfo_content)
            print("=" * 50)
        else:
            print("❌ Failed to create NFO file")

if __name__ == "__main__":
    test_nfo_creation_from_metadata() 