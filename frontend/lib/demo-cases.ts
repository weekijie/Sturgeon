/**
 * Demo Test Cases for Sturgeon
 * 
 * Pre-loaded medical cases for demonstration purposes.
 * Aligned with Guide-RAG paper evaluation framework.
 * 
 * 3 Cases:
 * 1. Melanoma (Dermatology) — Image + labs
 * 2. Pneumonia (Radiology) — Image + labs
 * 3. Sepsis (Critical Care) — Labs-focused shock case
 */

export interface DemoCase {
  id: string;
  name: string;
  category: "Dermatology" | "Radiology" | "Critical Care";
  evidenceMode: "Image + Labs" | "Labs only";
  description: string;
  patientHistory: string;
  labValues: Record<string, { value: string; unit: string; status: "normal" | "high" | "low" }>;
  labFile?: string;
  imageFile?: string;
  suggestedChallenges: string[];
}

export const demoCases: DemoCase[] = [
  {
    id: "melanoma",
    name: "Suspected Melanoma",
    category: "Dermatology",
    evidenceMode: "Image + Labs",
    description: "45-year-old male with changing pigmented lesion on upper back",
    patientHistory: `45-year-old male presents with a pigmented lesion on his upper back that he noticed 6 months ago. He reports it has been growing larger and the borders seem irregular. No family history of melanoma. Works as a construction worker with significant sun exposure.

Chief Complaint: Changing mole on upper back — growing larger, irregular borders over 6 months.

History of Present Illness:
- Lesion was previously flat and uniform brown, approximately 4mm
- Now raised, asymmetric, with irregular borders
- Color variation: dark brown, black, and reddish-pink areas
- Current size approximately 8mm (grown from ~4mm)
- Occasional itching, no bleeding or ulceration
- No pain at rest

Past Medical History:
- History of multiple sunburns in childhood/adolescence
- No prior skin cancer
- No family history of melanoma

Social History:
- Construction worker for 20 years (outdoor exposure)
- Minimal sunscreen use historically
- Fair skin, light brown hair, blue eyes (Fitzpatrick type II)
- No tobacco, occasional alcohol

Physical Examination:
- Asymmetric pigmented macule/papule on upper back
- Irregular, notched borders
- Color variegation: brown, black, red-pink
- Diameter 8mm
- Elevated centrally (previously flat per patient)
- ABCDE criteria: A+, B+, C+, D+, E+
- No palpable axillary or cervical lymphadenopathy
- No other suspicious lesions on full-body skin exam`,
    labValues: {
      "WBC": { value: "7.2", unit: "x10^9/L", status: "normal" },
      "Hemoglobin": { value: "14.8", unit: "g/dL", status: "normal" },
      "Platelets": { value: "245", unit: "x10^9/L", status: "normal" },
      "LDH": { value: "185", unit: "U/L", status: "normal" },
    },
    labFile: "test-data/melanoma-labs.pdf",
    imageFile: "test-data/derm-melanoma.jpg",
    suggestedChallenges: [
      "What if this is just a benign nevus? The patient has no family history.",
      "LDH is normal — doesn't that argue against melanoma?",
      "The lesion is only 8mm. Couldn't watchful waiting be appropriate?",
      "Could this be seborrheic keratosis instead?",
    ],
  },
  {
    id: "pneumonia",
    name: "Community-Acquired Pneumonia",
    category: "Radiology",
    evidenceMode: "Image + Labs",
    description: "68-year-old male with fever, cough, and chest X-ray infiltrate",
    patientHistory: `68-year-old male presents with 4 days of fever, productive cough with yellow sputum, right-sided pleuritic chest pain, and progressive dyspnea.

Chief Complaint: Fever, productive cough, and shortness of breath for 4 days.

History of Present Illness:
- Fever up to 38.9°C (102°F) for 4 days
- Productive cough with yellow-green sputum
- Right-sided pleuritic chest pain
- Progressive dyspnea — now dyspneic walking one block
- No hemoptysis
- Symptoms started gradually, worsening over 4 days

Past Medical History:
- Hypertension (controlled on lisinopril)
- Type 2 diabetes (on metformin)
- Hyperlipidemia (on atorvastatin)
- Former smoker (30 pack-years, quit 8 years ago)

Social History:
- Retired accountant
- Lives with wife
- No sick contacts
- No recent travel

Vital Signs:
- Temperature: 38.9°C (102°F)
- Heart rate: 110 bpm
- Respiratory rate: 24/min
- Blood pressure: 98/62 mmHg
- SpO2: 91% on room air

Physical Examination:
- Ill-appearing, diaphoretic male
- Tachypneic, using accessory muscles
- Right base: decreased breath sounds, crackles, dullness to percussion
- Left lung: clear
- No wheezing
- Regular tachycardia, no murmurs
- No JVD, no peripheral edema`,
    labValues: {
      "WBC": { value: "15.8", unit: "x10^9/L", status: "high" },
      "Hemoglobin": { value: "13.2", unit: "g/dL", status: "normal" },
      "Platelets": { value: "198", unit: "x10^9/L", status: "normal" },
      "Creatinine": { value: "1.4", unit: "mg/dL", status: "high" },
      "BUN": { value: "28", unit: "mg/dL", status: "high" },
      "Lactate": { value: "2.8", unit: "mmol/L", status: "high" },
      "CRP": { value: "85", unit: "mg/L", status: "high" },
      "Procalcitonin": { value: "4.2", unit: "ng/mL", status: "high" },
    },
    labFile: "test-data/pneumonia-labs.pdf",
    imageFile: "test-data/person100_bacteria_475.jpeg",
    suggestedChallenges: [
      "Could this be heart failure instead? He has diabetes and hypertension.",
      "The patient is hypotensive. Should he go to the ICU?",
      "What is his CURB-65 score and what does it mean for disposition?",
      "Should we test for Legionella given the severity?",
    ],
  },
  {
    id: "sepsis",
    name: "Septic Shock (UTI Source)",
    category: "Critical Care",
    evidenceMode: "Labs only",
    description: "72-year-old female with confusion, fever, hypotension",
    patientHistory: `72-year-old female with a history of diabetes and recurrent UTIs presents from a nursing home with 2 days of confusion, fever, and decreased urine output. She was last seen normal 48 hours ago.

Chief Complaint: Altered mental status and fever from nursing home.

History of Present Illness:
- Found confused and febrile at nursing home this morning
- Last seen normal 48 hours ago by nursing staff
- Decreased urine output over past 24 hours (voided only once)
- No cough, no abdominal pain reported (patient unable to give history reliably)
- Nursing home reports patient had been complaining of "burning when peeing" 3 days ago

Past Medical History:
- Type 2 diabetes (on glipizide + sitagliptin)
- Recurrent UTIs (3 episodes in past year)
- Hypertension (on amlodipine)
- Chronic kidney disease stage 2 (baseline creatinine 1.0)
- No known drug allergies

Social History:
- Nursing home resident for 2 years
- Bedridden, requires assistance with ADLs
- Foley catheter removed 2 weeks ago

Vital Signs:
- Temperature: 39.2°C (102.6°F)
- Heart rate: 118 bpm
- Respiratory rate: 26/min
- Blood pressure: 84/52 mmHg
- SpO2: 94% on room air

Physical Examination:
- Elderly female, ill-appearing, somnolent but arousable
- Oriented only to person
- Tachycardic, regular rhythm
- Tachypneic, lungs clear bilaterally
- Abdomen soft, non-tender, no masses
- Suprapubic tenderness on palpation
- No focal neurological deficits`,
    labValues: {
      "WBC": { value: "18.2", unit: "x10^9/L", status: "high" },
      "Hemoglobin": { value: "11.8", unit: "g/dL", status: "low" },
      "Platelets": { value: "132", unit: "x10^9/L", status: "low" },
      "Creatinine": { value: "2.1", unit: "mg/dL", status: "high" },
      "BUN": { value: "42", unit: "mg/dL", status: "high" },
      "Lactate": { value: "4.2", unit: "mmol/L", status: "high" },
      "Procalcitonin": { value: "8.5", unit: "ng/mL", status: "high" },
      "Glucose": { value: "285", unit: "mg/dL", status: "high" },
    },
    labFile: "test-data/sepsis-labs.pdf",
    imageFile: undefined,
    suggestedChallenges: [
      "What if this is just dehydration from poor oral intake?",
      "How do you differentiate sepsis from simple UTI?",
      "What are the qSOFA criteria and does she meet them?",
      "Should we start vasopressors given the hypotension?",
    ],
  },
];

/**
 * Get a demo case by ID
 */
export function getDemoCase(id: string): DemoCase | undefined {
  return demoCases.find((c) => c.id === id);
}

/**
 * Convert lab values object to formatted string for display
 */
export function formatLabValuesForDisplay(labValues: DemoCase["labValues"]): string {
  return Object.entries(labValues)
    .map(([name, data]) => `${name}: ${data.value} ${data.unit}`)
    .join("\n");
}

/**
 * Load demo case files
 */
export async function loadDemoImage(filePath: string | undefined): Promise<File | null> {
  if (!filePath) return null;
  
  try {
    const response = await fetch(filePath);
    if (!response.ok) return null;
    
    const blob = await response.blob();
    const filename = filePath.split("/").pop() || "image.jpg";
    return new File([blob], filename, { type: blob.type });
  } catch (error) {
    console.error("Failed to load demo image:", error);
    return null;
  }
}

export async function loadDemoLabFile(filePath: string | undefined): Promise<File | null> {
  if (!filePath) return null;

  try {
    const response = await fetch(filePath);
    if (!response.ok) return null;

    const blob = await response.blob();
    const filename = filePath.split("/").pop() || "labs.pdf";
    const mimeType = blob.type || "application/pdf";
    return new File([blob], filename, { type: mimeType });
  } catch (error) {
    console.error("Failed to load demo lab file:", error);
    return null;
  }
}
