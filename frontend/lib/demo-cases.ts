/**
 * Demo Test Cases for Sturgeon
 * 
 * Pre-loaded medical cases for demonstration purposes.
 * Each case includes patient history, lab values, and references to test images.
 */

export interface DemoCase {
  id: string;
  name: string;
  category: "Dermatology" | "Pathology" | "Radiology" | "General";
  description: string;
  patientHistory: string;
  labValues: Record<string, { value: string; unit: string; status: "normal" | "high" | "low" }>;
  imageFile?: string; // Path to test image in test-data/
  suggestedChallenges: string[];
}

export const demoCases: DemoCase[] = [
  {
    id: "melanoma",
    name: "Suspected Melanoma",
    category: "Dermatology",
    description: "43-year-old male with changing mole on upper back",
    patientHistory: `43-year-old male presents with a changing mole on his upper back, first noticed by his wife 3 months ago.

Chief Complaint: Pigmented skin lesion that has grown and changed color over the past 3 months.

History of Present Illness:
- Mole was previously flat and uniform brown, approximately 4mm
- Now raised, asymmetric, with irregular borders
- Color variation: dark brown, black, and reddish-pink areas
- Current size approximately 9mm (grown from ~4mm)
- Occasional itching, no bleeding or ulceration
- No pain at rest

Past Medical History:
- History of multiple sunburns in childhood/adolescence
- No prior skin cancer
- No family history of melanoma

Social History:
- Outdoor construction worker for 20 years
- Minimal sunscreen use historically
- Fair skin, light brown hair, blue eyes (Fitzpatrick type II)
- No tobacco, occasional alcohol

Physical Examination:
- Asymmetric pigmented macule/papule on upper back
- Irregular, notched borders
- Color variegation: brown, black, red-pink
- Diameter 9mm
- Elevated centrally (previously flat per patient)
- ABCDE criteria: A+, B+, C+, D+, E+
- No palpable axillary or cervical lymphadenopathy
- No other suspicious lesions on full-body skin exam`,
    labValues: {
      "WBC": { value: "7.2", unit: "x10^9/L", status: "normal" },
      "Hemoglobin": { value: "14.8", unit: "g/dL", status: "normal" },
      "Platelets": { value: "245", unit: "x10^9/L", status: "normal" },
      "LDH": { value: "185", unit: "U/L", status: "normal" },
      "CRP": { value: "2.1", unit: "mg/L", status: "normal" },
    },
    imageFile: "test-data/derm-melanoma.jpg",
    suggestedChallenges: [
      "Could this just be a dysplastic nevus? The patient has no family history of melanoma.",
      "LDH is normal — doesn't that argue against melanoma?",
      "The lesion is only 9mm. Couldn't watchful waiting be appropriate?",
      "What about seborrheic keratosis? Those can also look irregular in older patients.",
    ],
  },
  {
    id: "psoriasis",
    name: "Psoriasis vs Eczema",
    category: "Dermatology",
    description: "28-year-old female with recurring scaly plaques",
    patientHistory: `28-year-old female presents with recurring, scaly plaques on her elbows and knees for 6 months.

Chief Complaint: Itchy, red, scaly patches on elbows, knees, and scalp.

History of Present Illness:
- Started as small red patch on right elbow 6 months ago
- Gradually spread to both elbows, both knees, scalp, and lower back
- Lesions are well-demarcated, raised, erythematous plaques with silvery-white scales
- Auspitz sign positive (pinpoint bleeding when scales removed)
- Moderate pruritus, worsens with stress and cold weather
- Koebner phenomenon noted — new lesions appearing at site of scratch
- No joint pain or stiffness
- Tried OTC hydrocortisone cream with minimal improvement

Past Medical History:
- Father has psoriasis (diagnosed age 35)
- No prior skin conditions
- No autoimmune diseases

Social History:
- Office worker, moderate stress level
- Non-smoker, social drinker
- No recent medication changes

Physical Examination:
- Well-demarcated erythematous plaques with thick silvery scales
- Distribution: bilateral elbows, knees, scalp (behind ears), sacral area
- Auspitz sign positive
- Nail examination: pitting on 3 fingernails, no onycholysis
- No joint swelling or tenderness
- BSA involvement estimated at 8%`,
    labValues: {
      "WBC": { value: "8.1", unit: "x10^9/L", status: "normal" },
      "Hemoglobin": { value: "13.2", unit: "g/dL", status: "normal" },
      "CRP": { value: "8.5", unit: "mg/L", status: "normal" },
      "Uric Acid": { value: "7.1", unit: "mg/dL", status: "high" },
      "Fasting Glucose": { value: "102", unit: "mg/dL", status: "high" },
      "Total Cholesterol": { value: "218", unit: "mg/dL", status: "high" },
      "LDL": { value: "142", unit: "mg/dL", status: "high" },
    },
    imageFile: "test-data/derm-psoriasis.jpg",
    suggestedChallenges: [
      "How do you rule out nummular eczema? Both present as round scaly plaques.",
      "The metabolic abnormalities are interesting — is there a connection to the skin disease?",
      "Could this be secondary syphilis? The patient is young with a widespread rash.",
      "Nail pitting is present — should we be concerned about psoriatic arthritis even without joint symptoms?",
    ],
  },
  {
    id: "breast-carcinoma",
    name: "Breast Carcinoma",
    category: "Pathology",
    description: "56-year-old female with BI-RADS 5 lesion on mammography",
    patientHistory: `56-year-old female presents after mammography screening revealed a 2.3cm spiculated mass in the upper outer quadrant of the left breast.

Chief Complaint: Abnormal screening mammogram finding, referred for biopsy.

History of Present Illness:
- Routine annual mammogram showed BI-RADS 5 lesion (highly suggestive of malignancy)
- 2.3cm spiculated mass, upper outer quadrant, left breast
- Patient was asymptomatic — no palpable lump, pain, or nipple discharge
- No skin changes (dimpling, peau d'orange)
- Ultrasound confirmed solid hypoechoic mass with irregular margins
- Core needle biopsy performed 3 days ago, pathology pending

Past Medical History:
- Menarche age 11, nulliparous
- No prior breast biopsies
- No HRT use
- Maternal aunt diagnosed with breast cancer at age 62
- BRCA testing not previously performed

Social History:
- Accountant, sedentary lifestyle
- BMI 28.5
- Non-smoker
- 1-2 glasses of wine per week
- No occupational exposures

Physical Examination:
- Left breast: no palpable mass (deep lesion), no skin changes
- No axillary lymphadenopathy bilaterally
- Right breast normal
- No hepatomegaly`,
    labValues: {
      "WBC": { value: "6.8", unit: "x10^9/L", status: "normal" },
      "Hemoglobin": { value: "12.9", unit: "g/dL", status: "normal" },
      "CA 15-3": { value: "42", unit: "U/mL", status: "high" },
      "CEA": { value: "3.8", unit: "ng/mL", status: "high" },
      "Calcium": { value: "9.8", unit: "mg/dL", status: "normal" },
      "LDH": { value: "195", unit: "U/L", status: "normal" },
    },
    imageFile: "test-data/path-breast-carcinoma.png",
    suggestedChallenges: [
      "CA 15-3 is only mildly elevated. Isn't it unreliable for early-stage disease?",
      "ER/PR positive and HER2 negative — doesn't this actually carry a better prognosis?",
      "Ki-67 is 22%. Is that high enough to classify this as Luminal B?",
      "The patient has no palpable mass. Could this be DCIS rather than invasive carcinoma?",
    ],
  },
  {
    id: "lung-adenocarcinoma",
    name: "Lung Adenocarcinoma",
    category: "Pathology",
    description: "62-year-old male with persistent cough and incidental CT finding",
    patientHistory: `62-year-old male presents with persistent cough and incidental finding on chest CT.

Chief Complaint: 3-month history of dry cough, unintentional weight loss of 5kg.

History of Present Illness:
- Persistent dry cough for 3 months, not responding to antibiotics
- Unintentional weight loss of 5kg over 2 months
- Mild dyspnea on exertion (climbing 2 flights of stairs)
- No hemoptysis
- No chest pain
- CT chest revealed 2.8cm spiculated nodule in right upper lobe with ground-glass halo
- PET scan showed FDG avidity (SUV max 8.2)
- CT-guided biopsy performed, pathology result below

Past Medical History:
- 30 pack-year smoking history (quit 5 years ago)
- COPD (mild, on PRN albuterol)
- Hypertension (controlled on lisinopril)
- No prior malignancy

Social History:
- Retired mechanic (asbestos exposure possible)
- Former smoker (quit 5 years ago)
- Lives with wife, independent ADLs

Physical Examination:
- Decreased breath sounds right upper lobe
- No wheezing or crackles
- No clubbing or cyanosis
- No cervical or supraclavicular lymphadenopathy
- No hepatomegaly`,
    labValues: {
      "WBC": { value: "9.8", unit: "x10^9/L", status: "normal" },
      "Hemoglobin": { value: "11.2", unit: "g/dL", status: "low" },
      "CEA": { value: "12.4", unit: "ng/mL", status: "high" },
      "CYFRA 21-1": { value: "5.8", unit: "ng/mL", status: "high" },
      "Calcium": { value: "10.8", unit: "mg/dL", status: "high" },
      "LDH": { value: "310", unit: "U/L", status: "high" },
      "D-dimer": { value: "0.88", unit: "mg/L", status: "high" },
    },
    imageFile: "test-data/path-lung-adenocarcinoma.jpeg",
    suggestedChallenges: [
      "The patient quit smoking 5 years ago. Could this be a benign granuloma rather than malignancy?",
      "EGFR exon 19 deletion — doesn't this change the treatment approach entirely compared to wild-type?",
      "Hemoglobin is low with normal MCV. Is this anemia of chronic disease or could there be bone marrow involvement?",
      "LDH and calcium are both elevated. Should we be staging this higher than the imaging suggests?",
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
 * Load demo case files (returns File objects for images)
 * Note: In browser environment, you'll need to use fetch + File constructor
 */
export async function loadDemoImage(filePath: string): Promise<File | null> {
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