"""
MedGemma model loader and inference
Based on: https://huggingface.co/google/medgemma-1.5-4b-it

Upgraded from v1 (google/medgemma-4b-it) to v1.5 for:
- Better medical text reasoning accuracy
- Improved image support (CT, MRI, whole-slide histopathology)
- Structured data extraction from lab reports and EHR data
"""
from transformers import AutoProcessor, AutoModelForImageTextToText
from PIL import Image
from typing import Optional
import torch
import logging

logger = logging.getLogger(__name__)

class MedGemmaModel:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = None
        self.dtype = None
    
    def load(self, model_id: str = "google/medgemma-1.5-4b-it"):
        """Load MedGemma model with auto-selected precision."""
        logger.info(f"Loading {model_id}...")
        
        # Detect device
        if torch.cuda.is_available():
            self.device = "cuda"
            logger.info(f"Using CUDA: {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            logger.warning("CUDA not available, using CPU (will be slow)")
        
        # Auto-detect precision:
        #   bfloat16 → AMD ROCm, NVIDIA Ampere+ (A100, RTX 3090+)
        #   float16  → NVIDIA Turing (T4, GTX 1660, RTX 2080)
        if self.device == "cpu":
            self.dtype = torch.float32
        elif torch.cuda.is_bf16_supported():
            self.dtype = torch.bfloat16
        else:
            self.dtype = torch.float16
        logger.info(f"Using precision: {self.dtype}")
        
        # Load processor (replaces tokenizer for vision-language models)
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        # Load model with auto-detected precision
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            torch_dtype=self.dtype,
            device_map="auto",
            trust_remote_code=True
        )
        
        logger.info("Model loaded successfully")
        return self
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 1024,
        system_prompt: str = None,
        image: Optional[Image.Image] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate response from MedGemma using chat template.
        
        Args:
            prompt: Text prompt for the model
            max_new_tokens: Maximum tokens to generate
            system_prompt: Optional system prompt
            image: Optional PIL Image for multimodal analysis
                   (chest X-ray, dermatology, pathology, etc.)
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        # Build messages in chat format (MedGemma uses content lists)
        messages = []
        if system_prompt:
            messages.append({
                "role": "system", 
                "content": [{"type": "text", "text": system_prompt}]
            })
        
        # Build user content: image (if any) + text
        user_content = []
        if image is not None:
            # Convert to RGB if needed (e.g., RGBA PNGs, grayscale DICOM)
            if image.mode != "RGB":
                image = image.convert("RGB")
            user_content.append({"type": "image", "image": image})
            logger.info(f"Image attached: {image.size[0]}x{image.size[1]} {image.mode}")
        user_content.append({"type": "text", "text": prompt})
        
        messages.append({"role": "user", "content": user_content})
        
        # Apply chat template using processor
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device, dtype=self.dtype)
        
        input_len = inputs["input_ids"].shape[-1]
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=temperature > 0.0,
                temperature=temperature if temperature > 0.0 else 1.0,
                top_p=0.9
            )
        
        # Extract only the new tokens (after the input)
        generation = outputs[0][input_len:]
        response = self.processor.decode(generation, skip_special_tokens=True)
        
        return response.strip()


# Singleton instance
_model_instance = None

def get_model() -> MedGemmaModel:
    """Get or create the MedGemma model instance."""
    global _model_instance
    if _model_instance is None:
        _model_instance = MedGemmaModel()
    return _model_instance

