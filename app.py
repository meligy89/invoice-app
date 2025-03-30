import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
from fpdf import FPDF
import io
import openai
import os

# Set your OpenAI API key here or in Streamlit Secrets
openai.api_key = st.secrets["openai_api_key"] if "openai_api_key" in st.secrets else os.getenv("OPENAI_API_KEY")

# ---------- OCR TEXT EXTRACTION ----------
def extract_text_tesseract(image):
    text = pytesseract.image_to_string(image)
    return text.split('\n')

# ---------- GPT PARSING ----------
def parse_with_gpt(text_lines):
    prompt = (
        "You are a helpful assistant extracting itemized invoice data. "
        "From the following lines, extract a JSON list of items with: Item, Qty, Unit Price, Total. "
        "Ensure multiline items are grouped together.\n\n"
        "Example Output:\n"
        "[{'Item': 'Chicken Shawarma with garlic sauce', 'Qty': 2, 'Unit Price': 6.25, 'Total': 12.50}, ...]\n\n"
        f"Lines:\n{chr(10).join(text_lines)}"
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response["choices"][0]["message"]["content"]
    try:
        data = eval(content, {}, {})
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Failed to parse GPT output: {e}")
        return pd.DataFrame()

# ---------- PDF EXPORT ----------
def export_to_pdf(df, tip_percentage, total_amount, per_person, num_people):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Yalla Split & Pay Invoice", ln=True, align='C')
    pdf.ln(10)

    for index, row in df.iterrows():
        line = f"{row['Qty']} x {row['Item']} @ {row['Unit Price']:.2f} = {row['Total']:.2f}"
        pdf.cell(200, 10, txt=line, ln=True)

    pdf.ln(5)
    pdf.cell(200, 10, txt=f"Tip: {tip_percentage}%", ln=True)
    pdf.cell(200, 10, txt=f"Grand Total: {total_amount:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Split among {num_people} people: {per_person:.2f} each", ln=True)

    output = io.BytesIO()
    pdf.output(output)
    return output

# ---------- STREAMLIT UI ----------
st.title("🧾 Yalla Split & Pay (AI-Powered)")
st.write("Upload an invoice image. AI will extract and split the bill. You can review and edit items before splitting.")

uploaded_file = st.file_uploader("Choose an invoice image", type=["png", "jpg", "jpeg", "webp"])

if uploaded_file is not None:
    try:
        image = Image.open(uploaded_file)
        st.image(image, caption="Uploaded Invoice", use_column_width=True)

        text_lines = extract_text_tesseract(image)
        st.subheader("🔍 OCR Result")
        st.code("\n".join(text_lines))

        with st.spinner("Using GPT to extract items..."):
            df = parse_with_gpt(text_lines)

        if df.empty:
            st.warning("Could not detect any items. Try a clearer image or check the OCR.")
        else:
            st.subheader("📝 Edit Extracted Items")
            df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

            tip_percentage = st.slider("Tip (%)", 0, 30, 10)
            num_people = st.number_input("Number of people splitting", min_value=1, value=2, step=1)

            subtotal = df["Total"].sum()
            tip_amount = subtotal * (tip_percentage / 100)
            grand_total = subtotal + tip_amount
            per_person = grand_total / num_people

            st.markdown(f"### 💵 Subtotal: {subtotal:.2f}")
            st.markdown(f"### ➕ Tip ({tip_percentage}%): {tip_amount:.2f}")
            st.markdown(f"### 🧾 Grand Total: {grand_total:.2f}")
            st.markdown(f"### 👥 Each Person Pays: {per_person:.2f}")

            if st.button("📄 Export Bill to PDF"):
                pdf_file = export_to_pdf(df, tip_percentage, grand_total, per_person, num_people)
                st.download_button(
                    label="Download PDF",
                    data=pdf_file.getvalue(),
                    file_name="yalla_split_invoice.pdf",
                    mime="application/pdf"
                )

    except Exception as e:
        st.error(f"Something went wrong: {e}")
