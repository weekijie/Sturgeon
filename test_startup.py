"""Quick startup test - catches and prints any errors during model loading."""
import sys
import os
import traceback

print("=" * 60)
print("Sturgeon Startup Test")
print("=" * 60)

# Step 1: Test imports
print("\n[1/4] Testing imports...")
try:
    # Use importlib to handle the hyphenated package name
    import importlib
    pkg = importlib.import_module("ai-service")
    medgemma_mod = importlib.import_module("ai-service.medgemma")
    siglip_mod = importlib.import_module("ai-service.medsiglip")
    orch_mod = importlib.import_module("ai-service.gemini_orchestrator")
    
    get_model = medgemma_mod.get_model
    get_siglip = siglip_mod.get_siglip
    get_orchestrator = orch_mod.get_orchestrator
    print("  OK - All imports successful")
except Exception as e:
    print(f"  FAIL - Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 2: Load MedGemma
print("\n[2/4] Loading MedGemma...")
try:
    model = get_model()
    model.load()
    print(f"  OK - MedGemma loaded on {model.device}")
except Exception as e:
    print(f"  FAIL - MedGemma error: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 3: Load MedSigLIP
print("\n[3/4] Loading MedSigLIP...")
try:
    siglip = get_siglip()
    siglip.load()
    print(f"  OK - MedSigLIP loaded on {siglip.device}")
except Exception as e:
    print(f"  FAIL - MedSigLIP error: {e}")
    traceback.print_exc()
    print("  (MedSigLIP is optional, continuing...)")

# Step 4: Test Gemini
print("\n[4/4] Initializing Gemini orchestrator...")
try:
    orch = get_orchestrator()
    orch.medgemma = model
    orch.initialize()
    print(f"  OK - Gemini orchestrator ready")
except Exception as e:
    print(f"  WARN - Gemini not available: {e}")
    print("  (Will fall back to MedGemma-only mode)")

print("\n" + "=" * 60)
print("All critical components loaded!")
print("=" * 60)
print("\nStarting uvicorn server on http://127.0.0.1:8000 ...")

# Start server using the same method uvicorn CLI uses
import uvicorn
main_mod = importlib.import_module("ai-service.main")
uvicorn.run(main_mod.app, host="127.0.0.1", port=8000)
