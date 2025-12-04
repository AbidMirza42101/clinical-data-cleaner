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


# ---------------------------
# PHI Detection (Option A) + Highlighting
# ---------------------------
PHI_KEYWORDS = {
    "Name": [
        r"\bname\b", r"\bfull name\b", r"\blast name\b", r"\bfirst name\b"
    ],
    "Address": [
        r"\baddress\b", r"\bhome address\b", r"\bresidence\b",
        r"\bstreet\b", r"\bapt\b", r"\bapartment\b", r"\bbox\b", r"\brd\b", r"\bave\b", r"\bavenue\b"
    ],
    "Date of Birth": [
        r"\bdate of birth\b", r"\bbirthdate\b", r"\bdob\b"
    ],
    "Phone Number": [
        r"\bphone\b", r"\bphone number\b", r"\bcontact number\b",
        r"\bcell\b", r"\bmobile\b", r"\btel\b", r"\btelephone\b"
    ],
    "Email": [
        r"\bemail\b", r"\bemail address\b"
    ],
    "SSN": [
        r"\bssn\b", r"\bsocial security\b"
    ],
    "Medical Record Number": [
        r"\bmrn\b", r"\bmedical record number\b"
    ],
    "Insurance": [
        r"\binsurance\b", r"\bpolicy\b", r"\bmember id\b", r"\bmember number\b"
    ],
    "Facility": [
        r"\bhospital\b", r"\bclinic\b", r"\bmedical center\b", r"\bhealth center\b"
    ],
    "Zip Code": [
        r"\bzip\b", r"\bzipcode\b", r"\bpostal code\b"
    ]
}

# Numeric / identifier patterns (also flagged)
IDENTIFIER_PATTERNS = {
    "SSN Pattern": r"\b\d{3}-\d{2}-\d{4}\b",
    "Phone Pattern": r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",
    "MRN Pattern": r"\b\d{6,12}\b"  # MRNs vary; adjust as needed
}

# Excluded generic role words (we remove them from detection only)
EXCLUDED_WORDS = {"patient", "doctor", "dr", "md", "provider", "nurse", "physician"}

def detect_phi_findings(original_text):
    """
    Returns a list of findings, each as dict:
      {category, match_text, start, end}
    """
    findings = []
    # Work on a lowercase, but we'll find positions on the original for highlighting
    # To avoid flagging generic role words, temporarily remove them for matching purposes
    temp_text = original_text
    for ex in EXCLUDED_WORDS:
        # replace whole-word occurrences only (case-insensitive)
        temp_text = re.sub(rf"\b{re.escape(ex)}\b", " ", temp_text, flags=re.IGNORECASE)

    # 1) Keyword-based detection
    for category, patterns in PHI_KEYWORDS.items():
        for pat in patterns:
            # finditer on original text (case-insensitive)
            for m in re.finditer(pat, original_text, flags=re.IGNORECASE):
                findings.append({
                    "category": category,
                    "match": original_text[m.start():m.end()],
                    "start": m.start(),
                    "end": m.end()
                })

    # 2) Identifier patterns detection (phone, ssn, mrn)
    for category, pat in IDENTIFIER_PATTERNS.items():
        for m in re.finditer(pat, original_text, flags=re.IGNORECASE):
            findings.append({
                "category": category,
                "match": original_text[m.start():m.end()],
                "start": m.start(),
                "end": m.end()
            })

    # 3) Additional name/title detection (e.g., "Mr. Jones", "Dr Emily Carter")
    # This helps catch "Mr. Jones", "Dr. Emily Carter", etc.
    name_title_patterns = [
        r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?",  # Mr. Jones  or Dr Emily Carter
    ]
    for pat in name_title_patterns:
        for m in re.finditer(pat, original_text):
            findings.append({
                "category": "Title+Name",
                "match": original_text[m.start():m.end()],
                "start": m.start(),
                "end": m.end()
            })

    # 4) Age patterns (e.g., "52-year-old", "52 year old")
    for m in re.finditer(r"\b\d{1,3}\s*[- ]?(year|yr|years)\b\s*old\b", original_text, flags=re.IGNORECASE):
        findings.append({
            "category": "Age",
            "match": original_text[m.start():m.end()],
            "start": m.start(),
            "end": m.end()
        })

    # 5) Occupation heuristics (common job words)
    occupation_terms = ["consultant", "engineer", "teacher", "developer", "driver", "nurse", "lawyer", "physician"]
    for term in occupation_terms:
        for m in re.finditer(rf"\b{re.escape(term)}\b", original_text, flags=re.IGNORECASE):
            findings.append({
                "category": "Occupation",
                "match": original_text[m.start():m.end()],
                "start": m.start(),
                "end": m.end()
            })

    # Deduplicate findings by span (if multiple rules matched same span)
    unique = {}
    for f in findings:
        key = (f["start"], f["end"])
        # If same span exists, prefer the longer category name string (arbitrary)
        if key not in unique or len(f["category"]) > len(unique[key]["category"]):
            unique[key] = f

    deduped = list(unique.values())
    # Sort by start position
    deduped.sort(key=lambda x: x["start"])
    return deduped


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
