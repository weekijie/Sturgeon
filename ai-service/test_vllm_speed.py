#!/usr/bin/env python3
"""
Test script to verify vLLM setup and speed improvement.
Run this in WSL2 after installing vLLM.
"""
import time
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_vllm():
    """Test vLLM backend."""
    print("=" * 60)
    print("Testing vLLM Backend")
    print("=" * 60)
    
    try:
        from medgemma_vllm import get_vllm_model, is_vllm_available
        
        if not is_vllm_available():
            print("❌ vLLM not available (CUDA not detected)")
            return False, 0
        
        print("✓ vLLM is available")
        print("✓ CUDA is available")
        
        # Load model
        print("\nLoading MedGemma model with vLLM...")
        print("(This may take 2-3 minutes on first run)")
        start = time.time()
        model = get_vllm_model()
        model.load()
        load_time = time.time() - start
        print(f"✓ Model loaded in {load_time:.1f} seconds")
        
        # Test inference
        print("\nTesting inference speed...")
        prompt = "What are the three most common symptoms of pneumonia?"
        
        # Warm-up
        print("Warm-up generation...")
        _ = model.generate(prompt, max_new_tokens=100)
        
        # Timed run
        print("Timed generation (500 tokens)...")
        start = time.time()
        response = model.generate(prompt, max_new_tokens=500)
        inference_time = time.time() - start
        
        print(f"\n✓ Inference completed in {inference_time:.2f} seconds")
        print(f"\nResponse preview:")
        print("-" * 60)
        print(response[:300] + "..." if len(response) > 300 else response)
        print("-" * 60)
        
        return True, inference_time
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def test_standard():
    """Test standard transformers backend."""
    print("\n" + "=" * 60)
    print("Testing Standard Transformers Backend")
    print("=" * 60)
    
    try:
        from medgemma import get_model
        
        print("Loading MedGemma model (standard)...")
        print("(This may take 2-3 minutes)")
        start = time.time()
        model = get_model()
        model.load()
        load_time = time.time() - start
        print(f"✓ Model loaded in {load_time:.1f} seconds")
        
        # Test inference
        print("\nTesting inference speed...")
        prompt = "What are the three most common symptoms of pneumonia?"
        
        print("Timed generation (500 tokens)...")
        start = time.time()
        response = model.generate(prompt, max_new_tokens=500)
        inference_time = time.time() - start
        
        print(f"\n✓ Inference completed in {inference_time:.2f} seconds")
        print(f"\nResponse preview:")
        print("-" * 60)
        print(response[:300] + "..." if len(response) > 300 else response)
        print("-" * 60)
        
        return True, inference_time
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def main():
    """Run comparison tests."""
    print("\n" + "=" * 60)
    print("MedGemma Inference Speed Test")
    print("Comparing vLLM vs Standard Transformers")
    print("=" * 60)
    
    # Test vLLM
    vllm_success, vllm_time = test_vllm()
    
    # Test standard (optional)
    if len(sys.argv) > 1 and sys.argv[1] == "--compare":
        standard_success, standard_time = test_standard()
        
        # Compare results
        if vllm_success and standard_success:
            print("\n" + "=" * 60)
            print("SPEED COMPARISON")
            print("=" * 60)
            print(f"vLLM:        {vllm_time:.2f} seconds")
            print(f"Standard:    {standard_time:.2f} seconds")
            speedup = standard_time / vllm_time if vllm_time > 0 else 0
            print(f"Speedup:     {speedup:.1f}x faster")
            print("=" * 60)
    else:
        if vllm_success:
            print("\n✅ vLLM is working!")
            print(f"Inference time: {vllm_time:.2f} seconds")
            print("\nTo compare with standard backend, run:")
            print("  python test_vllm_speed.py --compare")


if __name__ == "__main__":
    main()
