# streamlit_app.py
# Clinical Note -> Structured Excel/CSV (regex-only version, no spaCy)

import re
import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Clinical Note Structuring Tool", layout="wide")

# ---------------------------
# Utility functions
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

    # --- Extract sections ---
    section_pattern = r"\*\*(.*?)\*\*\s*([\s\S]*?)(?=\n\*\*|$)"
    sections = re.findall(section_pattern, note_text)
    for title, content in sections:
        structured_data[title.strip()] = content.strip()

    # --- Add detected drug dosages ---
    drug_dosages = extract_drug_dosages(note_text)
    structured_data.update(drug_dosages)

    # --- Clean for Excel ---
    structured_data = {k: clean_text_for_excel(v) for k, v in structured_data.items()}

    return structured_data

# ---------------------------
# PHI Detection (Optional but recommended)
# ---------------------------
def contains_phi(text):
    forbidden = ["name:", "mrn", "dob", "phone", "address", "patient:"]
    return any(term in text.lower() for term in forbidden)

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("Clinical Note Structuring Tool")

# ---------------------------
# 🔒 Privacy & Data Handling Notice
# ---------------------------
st.markdown(
    """
### 🔒 Privacy & Data Handling Notice
This demo **does not store, save, or transmit** any text you enter.  
All processing occurs within your **individual Streamlit session**.

🚫 **Do NOT enter any real patient identifiers.**  
✔️ Only use **de-identified, fictional, or synthetic clinical notes.**

By continuing, you acknowledge that you will provide only de-identified input.
"""
)

st.markdown(
    """
Paste an unstructured clinical note and click **Process Note**.
This will convert the note into structured fields you can download as CSV/Excel.
"""
)

clinical_text = st.text_area("Clinical Note", height=320, placeholder="Paste clinical note here...")

col1, col2 = st.columns([1, 1])
with col1:
    process_btn = st.button("Process Note")
with col2:
    clear_btn = st.button("Clear")

if clear_btn:
    st.experimental_rerun()

if process_btn:
    if not clinical_text.strip():
        st.warning("Please paste a clinical note before processing.")
    elif contains_phi(clinical_text):
        st.error("⚠️ PHI detected. Please remove real patient identifiers before proceeding.")
    else:
        with st.spinner("Processing note..."):
            structured_data = extract_structured_data(clinical_text)

        if not structured_data:
            st.error("No structured data extracted.")
        else:
            df = pd.DataFrame([structured_data])

            st.success("Processing complete — preview below.")
            st.dataframe(df, use_container_width=True)

            # CSV download
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=csv_bytes,
                file_name="Structured_Clinical_Note.csv",
                mime="text/csv",
            )

            # Excel download
            try:
                import openpyxl
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="StructuredNote")
                towrite.seek(0)
                st.download_button(
                    label="Download Excel (.xlsx)",
                    data=towrite,
                    file_name="Structured_Clinical_Note.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception:
                st.info("Excel download not available.")

# Example
with st.expander("Example input & tips"):
    st.markdown(
        """
- Use `**History**` style formatting for section extraction.
- App detects durations: “for the past 3 days”
- App detects symptoms: cough, fever, congestion, etc.
- App detects drug dosages like: Amoxicillin 500 mg
"""
    )

# ---------------------------
# ⚠️ Disclaimer (at the very bottom)
# ---------------------------
st.markdown(
    """
---
### ⚠️ Disclaimer  
This tool is for **educational and research demonstration** only.  
It is **not a medical device** and must not be used for diagnosis, treatment, or clinical decision-making.  
Users are responsible for ensuring all text entered is **fully de-identified** and contains **no PHI**.
"""
)
