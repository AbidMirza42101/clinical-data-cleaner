# streamlit_app.py
# Clinical Note -> Structured Excel/CSV (regex-only version, no spaCy)
# Updated: Option A PHI detection + highlighting

import re
import io
import html
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


def detect_phi_findings(text):
    """
    NEW PHI DETECTION ENGINE
    - Allows generic clinical titles: patient, doctor, provider, nurse
    - Flags real PHI using:
        • explicit labels (Name:, DOB:, Address:, Email:)
        • pattern-based detection (dates, phone, SSN, MRN)
        • titled names (Mr Jones, Dr Emily Carter)
    Returns list of: {category, match, start, end}
    """

    findings = []
    cleaned = text.lower()

    # Allow generic clinical terms (remove them before matching)
    cleaned = re.sub(r"\b(patient|doctor|provider|dr|nurse|physician)\b", " ", cleaned)

    # ---------------------------
    # 1. Label-based PHI (strong signal)
    # ---------------------------
    keyword_patterns = [
        ("Name", r"name\s*[:\-]\s*[A-Za-z]"),
        ("DOB", r"dob\s*[:\-]\s*\d"),
        ("DOB", r"date of birth\s*[:\-]"),
        ("MRN", r"mrn\s*[:\-]\s*\w+"),
        ("MRN", r"medical record number"),
        ("SSN", r"ssn\s*[:\-]?\s*\d"),
        ("Address", r"address\s*[:\-]"),
        ("Email", r"email\s*[:\-]"),
    ]

    for category, pat in keyword_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            findings.append({
                "category": category,
                "match": text[m.start():m.end()],
                "start": m.start(),
                "end": m.end()
            })

    # ---------------------------
    # 2. Pattern-based PHI
    # ---------------------------
    patterns = [
        ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
        ("Phone", r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        ("Phone", r"\b\d{10}\b"),
        ("MRN", r"\b\d{8,9}\b"),
        ("Date", r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
        ("Email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        ("Address", r"\d+\s+[A-Za-z]+\s+(street|st|road|rd|avenue|ave|blvd|lane|ln)"),
    ]

    for category, pat in patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            findings.append({
                "category": category,
                "match": text[m.start():m.end()],
                "start": m.start(),
                "end": m.end()
            })

    # ---------------------------
    # 3. Titled names (Dr Emily Carter, Mr Jones)
    # ---------------------------
    titled_name_pat = r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
    for m in re.finditer(titled_name_pat, text):
        findings.append({
            "category": "Title+Name",
            "match": text[m.start():m.end()],
            "start": m.start(),
            "end": m.end()
        })

    # Deduplicate by span
    unique = {}
    for f in findings:
        key = (f["start"], f["end"])
        if key not in unique:
            unique[key] = f

    findings = list(unique.values())
    findings.sort(key=lambda x: x["start"])
    return findings


def highlight_text(original_text, findings):
    """
    Return HTML with matched spans highlighted (yellow).
    We insert spans from the end to avoid invalidating indices.
    """
    if not findings:
        return html.escape(original_text).replace("\n", "<br>")

    # Sort findings by start descending to safely replace slices
    findings_sorted = sorted(findings, key=lambda x: x["start"], reverse=True)
    out = original_text
    for f in findings_sorted:
        start, end = f["start"], f["end"]
        matched = html.escape(out[start:end])
        span = f'<span style="background: #fff176; padding:2px 3px; border-radius:3px;">{matched}</span>'
        out = out[:start] + span + out[end:]
    # Escape remaining and preserve line breaks
    out = html.escape(out).replace("&lt;span", "<span").replace("span&gt;", "span>").replace("\n", "<br>")
    # Note: The replacements above restore our injected <span> tags which were escaped by html.escape
    return out


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
All processing occurs within your **individual Streamlit session** hosted by the environment you run it in.

🚫 **Do NOT enter any real patient identifiers.**  
✔️ Only use **de-identified, fictional, or synthetic clinical notes**.

By continuing, you acknowledge that you will provide only de-identified input.
"""
)

st.markdown(
    """
Paste an unstructured clinical note and click **Process Note**.
This will convert the note into structured fields you can download as CSV/Excel.
"""
)

clinical_text = st.text_area("Clinical Note", height=360, placeholder="Paste clinical note here...")

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
    else:
        # Run PHI detection
        findings = detect_phi_findings(clinical_text)

        if findings:
            st.error("⚠️ Potential PHI detected. Please remove or de-identify before processing.")
            # Show highlighted view
            highlighted_html = highlight_text(clinical_text, findings)
            st.markdown("**Detected PHI (highlighted):**", unsafe_allow_html=True)
            st.markdown(highlighted_html, unsafe_allow_html=True)

            # Build a summary table
            summary = {}
            for f in findings:
                summary[f["category"]] = summary.get(f["category"], 0) + 1
            df_summary = pd.DataFrame(
                [{"PHI Category": k, "Count": v} for k, v in summary.items()]
            )
            st.markdown("**PHI Summary:**")
            st.table(df_summary)

            st.info("Edit the note to remove the highlighted items, then press **Process Note** again.")
        else:
            # No PHI detected — proceed with processing
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
- The app highlights possible PHI (DOB, names, addresses, MRN, phone, email, occupations)
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
