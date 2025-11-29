# streamlit_app.py
# Clinical Note -> Structured Excel/CSV (Streamlit version of your original script)
import re
import io
import pandas as pd
import spacy
import streamlit as st

st.set_page_config(page_title="Clinical Note Structuring Tool", layout="wide")

# ---------------------------
# Load spaCy model (cached)
# ---------------------------
@st.cache_resource
def load_model():
    """
    Attempt to load the 'en_core_web_sm' model.
    If it's not present, raise an informative error instructing the user
    to add the 'en-core-web-sm' package in requirements.txt and redeploy.
    """
    try:
        return spacy.load("en_core_web_sm")
    except Exception as e:
        # Streamlit Cloud typically installs models from requirements; give clear instruction
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' not found. "
            "Add 'en-core-web-sm' to requirements.txt (alongside 'spacy') and redeploy the app."
        ) from e

try:
    nlp = load_model()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

# ---------------------------
# Utility functions (from your original code)
# ---------------------------
def clean_text_for_excel(text):
    """Remove illegal characters that Excel cannot handle."""
    if not isinstance(text, str):
        return text
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')

def extract_drug_dosages(note_text):
    """Finds all drug names with dosages in mg (e.g., 'Paracetamol 500 mg')."""
    dosage_pattern = r"([A-Za-z][A-Za-z\s]+?)\s+(\d+(?:\.\d+)?)\s*mg"
    matches = re.findall(dosage_pattern, note_text, re.IGNORECASE)
    dosage_dict = {}
    for drug, mg in matches:
        drug_name = drug.strip()
        dosage_dict[drug_name] = f"{mg} mg"
    return dosage_dict

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

    # --- spaCy NLP entities (keeps short entities) ---
    doc = nlp(note_text)
    for ent in doc.ents:
        # Only include short entity text to avoid huge blobs as values
        if ent.label_ not in structured_data and len(ent.text.split()) < 10:
            # Use label + a numeric suffix if label repeats to avoid key collision
            key_base = ent.label_
            key = key_base
            i = 1
            while key in structured_data:
                i += 1
                key = f"{key_base}_{i}"
            structured_data[key] = ent.text

    # --- Extract sections marked with **Section Title** (your pattern) ---
    section_pattern = r"\*\*(.*?)\*\*\s*([\s\S]*?)(?=\n\*\*|$)"
    sections = re.findall(section_pattern, note_text)
    for title, content in sections:
        structured_data[title.strip()] = content.strip()

    # --- Add detected drug dosages ---
    drug_dosages = extract_drug_dosages(note_text)
    structured_data.update(drug_dosages)

    # --- Clean all text for Excel-friendly output ---
    structured_data = {k: clean_text_for_excel(v) for k, v in structured_data.items()}

    return structured_data

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("Clinical Note Structuring Tool")
st.markdown(
    """
Paste an unstructured clinical note in the box below and click **Process Note**.
The app will extract structured fields and provide a CSV (Excel-compatible) download.
"""
)

clinical_text = st.text_area("Clinical Note", height=320, placeholder="Paste clinical note here...")

col1, col2 = st.columns([1, 1])
with col1:
    process_btn = st.button("Process Note")
with col2:
    clear_btn = st.button("Clear")

if clear_btn:
    # Clear the text area by re-running with empty input (Streamlit limitation: this just instructs user)
    st.experimental_rerun()

if process_btn:
    if not clinical_text.strip():
        st.warning("Please paste a clinical note before processing.")
    else:
        with st.spinner("Processing note..."):
            structured_data = extract_structured_data(clinical_text)

        if not structured_data:
            st.error("No structured data extracted. Try a different note or adjust input format.")
        else:
            # Convert to DataFrame (one row; keys become columns)
            df = pd.DataFrame([structured_data])

            st.success("Processing complete — preview below.")
            st.dataframe(df, use_container_width=True)

            # Offer CSV download
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV (Excel compatible)",
                data=csv_bytes,
                file_name="Structured_Clinical_Note.csv",
                mime="text/csv"
            )

            # Offer Excel download if openpyxl is available
            try:
                import openpyxl  # just to check availability
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="StructuredNote")
                towrite.seek(0)
                st.download_button(
                    label="Download Excel (.xlsx)",
                    data=towrite,
                    file_name="Structured_Clinical_Note.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception:
                st.info("Excel download not available (openpyxl not installed). CSV is provided and can be opened in Excel.")

# Optional: show a short example/help expander
with st.expander("Example input & tips"):
    st.markdown(
        """
- You can mark sections in your note like **History** or **Plan** using `**Section Title**` and the app will extract the section text.
- The app looks for common symptom keywords (rhinorrhea, cough, fever, etc.) and basic duration strings ("for the past 3 days").
- Drug dosages of the form `DrugName 500 mg` will be captured as separate fields.
- spaCy entities are extracted and added as columns (short entities only).
"""
    )
