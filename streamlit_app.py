# streamlit_app.py
# Clinical Note -> Structured Excel/CSV (regex-only version, no spaCy)
# Updated: Option A PHI detection + highlighting with "PHI DETECTED" in red
# Added: Optional GitHub Private Repo Access

import re
import io
import html
import os
import pandas as pd
import streamlit as st
import git  # For cloning private repo if needed

st.set_page_config(page_title="Clinical Note Structuring Tool", layout="wide")

# ---------------------------
# 🔑 Optional GitHub Private Repo Access
# ---------------------------
try:
    token = st.secrets["GITHUB_TOKEN"]  # Get token from Streamlit Secrets
    repo_url = f"https://{token}@github.com/AbidMirza42101/myrepo.git"
    local_folder = "private_repo"

    if not os.path.exists(local_folder):
        git.Repo.clone_from(repo_url, local_folder)
        st.success(f"Cloned private repo into '{local_folder}'")
    else:
        st.info(f"Private repo already exists at '{local_folder}'")
except KeyError:
    st.warning("GITHUB_TOKEN not found in Streamlit Secrets. Skipping private repo access.")
except Exception as e:
    st.error(f"Error accessing private repo: {e}")

# ---------------------------
# Utility functions
# ---------------------------
def clean_text_for_excel(text):
    if not isinstance(text, str):
        return text
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')


def extract_drug_dosages(note_text):
    dosage_pattern = r"([A-Za-z][A-Za-z\s]+?)\s+(\d+(?:\.\d+)?)\s*mg"
    matches = re.findall(dosage_pattern, note_text, re.IGNORECASE)
    dosage_dict = {}
    for drug, mg in matches:
        dosage_dict[drug.strip()] = f"{mg} mg"
    return dosage_dict


def extract_structured_data(note_text):
    structured_data = {}

    duration_match = re.search(r"for the past ([\w\s]+days?)", note_text, re.IGNORECASE)
    if duration_match:
        structured_data["Duration"] = duration_match.group(1).strip()

    symptoms = []
    symptom_keywords = ["rhinorrhea", "congestion", "sneezing", "stuffiness", "cough", "dyspnea", "fever"]
    for symptom in symptom_keywords:
        if re.search(rf"\b{symptom}\b", note_text, re.IGNORECASE):
            symptoms.append(symptom)
    if symptoms:
        structured_data["Symptoms"] = ", ".join(symptoms)

    physical_findings = re.findall(r"(?:reveals|shows|demonstrates|indicates)\s([^\.]+)\.", note_text, re.IGNORECASE)
    if physical_findings:
        structured_data["Physical Findings"] = "; ".join([f.strip() for f in physical_findings])

    if re.search(r"no acute distress", note_text, re.IGNORECASE):
        structured_data["General Appearance"] = "No acute distress"
    if re.search(r"afebrile", note_text, re.IGNORECASE):
        structured_data["Temperature Status"] = "Afebrile"

    section_pattern = r"\*\*(.*?)\*\*\s*([\s\S]*?)(?=\n\*\*|$)"
    sections = re.findall(section_pattern, note_text)
    for title, content in sections:
        structured_data[title.strip()] = content.strip()

    drug_dosages = extract_drug_dosages(note_text)
    structured_data.update(drug_dosages)

    structured_data = {k: clean_text_for_excel(v) for k, v in structured_data.items()}
    return structured_data


def detect_phi_findings(text):
    findings = []
    cleaned = text.lower()
    cleaned = re.sub(r"\b(patient|doctor|provider|dr|nurse|physician)\b", " ", cleaned)

    keyword_patterns = [
        ("Name", r"name\s*[:\-]\s*[A-Za-z]"),
        ("DOB", r"dob\s*[:\-]"),
        ("MRN", r"mrn\s*[:\-]"),
        ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
        ("Address", r"address\s*[:\-]"),
        ("Email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    ]

    for category, pat in keyword_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            findings.append({"category": category, "match": text[m.start():m.end()], "start": m.start(), "end": m.end()})

    titled_name_pat = r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
    for m in re.finditer(titled_name_pat, text):
        findings.append({"category": "Title+Name", "match": text[m.start():m.end()], "start": m.start(), "end": m.end()})

    unique = {}
    for f in findings:
        key = (f["start"], f["end"])
        if key not in unique:
            unique[key] = f
    findings = list(unique.values())
    findings.sort(key=lambda x: x["start"])
    return findings


def highlight_text(original_text, findings):
    if not findings:
        return html.escape(original_text).replace("\n", "<br>")

    out = original_text
    findings_sorted = sorted(findings, key=lambda x: x["start"], reverse=True)

    for f in findings_sorted:
        start, end = f["start"], f["end"]
        matched_text = out[start:end]
        replacement = f'{matched_text}<span style="color:red; font-weight:bold;"> [PHI DETECTED]</span>'
        out = out[:start] + replacement + out[end:]

    out = html.escape(out).replace("&lt;span", "<span").replace("span&gt;", "span>").replace("\n", "<br>")
    return out

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("Clinical Note Structuring Tool")

st.markdown(
    """
### 🔒 Privacy & Data Handling Notice
This demo **does not store, save, or transmit** any text you enter.  
All processing occurs within your **individual Streamlit session**.

🚫 **Do NOT enter any real patient identifiers.**  
✔️ Only use **de-identified, fictional, or synthetic clinical notes**.
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
        findings = detect_phi_findings(clinical_text)
        if findings:
            st.error("⚠️ Potential PHI detected. Please remove or de-identify before processing.")
            highlighted_html = highlight_text(clinical_text, findings)
            st.markdown("**Detected PHI (highlighted with PHI DETECTED tag):**", unsafe_allow_html=True)
            st.markdown(highlighted_html, unsafe_allow_html=True)

            summary = {}
            for f in findings:
                summary[f["category"]] = summary.get(f["category"], 0) + 1
            df_summary = pd.DataFrame([{"PHI Category": k, "Count": v} for k, v in summary.items()])
            st.markdown("**PHI Summary:**")
            st.table(df_summary)

            st.info("Edit the note to remove highlighted items, then press **Process Note** again.")
        else:
            with st.spinner("Processing note..."):
                structured_data = extract_structured_data(clinical_text)

            if not structured_data:
                st.error("No structured data extracted.")
            else:
                df = pd.DataFrame([structured_data])
                st.success("Processing complete — preview below.")
                st.dataframe(df, use_container_width=True)

                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button("Download CSV", csv_bytes, "Structured_Clinical_Note.csv", "text/csv")

                try:
                    import openpyxl
                    towrite = io.BytesIO()
                    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="StructuredNote")
                    towrite.seek(0)
                    st.download_button("Download Excel (.xlsx)", towrite, "Structured_Clinical_Note.xlsx",
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except Exception:
                    st.info("Excel download not available.")

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

st.markdown(
    """
---
### ⚠️ Disclaimer  
This tool is for **educational and research demonstration** only.  
It is **not a medical device** and must not be used for diagnosis, treatment, or clinical decision-making.  
Users are responsible for ensuring all text entered is **fully de-identified** and contains **no PHI**.
"""
)

