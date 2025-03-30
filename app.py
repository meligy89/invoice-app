import streamlit as st
from PIL import Image, ImageEnhance
import pandas as pd
import pytesseract
import re
from fpdf import FPDF
import tempfile
import os
import io
import yagmail
import json
from openai import OpenAI
import numpy as np

# --- OpenAI Client Setup ---
client = OpenAI(api_key=st.secrets["openai_api_key"] if "openai_api_key" in st.secrets else os.getenv("OPENAI_API_KEY"))

# --- OCR with Tesseract ---
def extract_text_tesseract(image):
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    elif not isinstance(image, Image.Image):
        image = Image.open(image)

    image = image.convert("L")
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2.0)

    text = pytesseract.image_to_string(image)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return lines

# --- GPT Parsing ---
def parse_with_gpt(text_lines):
    prompt = (
        "You are an intelligent invoice parser. From the following lines, extract items with:\n"
        "- Item (string)\n- Qty (int)\n- Unit Price (float)\n- Total (float)\n\n"
        "Return a valid JSON array, like:\n"
        "[{\"Item\": \"سلطة طحينة\", \"Qty\": 2, \"Unit Price\": 40.0, \"Total\": 80.0}]\n\n"
        f"Lines:\n{chr(10).join(text_lines)}"
    )

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    content = response.choices[0].message.content
    st.subheader("🧠 GPT Raw Response")
    st.code(content)

    try:
        data = json.loads(content)
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Failed to parse GPT output: {e}")
        return pd.DataFrame()

# --- PDF Generator ---
def generate_pdf(df_selected, summary, per_person, filename="invoice.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    logo_path = "logo.png"
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=40)
        pdf.ln(30)
    else:
        pdf.ln(10)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Invoice Summary", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(5)

    for index, row in df_selected.iterrows():
        pdf.cell(200, 10, txt=f"{row['Item']} - Qty: {row['Qty']} - Unit: {row['Unit Price (EGP)']} - Total: {row['Total (EGP)']}", ln=True)

    pdf.ln(5)
    for k, v in summary.items():
        pdf.cell(200, 10, txt=f"{k}: EGP {v:.2f}", ln=True)

    pdf.cell(200, 10, txt=f"Total: EGP {per_person:.2f}", ln=True)

    path = os.path.join(tempfile.gettempdir(), filename)
    pdf.output(path)
    return path

# --- Email Invoice ---
def send_email(recipient, subject, body, attachment_path):
    sender = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    if not sender or not password:
        st.error("❌ Email credentials not set in environment variables.")
        return
    yag = yagmail.SMTP(sender, password)
    yag.send(to=recipient, subject=subject, contents=body, attachments=attachment_path)
    return True

# --- Streamlit App UI ---
st.set_page_config(page_title="Yalla Split & Pay", page_icon="💸")

logo_path = "logo.png"
if os.path.exists(logo_path):
    st.image(logo_path, width=150)

st.title("💸 Yalla Split & Pay")
st.write("Upload your invoice image, extract items, choose what you had, and get your share!")

uploaded_image = st.file_uploader("📸 Upload an invoice image", type=["png", "jpg", "jpeg"])

if uploaded_image:
    image = Image.open(uploaded_image)
    st.image(image, caption="Uploaded Image", use_container_width=True)

    with st.spinner("🧠 Extracting items from invoice using GPT..."):
        text_lines = extract_text_tesseract(image)
        df = parse_with_gpt(text_lines)

    if not df.empty:
        st.success("✅ Items extracted successfully!")
        st.write("### 🛒 Select your items")

        selected_rows = st.multiselect(
            "Select what you personally ordered:",
            options=df.index,
            format_func=lambda i: f"{df.at[i, 'Qty']}x {df.at[i, 'Item']} - EGP {df.at[i, 'Total']:.2f}"
        )

        if selected_rows:
            df_selected = df.loc[selected_rows]
            st.dataframe(df_selected)

            st.subheader("💰 Your Personal Summary")
            service_charge = st.number_input("Service Charge %", value=12.0, key="your_service")
            vat = st.number_input("VAT %", value=14.0, key="your_vat")
            tip = st.number_input("Optional Tip (EGP)", value=0.0, key="your_tip")

            personal_subtotal = df_selected["Total"].sum()
            personal_service = personal_subtotal * (service_charge / 100)
            personal_vat = (personal_subtotal + personal_service) * (vat / 100)
            personal_total = personal_subtotal + personal_service + personal_vat + tip

            summary = {
                "Subtotal": personal_subtotal,
                "Service Charge": personal_service,
                "VAT": personal_vat,
                "Tip": tip,
                "Total Due": personal_total
            }

            st.write(summary)
            st.markdown(f"### 💸 You Owe: **EGP {personal_total:.2f}**")

            if st.button("📄 Generate Your Invoice PDF"):
                pdf_path = generate_pdf(df_selected, summary, per_person=personal_total)
                with open(pdf_path, "rb") as f:
                    st.download_button("Download Your PDF", f, file_name="my_invoice.pdf")

            with st.expander("📧 Send Your Invoice by Email"):
                email = st.text_input("Your Email")
                subject = st.text_input("Email Subject", value="My Split Invoice")
                body = st.text_area("Email Body", value="Here’s the part I’m paying for.")
                if st.button("Send My Part via Email"):
                    pdf_path = generate_pdf(df_selected, summary, per_person=personal_total)
                    result = send_email(email, subject, body, pdf_path)
                    if result:
                        st.success("📤 Email sent successfully!")
        else:
            st.info("Select the items you personally ordered to see your total.")
    else:
        st.warning("⚠️ No items were detected. Try a clearer image or check the GPT response above.")
