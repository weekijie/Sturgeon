
import sys
import os
import torch
import importlib.util
from transformers import AutoConfig

def check_package(name):
    if importlib.util.find_spec(name) is None:
        print(f"❌ {name} is NOT installed")
    else:
        try:
            module = __import__(name)
            print(f"✅ {name} is installed (version: {getattr(module, '__version__', 'unknown')})")
        except:
             print(f"✅ {name} is installed (version unknown)")

print("=== Environment Verification ===")
print(f"Python: {sys.version}")
check_package("torch")
check_package("transformers")
check_package("PIL")
check_package("accelerate")
check_package("protobuf")

if torch.cuda.is_available():
    print(f"✅ CUDA available: {torch.cuda.get_device_name(0)}")
else:
    print("⚠️ CUDA NOT available")

print("\n=== Model Access Verification ===")

# Test MedGemma
medgemma_id = "google/medgemma-1.5-4b-it"
print(f"Checking MedGemma ({medgemma_id})...")
try:
    config = AutoConfig.from_pretrained(medgemma_id, trust_remote_code=True)
    print("✅ MedGemma config loaded successfully (Access OK)")
    print("  Note: Full loading requires memory and takes time. This check confirms access/download.")
except Exception as e:
    print(f"❌ MedGemma access failed: {e}")

# Test MedSigLIP
medsiglip_id = "google/medsiglip-448"
print(f"\nChecking MedSigLIP ({medsiglip_id})...")
try:
    config = AutoConfig.from_pretrained(medsiglip_id, trust_remote_code=True)
    print("✅ MedSigLIP config loaded successfully (Access OK)")
except Exception as e:
    print(f"❌ MedSigLIP access failed: {e}")
    if "403" in str(e) or "gated" in str(e).lower():
        print("\n⚠️  ACTION REQUIRED: MedSigLIP is a GATED model.")
        print("   You must accept the license at: https://huggingface.co/google/medsiglip-448")
        print("   Then log in via CLI: `huggingface-cli login`")

print("\n=== Verification Complete ===")
