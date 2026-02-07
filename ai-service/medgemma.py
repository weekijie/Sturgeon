"""
MedGemma model loader and inference
Based on: https://huggingface.co/google/medgemma-1.5-4b-it

Upgraded from v1 (google/medgemma-4b-it) to v1.5 for:
- Better medical text reasoning accuracy
- Improved image support (CT, MRI, whole-slide histopathology)
- Structured data extraction from lab reports and EHR data
"""
from transformers import AutoProcessor, AutoModelForImageTextToText
import torch
import logging

logger = logging.getLogger(__name__)

class MedGemmaModel:
    def __init__(self):
        self.model = None
        self.processor = None
        self.device = None
    
    def load(self, model_id: str = "google/medgemma-1.5-4b-it"):
        """Load MedGemma model with FP16 precision."""
        logger.info(f"Loading {model_id}...")
        
        # Detect device
        if torch.cuda.is_available():
            self.device = "cuda"
            logger.info(f"Using CUDA: {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            logger.warning("CUDA not available, using CPU (will be slow)")
        
        # Load processor (replaces tokenizer for vision-language models)
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        # Load model with bfloat16 (required for AMD GPUs with ROCm)
        self.model = AutoModelForImageTextToText.from_pretrained(
            model_id,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True
        )
        
        logger.info("Model loaded successfully")
        return self
    
    def generate(self, prompt: str, max_new_tokens: int = 1024, system_prompt: str = None) -> str:
        """Generate response from MedGemma using chat template."""
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        # Build messages in chat format (MedGemma uses content lists)
        messages = []
        if system_prompt:
            messages.append({
                "role": "system", 
                "content": [{"type": "text", "text": system_prompt}]
            })
        messages.append({
            "role": "user", 
            "content": [{"type": "text", "text": prompt}]
        })
        
        # Apply chat template using processor
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt"
        ).to(self.model.device, dtype=torch.bfloat16)
        
        input_len = inputs["input_ids"].shape[-1]
        
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=True,
                temperature=0.7,
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

