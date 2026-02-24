# Sturgeon Demo Cases

## Overview

These 3 demo cases showcase Sturgeon's core capabilities:

1. **MedSigLIP image triage** — Zero-shot modality detection
2. **MedGemma vision** — Medical image interpretation
3. **MedGemma reasoning** — Clinical differential diagnosis
4. **RAG + citations** — Evidence-based recommendations
5. **Debate flow** — Multi-turn diagnostic reasoning

---

## Case 1: Melanoma (Dermatology) — Visual Diagnosis Star

**Duration**: 60-90 seconds

**Showcases**:
- MedSigLIP: Dermatology image classification
- MedGemma: Skin lesion analysis (ABCDE criteria)
- RAG: AAD melanoma guidelines
- Debate: "Could this be benign?"

### Patient Presentation

**History**: 45-year-old male presents with a pigmented lesion on his upper back that he noticed 6 months ago. He reports it has been growing larger and the borders seem irregular. No family history of melanoma. Works as a construction worker with significant sun exposure.

**Image**: Dermoscopy/clinical photograph showing asymmetric pigmented lesion with:
- Irregular borders
- Multiple shades of brown and black
- Diameter approximately 8mm
- Asymmetric shape

### Expected Flow

1. **Upload image** → MedSigLIP detects "dermatology photograph"
2. **MedGemma analysis** → Identifies asymmetric pigmented lesion, irregular borders, color variegation
3. **Initial differential**:
   - Melanoma (High probability)
   - Dysplastic nevus (Medium)
   - Seborrheic keratosis (Low)
4. **Challenge**: "What if this is just a benign nevus?"
5. **AI response**: Defends melanoma concern with ABCDE criteria, cites AAD guidelines
6. **Suggested test**: Excisional biopsy with 1-3mm margins

### Key Points to Highlight

- ABCDE criteria application
- "Evolution" as most important criterion (changing over time)
- Excisional biopsy recommendation (not shave)
- AAD guideline citation: "(AAD Melanoma Guidelines, 2018)"

---

## Case 2: Community-Acquired Pneumonia (Radiology) — Classic Case

**Duration**: 60-90 seconds

**Showcases**:
- MedSigLIP: Chest X-ray detection
- MedGemma: Chest radiograph interpretation
- RAG: Pneumonia severity assessment guidelines
- Debate: Severity scoring, treatment decisions

### Patient Presentation

**History**: 68-year-old male presents with 4 days of fever, productive cough with yellow sputum, right-sided pleuritic chest pain, and progressive dyspnea. He has a history of hypertension and type 2 diabetes. He is a former smoker (30 pack-years).

**Vitals**:
- Temperature: 38.9°C (102°F)
- Heart rate: 110 bpm
- Respiratory rate: 24/min
- Blood pressure: 98/62 mmHg
- SpO2: 91% on room air

**Image**: Chest X-ray showing right lower lobe consolidation with possible small effusion.

### Expected Flow

1. **Upload CXR** → MedSigLIP detects "chest radiograph"
2. **MedGemma analysis** → Right lower lobe opacity, possible effusion, no pneumothorax
3. **Initial differential**:
   - Community-acquired pneumonia (High)
   - Aspiration pneumonia (Medium)
   - Lung malignancy (Low)
4. **Challenge**: "Could this be heart failure instead?"
5. **AI response**: Discusses pneumonia vs pulmonary edema features (unilateral vs bilateral, fever, purulent sputum), calculates CURB-65 score
6. **Suggested tests**: Blood cultures, sputum culture, consider Legionella urinary antigen

### Key Points to Highlight

- CURB-65 scoring (this patient: 3 = high risk)
- Site of care decision (ICU vs ward vs outpatient)
- Legionella testing indications (severe CAP, hypotension)
- PMC guideline citation: "(PMC Guidelines for Pneumonia Evaluation, 2018)"

---

## Case 3: Sepsis (Multi-Modal) — Full Stack Demonstration

**Duration**: 30-45 seconds

**Showcases**:
- Lab value extraction from text
- Clinical reasoning without image
- Multi-source data synthesis
- Sepsis guideline integration

### Patient Presentation

**History**: 72-year-old female with a history of diabetes and recurrent UTIs presents from a nursing home with 2 days of confusion, fever, and decreased urine output. She was last seen normal 48 hours ago.

**Vitals**:
- Temperature: 39.2°C (102.6°F)
- Heart rate: 118 bpm
- Respiratory rate: 26/min
- Blood pressure: 84/52 mmHg
- SpO2: 94% on room air

**Lab Results** (to be extracted from text):
```
WBC: 18.2 x10^9/L (4.0-11.0) - HIGH
Hemoglobin: 11.8 g/dL (12.0-16.0) - LOW
Platelets: 132 x10^9/L (150-400) - LOW
Creatinine: 2.1 mg/dL (0.7-1.3) - HIGH (baseline 1.0)
Lactate: 4.2 mmol/L (<2.0) - HIGH
Procalcitonin: 8.5 ng/mL (<0.5) - HIGH
Urinalysis: Positive leukocyte esterase, positive nitrites, 50 WBC/hpf
```

### Expected Flow

1. **Upload lab text** → MedGemma extracts structured values
2. **No image needed** → Pure clinical reasoning
3. **Initial differential**:
   - Septic shock (UTI source) (High)
   - Severe sepsis with AKI (High)
   - Urosepsis with bacteremia (High)
4. **Challenge**: "What if this is just dehydration from poor oral intake?"
5. **AI response**: Defends sepsis diagnosis with qSOFA criteria (altered mental status, RR>22, SBP<100), discusses lactate elevation, acute kidney injury, thrombocytopenia as evidence of organ dysfunction
6. **Suggested tests**: Blood cultures x2, urine culture, empiric antibiotics within 1 hour

### Key Points to Highlight

- qSOFA criteria application
- Sepsis-3 definition (infection + organ dysfunction)
- Time-sensitive interventions (antibiotics within 1 hour, fluids)
- CDC guideline citation: "(CDC Hospital Sepsis Program Core Elements, 2025)"

---

## Demo Recording Tips

### Video Flow

1. **Introduction** (5 sec): "Sturgeon — Clinical Debate AI for Differential Diagnosis"
2. **Case 1 — Melanoma** (60-90 sec): 
   - Upload image
   - Show MedSigLIP detection
   - Show differential
   - Challenge and AI defense
   - Citation highlight
3. **Case 2 — Pneumonia** (60-90 sec):
   - Upload CXR
   - Show analysis
   - Calculate severity score
   - Challenge alternative diagnosis
   - Guideline recommendation
4. **Case 3 — Sepsis** (30-45 sec):
   - Paste lab values
   - Show extraction
   - Sepsis recognition
   - Challenge and defense
5. **Outro** (5 sec): "Sturgeon — AI-powered diagnostic reasoning"

### Total Duration: ~3 minutes

---

## Image Requirements

| Case | Image Type | Source Suggestion |
|------|------------|-------------------|
| Melanoma | Dermoscopy/clinical photo | DermNet, ISIC Archive |
| Pneumonia | Chest X-ray | NIH ChestX-ray14, MIMIC |
| Sepsis | None (lab-based) | N/A |

### Melanoma Image Criteria

Look for an image showing:
- **Asymmetry**: One half different from other
- **Border irregularity**: Ragged, notched edges
- **Color variation**: Multiple shades (brown, black, red, blue)
- **Diameter**: >6mm visible
- **Clear photography**: Well-lit, focused

**Sources**:
- DermNet NZ (free for educational use)
- ISIC Archive (public dataset)
- Clinical photography with patient consent

### Pneumonia Image Criteria

Look for:
- **Right or left lower lobe consolidation**
- **Visible infiltrate/opacity**
- **Standard PA/lateral views**
- **Clear anatomical landmarks**

**Sources**:
- NIH ChestX-ray14 dataset (public)
- MIMIC-CXR (with data use agreement)
- PadChest dataset

---

## Citation Expectations

| Case | Expected Citations |
|------|-------------------|
| Melanoma | AAD Melanoma Guidelines, 2018 |
| Pneumonia | PMC Pneumonia Guidelines, 2018; CDC Legionella, 2025 |
| Sepsis | CDC Sepsis Program Core Elements, 2025 |

These citations should appear automatically when RAG retrieves relevant guidelines.
