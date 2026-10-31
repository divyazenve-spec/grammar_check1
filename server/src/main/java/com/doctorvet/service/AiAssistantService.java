package com.doctorvet.service;

import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class AiAssistantService {

    public record Differential(String name, String likelihood, String reasoning) {}

    public record AiResponse(
            List<Differential> primaryDifferentials,
            List<String> recommendedDiagnostics,
            List<String> emergencyActionProtocol
    ) {}

    public AiResponse generateDifferential(String species, String symptoms, String vitals) {
        String sp = species != null && !species.isBlank() ? species.trim() : "Canine";
        String sym = symptoms != null ? symptoms.toLowerCase() : "";
        String vit = vitals != null ? vitals.toLowerCase() : "";
        String combined = sym + " " + vit;

        // 1. CARDIAC
        if (combined.contains("syncope") || combined.contains("murmur") || combined.contains("tachycardia") || 
            combined.contains("arrhythmia") || combined.contains("gallop") || combined.contains("cough") && combined.contains("heart")) {
            return new AiResponse(
                    List.of(
                            new Differential("Stage C Dilated Cardiomyopathy (DCM) / Arrhythmia", "High (80%)", "Evidence of cardiac compromise, pulse deficits, exercise intolerance, or syncope in " + sp + "."),
                            new Differential("Congestive Heart Failure (CHF) with Pulmonary Edema", "Moderate (65%)", "Tachypnea, resting respiratory distress, and potential thoracic fluid congestion."),
                            new Differential("Pericardial Effusion with Cardiac Tamponade", "Moderate (40%)", "Muffled heart sounds and weak arterial pulses.")
                    ),
                    List.of(
                            "Right lateral and dorsoventral thoracic radiographs to assess the vertebral heart score (VHS)",
                            "Transthoracic echocardiogram (verify fractional shortening and chamber dimensions)",
                            "6-lead continuous electrocardiogram (ECG) to identify rhythm disturbance",
                            "Serum NT-proBNP biomarker and cardiac Troponin I (cTnI) levels"
                    ),
                    List.of(
                            "Provide supplemental oxygen via cage or gentle flow-by (40–60% FiO2).",
                            "Administer an IV loop diuretic (Furosemide 2 mg/kg) if pulmonary crackles or edema are present.",
                            "Initiate oral inodilator (Pimobendan 0.25 mg/kg) once stabilized.",
                            "Avoid aggressive fluid therapy or high-sodium crystalloids."
                    )
            );
        }

        // 2. FELINE SPECIFIC: LOWER URINARY TRACT / OBSTRUCTION
        if (sp.equalsIgnoreCase("Feline") && (combined.contains("stranguria") || combined.contains("straining") || 
            combined.contains("litter") || combined.contains("block") || combined.contains("urinary") || combined.contains("hematuria"))) {
            return new AiResponse(
                    List.of(
                            new Differential("Feline Urethral Obstruction (FLUTD / Blocked Cat)", "High (90%)", "Tense, painful, non-expressible bladder with dysuria and vocalization in a feline."),
                            new Differential("Feline Idiopathic Cystitis (FIC)", "Moderate (55%)", "Sterile neurogenic inflammation triggered by environmental stress."),
                            new Differential("Urolithiasis (Struvite or Calcium Oxalate Calculi)", "Moderate (45%)", "Cystic calculi causing mechanical outflow blockage.")
                    ),
                    List.of(
                            "Immediate point-of-care serum potassium and creatinine evaluation (hyperkalemia triage)",
                            "Lateral abdominal radiograph to assess for radiopaque calculi along the urethral tract",
                            "Urinalysis (sediment microscopy, crystals, urine protein-to-creatinine ratio)",
                            "Bladder ultrasound to inspect mucosal thickening and intraluminal matrix plugs"
                    ),
                    List.of(
                            "Immediate emergency decompressive cystocentesis if catheterization is delayed.",
                            "Address life-threatening hyperkalemia: 10% Calcium gluconate (0.5-1.5 mL/kg slow IV with ECG monitoring).",
                            "Place an indwelling soft radiopaque tomcat catheter under sedation and flush with warm sterile saline.",
                            "Initiate IV balanced crystalloids to correct metabolic acidosis and post-obstructive diuresis."
                    )
            );
        }

        // 3. RESPIRATORY / DYSPNEA
        if (combined.contains("dyspnea") || combined.contains("tachypnea") || combined.contains("cyanosis") || 
            combined.contains("stridor") || combined.contains("wheezing") || combined.contains("respiratory")) {
            return new AiResponse(
                    List.of(
                            new Differential("Acute Respiratory Distress / Tension Pneumothorax", "High (75%)", "Rapid, shallow tachypnea with cyanotic or pale mucous membranes in " + sp + "."),
                            new Differential("Severe Bronchoconstriction / Feline Asthma or RAO", "Moderate (60%)", "Prominent expiratory push, wheezing, and hyper-resonance on thoracic percussion."),
                            new Differential("Non-Cardiogenic Pulmonary Edema / ARDS", "Moderate (35%)", "Diffuse pulmonary alveolar infiltrates secondary to trauma, electrocution, or sepsis.")
                    ),
                    List.of(
                            "TFAST (Thoracic Focused Assessment with Sonography for Trauma/Triage)",
                            "Arterial blood gas (ABG) or pulse oximetry monitoring (SpO2)",
                            "Three-view thoracic radiographs (defer if the patient is too stressed for restraint)",
                            "Complete CBC with differential leukogram to evaluate septic left-shift"
                    ),
                    List.of(
                            "Immediate minimal-handling oxygen therapy via mask, hood, or oxygen cage.",
                            "Perform emergency bilateral thoracocentesis in the 7th–9th intercostal space if a pneumothorax is suspected.",
                            "Inject a rapid-acting bronchodilator (Terbutaline 0.01 mg/kg SC) or dexamethasone SP if asthma or anaphylaxis is suspected.",
                            "Keep environmental noise and stress to an absolute minimum."
                    )
            );
        }

        // 4. EQUINE SPECIFIC: COLIC
        if (sp.equalsIgnoreCase("Equine") && (combined.contains("colic") || combined.contains("pawing") || 
            combined.contains("reflux") || combined.contains("rolling") || combined.contains("gut"))) {
            return new AiResponse(
                    List.of(
                            new Differential("Strangulating Large Colon Volvulus / Small Intestinal Entrapment", "High (80%)", "Unremitting, violent colic pain unresponsive to systemic analgesics in an equine."),
                            new Differential("Large Colon Impaction (Pelvic Flexure)", "Moderate (50%)", "Mild-to-moderate continuous colic with decreased fecal output."),
                            new Differential("Spasmodic Colic / Tympany", "Moderate (40%)", "Intermittent hypermotile bowel sounds responsive to antispasmodics.")
                    ),
                    List.of(
                            "Immediate nasogastric intubation (assess net spontaneous fluid reflux volume)",
                            "Transrectal palpation to evaluate pelvic flexure impaction or distended small bowel loops",
                            "FLASH abdominal ultrasound protocol (evaluate intestinal wall thickness > 4mm)",
                            "Abdominocentesis (evaluate peritoneal total protein and lactate level > 4 mmol/L)"
                    ),
                    List.of(
                            "Pass a nasogastric tube promptly to relieve gastric distension and prevent stomach rupture.",
                            "Control visceral pain: Flunixin meglumine (1.1 mg/kg IV) or Xylazine (0.5 mg/kg IV).",
                            "Prepare for emergency exploratory laparotomy if net reflux > 5 L or peritoneal lactate is elevated.",
                            "Initiate rapid IV balanced fluid resuscitation via a 10G jugular catheter."
                    )
            );
        }

        // 5. GASTROINTESTINAL / ACUTE ABDOMEN (DEFAULT OR CANINE GDV)
        return new AiResponse(
                List.of(
                        new Differential("Acute Gastric Dilatation-Volvulus (GDV)", "High (85%)", "Prominent cranial abdominal distension, non-productive retching, and tachycardia in " + sp + "."),
                        new Differential("Severe Acute Pancreatitis with Peritonitis", "Moderate (45%)", "Cranial abdominal guarding, vomiting, and systemic inflammatory response."),
                        new Differential("Intestinal Foreign Body Obstruction with Perforation", "Moderate (40%)", "Vomiting, dehydration, and localized pain on mid-abdominal palpation.")
                ),
                List.of(
                        "Right lateral abdominal radiograph (verify double-bubble / reverse C-sign for GDV)",
                        "Abdominal FAST (AFAST) scan to rule out peritoneal effusion in hepato-renal and spleno-renal sites",
                        "Serial blood lactate monitoring (Lactate > 6 mmol/L correlates with gastric wall necrosis)",
                        "Complete Blood Count (CBC) and full serum chemistry with electrolytes"
                ),
                List.of(
                        "Place dual 16G/18G cephalic IV catheters immediately.",
                        "Initiate balanced isotonic crystalloid shock resuscitation (20-30 mL/kg over 15-20 min).",
                        "Perform percutaneous gastric trocar decompression with a 14G catheter in the right paracostal flank.",
                        "Schedule prompt emergency surgical stabilization, exploratory laparotomy, and gastropexy."
                )
        );
    }
}
