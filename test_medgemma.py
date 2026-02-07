"""Quick test script for MedGemma differential diagnosis."""
import requests
import json

# Your clinical case
patient_history = """A 48-year-old male with a 15-year history of HIV, well-controlled on antiretroviral therapy (viral load undetectable, CD4 count 620 cells/mm³), presents with progressive truncal obesity over the past 2 years despite regular exercise and a balanced diet. Physical examination reveals increased abdominal girth with relatively thin extremities. CT imaging confirms a significant increase in visceral adipose tissue. His BMI is 27 kg/m² and fasting glucose is 108 mg/dL.

His current antiretroviral regimen was recently switched from an older protease inhibitor-based regimen to an integrase inhibitor-based regimen, but the abdominal fat accumulation has not improved after 12 months."""

lab_values = {
    "CD4": {"value": 620, "unit": "cells/mm³", "status": "normal"},
    "Viral Load": {"value": "undetectable", "unit": "", "status": "normal"},
    "BMI": {"value": 27, "unit": "kg/m²", "status": "elevated"},
    "Fasting Glucose": {"value": 108, "unit": "mg/dL", "status": "elevated"}
}

print("🧬 Sending request to MedGemma...")
print("-" * 50)

response = requests.post(
    "http://localhost:8000/differential",
    json={"patient_history": patient_history, "lab_values": lab_values},
    timeout=300  # 5 min timeout for model inference
)

if response.status_code == 200:
    data = response.json()
    print("\n✅ Differential Diagnoses:\n")
    for i, dx in enumerate(data["diagnoses"], 1):
        prob_emoji = "🔴" if dx["probability"] == "high" else "🟡" if dx["probability"] == "medium" else "🟢"
        print(f"{i}. {prob_emoji} {dx['name']} ({dx['probability']} probability)")
        print(f"   Supporting: {', '.join(dx['supporting_evidence'][:2])}")
        if dx['against_evidence']:
            print(f"   Against: {', '.join(dx['against_evidence'][:2])}")
        print()
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
