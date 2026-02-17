"""
MedGemma model loader and inference using vLLM for faster performance.
Compatible with AMD ROCm GPUs via WSL2.

This module provides the same API as medgemma.py but uses vLLM for 3x faster inference.
"""
from vllm import LLM, SamplingParams
from PIL import Image
from typing import Optional, List, Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

class MedGemmaModelVLLM:
    def __init__(self):
        self.llm = None
        self.model_id = "google/medgemma-1.5-4b-it"
        self.loaded = False
    
    def load(self, model_id: str = "google/medgemma-1.5-4b-it"):
        """Load MedGemma model using vLLM."""
        logger.info(f"Loading {model_id} with vLLM...")
        
        # Check for GPU
        import torch
        if not torch.cuda.is_available():
            logger.error("CUDA not available. vLLM requires GPU.")
            raise RuntimeError("GPU not available")
        
        logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        
        # vLLM configuration optimized for MedGemma 4B
        # Using tensor_parallel_size=1 for single GPU
        # Explicitly set device to 'cuda' (vLLM's internal name for GPU backends)
        # Setting enforce_eager=True is often required for ROCm/WSL2 stability
        self.llm = LLM(
            model=model_id,
            dtype="bfloat16",  # Use bfloat16 for better performance on AMD
            tensor_parallel_size=1,
            gpu_memory_utilization=0.8,  # Slightly lower to avoid OOM during loading
            max_model_len=4096,  # Maximum sequence length
            trust_remote_code=True,
            download_dir=os.path.expanduser("~/.cache/huggingface"),
            enforce_eager=True
        )
        
        self.loaded = True
        logger.info("Model loaded successfully with vLLM")
        return self
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 1024,
        system_prompt: str = None,
        image: Optional[Image.Image] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate response from MedGemma using vLLM.
        
        Args:
            prompt: Text prompt for the model
            max_new_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            image: Optional PIL Image for multimodal analysis
            temperature: Sampling temperature
        """
        if not self.loaded or self.llm is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        # Build the full prompt with system prompt if provided
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        # Configure sampling parameters
        sampling_params = SamplingParams(
            temperature=temperature if temperature > 0.0 else 0.0,
            top_p=0.9,
            max_tokens=max_new_tokens,
        )
        
        # Handle multimodal input (images)
        if image is not None:
            # Convert to RGB if needed
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            logger.info(f"Processing image: {image.size[0]}x{image.size[1]} {image.mode}")
            
            # For vLLM multimodal, we need to use the chat template format
            # MedGemma uses a specific format for multimodal inputs
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": full_prompt}
                    ]
                }
            ]
            
            # Use vLLM's chat method for multimodal
            outputs = self.llm.chat(messages, sampling_params=sampling_params)
        else:
            # Text-only generation
            outputs = self.llm.generate(full_prompt, sampling_params=sampling_params)
        
        # Extract the generated text
        if image is not None:
            # For chat/multimodal, outputs is a list
            response = outputs[0].outputs[0].text
        else:
            # For text-only
            response = outputs[0].outputs[0].text
        
        return response.strip()
    
    def batch_generate(
        self,
        prompts: List[str],
        max_new_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> List[str]:
        """Generate responses for multiple prompts in batch (more efficient).
        
        Args:
            prompts: List of text prompts
            max_new_tokens: Maximum tokens to generate per prompt
            temperature: Sampling temperature
        """
        if not self.loaded or self.llm is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        sampling_params = SamplingParams(
            temperature=temperature if temperature > 0.0 else 0.0,
            top_p=0.9,
            max_tokens=max_new_tokens,
        )
        
        outputs = self.llm.generate(prompts, sampling_params=sampling_params)
        
        return [output.outputs[0].text.strip() for output in outputs]


# Singleton instance
_vllm_model_instance = None

def get_vllm_model() -> MedGemmaModelVLLM:
    """Get or create the MedGemma vLLM model instance."""
    global _vllm_model_instance
    if _vllm_model_instance is None:
        _vllm_model_instance = MedGemmaModelVLLM()
    return _vllm_model_instance


def is_vllm_available() -> bool:
    """Check if vLLM is available and working."""
    try:
        import vllm
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# Test function
def test_vllm_inference():
    """Test vLLM inference speed."""
    import time
    
    print("Testing vLLM inference...")
    model = get_vllm_model()
    model.load()
    
    # Test prompt
    prompt = "What are the common symptoms of pneumonia?"
    
    # Warm-up
    print("Warming up...")
    _ = model.generate(prompt, max_new_tokens=100)
    
    # Timed run
    print("Running timed test...")
    start = time.time()
    response = model.generate(prompt, max_new_tokens=500)
    elapsed = time.time() - start
    
    print(f"\nResponse generated in {elapsed:.2f} seconds")
    print(f"Response preview: {response[:200]}...")
    
    return elapsed


if __name__ == "__main__":
    # Run test if called directly
    test_vllm_inference()
