import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

class FileService:
    """File management service for saving/loading system states"""
    
    def __init__(self, saves_dir: str = 'saved_systems'):
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(exist_ok=True)
    
    def save_system(self, system_state: Dict) -> Dict:
        """Save system state to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cleanify_system_{timestamp}.json"
        filepath = self.saves_dir / filename
        
        # Add metadata
        system_state['metadata'] = {
            'saved_at': datetime.now().isoformat(),
            'filename': filename,
            'version': '2.0-simplified'
        }
        
        # Save to file
        with open(filepath, 'w') as f:
            json.dump(system_state, f, indent=2)
        
        return {
            'status': 'success',
            'filename': filename,
            'filepath': str(filepath)
        }
    
    def load_system(self, filename: str) -> Optional[Dict]:
        """Load system state from file"""
        filepath = self.saves_dir / filename
        if not filepath.exists():
            return None
        
        with open(filepath, 'r') as f:
            system_state = json.load(f)
        
        return system_state
    
    def get_saved_files(self) -> List[Dict]:
        """Get list of saved files"""
        files = []
        
        for filepath in self.saves_dir.glob('*.json'):
            stat = filepath.stat()
            files.append({
                'name': filepath.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        return files