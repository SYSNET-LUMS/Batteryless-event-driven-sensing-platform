from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

class BaseRepository(ABC):
    """Base repository interface"""
    
    @abstractmethod
    def get_all(self) -> List[Any]:
        pass
    
    @abstractmethod
    def get_by_id(self, item_id: str) -> Optional[Any]:
        pass
    
    @abstractmethod
    def add(self, item: Any) -> Any:
        pass
    
    @abstractmethod
    def update(self, item_id: str, data: Dict) -> Optional[Any]:
        pass
    
    @abstractmethod
    def delete(self, item_id: str) -> bool:
        pass
    
    @abstractmethod
    def clear(self) -> None:
        pass