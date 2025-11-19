"""
Enhanced Llama model wrapper for agent operations
"""
import sys
import os
import json
import re

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ChunkAndMap import LlamaModel


class AgentLlamaModel:
    """
    Wrapper around LlamaModel with additional functionality for agents
    """
    
    def __init__(self, model_name="meta-llama/Llama-3.2-1B"):
        self.llm = LlamaModel(model_name)
    
    def generate(self, prompt: str, max_new_tokens: int = 500, temperature: float = 0.7) -> str:
        """
        Generate text using the underlying Llama model
        """
        return self.llm.generate(prompt, max_new_tokens=max_new_tokens, temperature=temperature)
    
    def generate_json(self, prompt: str, max_new_tokens: int = 500) -> dict:
        """
        Generate JSON response and parse it
        Uses lower temperature for more consistent formatting
        """
        response = self.llm.generate(prompt, max_new_tokens=max_new_tokens, temperature=0.3)
        
        # Try to extract JSON from response
        try:
            # Look for JSON array or object
            json_match = re.search(r'(\[.*\]|\{.*\})', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json.loads(json_str)
            else:
                # Try parsing the whole response
                return json.loads(response)
        except json.JSONDecodeError as e:
            print(f"failed json parse lol {e}")
            print(f"Response was: {response[:200]}...")
            return {}
    
    def extract_number(self, prompt: str) -> int:
        """
        Generate response and extract the first number
        """
        response = self.llm.generate(prompt, max_new_tokens=50, temperature=0.3)
        
        # Extract first number from response
        match = re.search(r'\d+', response)
        if match:
            return int(match.group())
        
        return 0
    
    def extract_text(self, prompt: str, max_new_tokens: int = 100) -> str:
        """
        Generate response and clean it up (remove extra whitespace)
        """
        response = self.llm.generate(prompt, max_new_tokens=max_new_tokens, temperature=0.5)
        return response.strip()


# Singleton instance to avoid reloading model
_agent_llm_instance = None


def get_llm() -> AgentLlamaModel:
    """
    Get or create singleton LLM instance
    """
    global _agent_llm_instance
    
    if _agent_llm_instance is None:
        _agent_llm_instance = AgentLlamaModel()
    
    return _agent_llm_instance
