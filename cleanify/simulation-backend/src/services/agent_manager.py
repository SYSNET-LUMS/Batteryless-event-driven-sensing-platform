"""
Agent Manager - Singleton pattern to ensure only one WasteCollectionAgent instance exists
This prevents clustering cache loss during high-speed simulation by maintaining the same agent instance
"""

from typing import Optional
from services.agent_service import WasteCollectionAgent

class AgentManager:
    """Singleton manager for WasteCollectionAgent instances"""
    
    _instance: Optional[WasteCollectionAgent] = None
    _initialized: bool = False
    
    @classmethod
    def get_agent(cls) -> WasteCollectionAgent:
        """Get the singleton agent instance, creating it if necessary"""
        if cls._instance is None:
            print(f"🏗️ AgentManager: Creating new singleton WasteCollectionAgent")
            cls._instance = WasteCollectionAgent()
            cls._initialized = True
        else:
            print(f"✅ AgentManager: Using existing singleton agent - agent_id={id(cls._instance)}")
        
        return cls._instance
    
    @classmethod
    def reset_agent(cls) -> None:
        """Reset the agent instance (for testing purposes only)"""
        print(f"🔄 AgentManager: Resetting singleton agent")
        cls._instance = None
        cls._initialized = False
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the agent has been initialized"""
        return cls._initialized and cls._instance is not None
    
    @classmethod
    def get_agent_id(cls) -> Optional[str]:
        """Get the current agent ID for debugging"""
        if cls._instance is not None:
            return str(id(cls._instance))
        return None

# Convenience function for easy import
def get_agent() -> WasteCollectionAgent:
    """Get the singleton agent instance"""
    return AgentManager.get_agent()