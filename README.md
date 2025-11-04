# Clinical-Notes-Cleaner
# NLP-powered Python app that converts unstructured clinical notes into structured EHR-ready data.
import re
import sys
import subprocess
import pandas as pd

# -----------------------------------------------
# Auto-install dependencies if missing
# -----------------------------------------------
def install_package(package):
    try:
        __import__(package)
    except ImportError:
        print(f"Installing missing package: {package} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_package("spacy")
install_package("pandas")
install_package("openpyxl")

# -----------------------------------------------
# Try scispaCy first (better for clinical text)
# -----------------------------------------------
use_scispacy = False
try:
    install_package("scispacy")
    # Updated working model URL for scispaCy
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "https://github.com/allenai/scispacy/releases/download/v0.5.1/en_core_sci_sm-0.5.1.tar.gz"
    ])
    import scispacy
    import en_core_sci_sm
    nlp = en_core_sci_sm.load()
    use_scispacy = True
    print("✅ Using scispaCy biomedical model.")
except Exception:
    import spacy
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        print("Downloading 'en_core_web_sm' model...")
        subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
        nlp = spacy.load("en_core_web_sm")
    print("⚠️ Using basic spaCy model (general English).")

# -----------------------------------------------
# Function: Clean text for Excel
# -----------------------------------------------
def clean_text_for_excel(text):
    """Remove illegal characters that Excel cannot handle."""
    if not isinstance(text, str):
        return text
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')

# -----------------------------------------------
# Function: Extract drug dosages with mg
# -----------------------------------------------
def extract_drug_dosages(note_text):
    """Finds all drug names with dosages in mg (e.g., 'Paracetamol 500 mg')."""
    dosage_pattern = r"([A-Za-z][A-Za-z\s]+?)\s+(\d+(?:\.\d+)?)\s*mg"
    matches = re.findall(dosage_pattern, note_text, re.IGNORECASE)
    dosage_dict = {}
    for drug, mg in matches:
        drug_name = drug.strip()
        dosage_dict[drug_name] = f"{mg} mg"
    return dosage_dict

# -----------------------------------------------
# Function: Extract structured data (enhanced)
# -----------------------------------------------
def extract_structured_data(note_text):
    structured_data = {}

    # --- Extract duration ---
    duration_match = re.search(r"for the past ([\w\s]+days?)", note_text, re.IGNORECASE)
    if duration_match:
        structured_data["Duration"] = duration_match.group(1).strip()

    # --- Extract symptoms ---
    symptoms = []
    symptom_keywords = ["rhinorrhea", "congestion", "sneezing", "stuffiness", "cough", "dyspnea", "fever"]
    for symptom in symptom_keywords:
        if re.search(rf"\b{symptom}\b", note_text, re.IGNORECASE):
            symptoms.append(symptom)
    if symptoms:
        structured_data["Symptoms"] = ", ".join(symptoms)

    # --- Extract physical findings ---
    physical_findings = re.findall(r"(?:reveals|shows|demonstrates|indicates)\s([^\.]+)\.", note_text, re.IGNORECASE)
    if physical_findings:
        structured_data["Physical Findings"] = "; ".join([f.strip() for f in physical_findings])

    # --- Extract general condition ---
    if re.search(r"no acute distress", note_text, re.IGNORECASE):
        structured_data["General Appearance"] = "No acute distress"
    if re.search(r"afebrile", note_text, re.IGNORECASE):
        structured_data["Temperature Status"] = "Afebrile"

    # --- NLP entities ---
    if use_scispacy:
        doc = nlp(note_text)
        for ent in doc.ents:
            if ent.label_ not in structured_data and len(ent.text.split()) < 10:
                structured_data[ent.label_] = ent.text

    # --- Extract sections ---
    section_pattern = r"\*\*(.*?)\*\*\s*([\s\S]*?)(?=\n\*\*|$)"
    sections = re.findall(section_pattern, note_text)
    for title, content in sections:
        structured_data[title.strip()] = content.strip()

    # --- Add detected drug dosages ---
    drug_dosages = extract_drug_dosages(note_text)
    structured_data.update(drug_dosages)

    # --- Clean all text for Excel ---
    structured_data = {k: clean_text_for_excel(v) for k, v in structured_data.items()}

    return structured_data

# -----------------------------------------------
# Function: Process clinical note and save to Excel
# -----------------------------------------------
def process_note_input(note_text):
    structured_data = extract_structured_data(note_text)

    # Print structured data
    print("\n--- Extracted Structured Data ---")
    for key, value in structured_data.items():
        print(f"{key}: {value}")
    print("---------------------------------\n")

    if not structured_data:
        print("⚠️ No structured data extracted. Try reviewing input format.")
    else:
        df = pd.DataFrame([structured_data])
        output_path = "Structured_Clinical_Note.xlsx"
        df.to_excel(output_path, index=False)
        print(f"✅ Conversion complete! Structured Excel file saved as: {output_path}\n")

# -----------------------------------------------
# Main Execution
# -----------------------------------------------
if __name__ == "__main__":
    print("\n=== Clinical Note to Structured Excel Converter (Biomedical Enhanced) ===\n")
    print("🩺 Paste your clinical note below. When finished, press ENTER, then CTRL+Z (Windows) or CTRL+D (Mac/Linux).\n")

    note_text = sys.stdin.read().strip()
    if not note_text:
        print("⚠️ No input detected. Please paste a clinical note next time.")
    else:
        process_note_input(note_text)
