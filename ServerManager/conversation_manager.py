"""
Conversation history management for MCP server interactions.
"""
from typing import Dict, List, Tuple, Optional


class ConversationManager:
    """Manages conversation history for MCP server interactions."""
    
    def __init__(self, max_history_length: int = 20):
        """
        Initialize conversation manager.
        
        Args:
            max_history_length: Maximum number of messages to keep in history
        """
        self.max_history_length = max_history_length
        # Thread-based conversation histories: key is (channel_id, thread_ts)
        self.conversation_histories: Dict[Tuple[Optional[str], Optional[str]], List[Dict[str, str]]] = {}
    
    def add_message(self, role: str, content: str, channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> None:
        """
        Add a message to conversation history.
        
        Args:
            role: The role of the message sender (user, assistant, system)
            content: The message content
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
        """
        key = (channel_id, thread_ts)
        if key not in self.conversation_histories:
            self.conversation_histories[key] = []
        
        self.conversation_histories[key].append({"role": role, "content": content})
        
        # Keep only the most recent messages
        if len(self.conversation_histories[key]) > self.max_history_length:
            self.conversation_histories[key] = self.conversation_histories[key][-self.max_history_length:]
    
    def get_history_text(self, channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> str:
        """
        Get conversation history as formatted text.
        
        Args:
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
            
        Returns:
            Formatted conversation history string
        """
        key = (channel_id, thread_ts)
        history = self.conversation_histories.get(key, [])
        
        if not history:
            return "No previous conversation history."
        
        history_lines = [f"{entry['role'].capitalize()}: {entry['content']}" for entry in history]
        return "\n".join(history_lines)
    
    def get_history_messages(self, channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Get conversation history as list of message dictionaries.
        
        Args:
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
            
        Returns:
            List of message dictionaries with 'role' and 'content' keys
        """
        key = (channel_id, thread_ts)
        return self.conversation_histories.get(key, []).copy()
    
    def clear_history(self, channel_id: Optional[str] = None, thread_ts: Optional[str] = None) -> None:
        """
        Clear conversation history for a specific thread.
        
        Args:
            channel_id: Channel identifier for thread-based conversations
            thread_ts: Thread timestamp for thread-based conversations
        """
        key = (channel_id, thread_ts)
        if key in self.conversation_histories:
            del self.conversation_histories[key]
    
    def clear_all_histories(self) -> None:
        """Clear all conversation histories."""
        self.conversation_histories.clear()
    
    def get_thread_count(self) -> int:
        """Get the number of active conversation threads."""
        return len(self.conversation_histories) 