"""
Lightweight LLM API wrappers to avoid heavy langchain dependencies.
"""

import logging
import google.generativeai as genai
import openai
from config import settings

logger = logging.getLogger(__name__)


class SimpleLLM:
    """Unified interface for Google and OpenAI models."""
    
    def __init__(self, provider: str, model: str, temperature: float = 0.0):
        self.provider = provider
        self.model = model
        self.temperature = temperature
        
        if provider == "google":
            genai.configure(api_key=settings.GOOGLE_API_KEY)
        else:
            openai.api_key = settings.OPENAI_API_KEY
    
    async def ainvoke(self, prompt: str) -> dict:
        """Async invoke to get completion."""
        if self.provider == "google":
            response = genai.GenerativeModel(self.model).generate_content(prompt)
            return {"content": response.text}
        else:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            )
            return {"content": response.choices[0].message.content}


async def call_llm(provider: str, model: str, prompt: str, temperature: float = 0.0) -> str:
    """Simple async LLM call."""
    llm = SimpleLLM(provider, model, temperature)
    response = await llm.ainvoke(prompt)
    return response["content"]
