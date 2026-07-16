"""
Lightweight LLM API wrappers to avoid heavy langchain dependencies.
"""

import logging
import google.generativeai as genai
from config import settings

logger = logging.getLogger(__name__)


class SimpleLLM:
    """Unified interface for Google models."""
    
    def __init__(self, provider: str, model: str, temperature: float = 0.0):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        
        if provider == "google":
            genai.configure(api_key=settings.GOOGLE_API_KEY)
        else:
            logger.warning(f"Provider {provider} not supported, falling back to Google")
            genai.configure(api_key=settings.GOOGLE_API_KEY)
    
    async def ainvoke(self, prompt: str) -> dict:
        """Async invoke to get completion."""
        try:
            response = genai.GenerativeModel(self.model).generate_content(prompt)
            return {"content": response.text}
        except Exception as e:
            logger.error(f"Error calling GenerativeModel: {e}")
            raise


async def call_llm(provider: str, model: str, prompt: str, temperature: float = 0.0) -> str:
    """Simple async LLM call using Google Generative AI."""
    llm = SimpleLLM(provider, model, temperature)
    response = await llm.ainvoke(prompt)
    return response["content"]
