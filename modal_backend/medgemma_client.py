"""
MedGemma Client - HTTP client for vLLM OpenAI-compatible API.

Replaces direct model loading with HTTP calls to a vLLM server,
enabling scalable deployment on Modal.
"""
import httpx
import base64
import io
import logging
from PIL import Image
from typing import Optional, List, Union

logger = logging.getLogger(__name__)

MODEL_ID = "google/medgemma-1.5-4b-it"
DEFAULT_TIMEOUT = 120.0


class MedGemmaClient:
    """HTTP client for MedGemma via vLLM OpenAI-compatible API."""
    
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
        self.sync_client = httpx.Client(timeout=timeout)
    
    async def generate(
        self,
        prompt: str,
        max_new_tokens: int = 1024,
        system_prompt: Optional[str] = None,
        image: Optional[Image.Image] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate response from MedGemma via vLLM.
        
        Args:
            prompt: Text prompt for the model
            max_new_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            image: Optional PIL Image for multimodal analysis
            temperature: Sampling temperature
            
        Returns:
            Generated text response
        """
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        user_content: List[Union[str, dict]] = []
        
        if image is not None:
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}"
                }
            })
            logger.info(f"Image attached: {image.size[0]}x{image.size[1]}")
        
        user_content.append({
            "type": "text",
            "text": prompt
        })
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        try:
            response = await self.client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": max_new_tokens,
                    "temperature": temperature if temperature > 0 else 1.0,
                    "top_p": 0.9,
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"vLLM HTTP error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"vLLM request failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"vLLM connection error: {e}")
            raise RuntimeError(f"vLLM connection failed: {e}")
    
    def generate_sync(
        self,
        prompt: str,
        max_new_tokens: int = 1024,
        system_prompt: Optional[str] = None,
        image: Optional[Image.Image] = None,
        temperature: float = 0.7,
    ) -> str:
        """Synchronous generate for backwards compatibility."""
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        user_content: List[Union[str, dict]] = []
        
        if image is not None:
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            img_base64 = base64.b64encode(buffer.getvalue()).decode()
            
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}"
                }
            })
        
        user_content.append({
            "type": "text",
            "text": prompt
        })
        
        messages.append({
            "role": "user",
            "content": user_content
        })
        
        try:
            response = self.sync_client.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "model": MODEL_ID,
                    "messages": messages,
                    "max_tokens": max_new_tokens,
                    "temperature": temperature if temperature > 0 else 1.0,
                    "top_p": 0.9,
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
            
        except httpx.HTTPStatusError as e:
            logger.error(f"vLLM HTTP error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"vLLM request failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"vLLM connection error: {e}")
            raise RuntimeError(f"vLLM connection failed: {e}")
    
    async def health_check(self) -> bool:
        """Check if vLLM server is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except:
            return False
    
    async def close(self):
        """Close HTTP clients."""
        await self.client.aclose()
        self.sync_client.close()


_singleton_client: Optional[MedGemmaClient] = None


def get_client(base_url: str = "http://localhost:6501") -> MedGemmaClient:
    """Get or create the MedGemma client singleton."""
    global _singleton_client
    if _singleton_client is None:
        _singleton_client = MedGemmaClient(base_url)
    return _singleton_client
