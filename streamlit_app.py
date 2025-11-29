import streamlit as st
import pandas as pd

st.set_page_config(page_title="Clinical Note Structuring Tool")

st.title("Clinical Note Structuring Tool")
st.write("Paste your unstructured clinical note below:")

clinical_text = st.text_area("Clinical Note", height=250)

if st.button("Process Note"):
    if clinical_text.strip() == "":
        st.warning("Please paste a clinical note.")
    else:
        # Dummy output - replace with your own NLP code later
        extracted_data = {
            "Diagnosis": ["Hypertension"],
            "Medications": ["Lisinopril"],
            "Allergies": ["None"],
            "Procedures": ["Blood Test"]
        }

        df = pd.DataFrame(extracted_data)
        st.success("Processing complete!")
        st.dataframe(df)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Excel File",
            data=csv,
            file_name="structured_output.csv",
            mime="text/csv"
        )
