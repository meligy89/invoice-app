import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter
import pandas as pd
import numpy as np
import re
from fpdf import FPDF
import tempfile
import os
import yagmail
from paddleocr import PaddleOCR

# --- Initialize PaddleOCR ---
ocr_engine = PaddleOCR(use_angle_cls=True, lang='en')

# --- OCR Helper Functions ---
def enhance_image(image):
    image = image.convert('L')
    image = image.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(2)

# --- PaddleOCR-powered Item Extractor ---
def extract_items(image):
    image = enhance_image(image)
    image_np = np.array(image)

    result = ocr_engine.ocr(image_np, cls=True)
    text_lines = [line[1][0] for line in result[0] if line[1][0].strip()]
    items = []

    ignore_keywords = ["subtotal", "vat", "total", "service", "thank", "count", "cash", "payment", "balance", "%", "tip", "delivery"]
    currency_variants = ["EGP", "LE", "L.E.", "L.E", "جنيه"]

    for i, line in enumerate(text_lines):
        if any(x.lower() in line.lower() for x in ignore_keywords):
            continue

        for cur in currency_variants:
            line = line.replace(cur, "EGP")

        price_match = re.search(r'(EGP)?\s*([\d,]+\.\d{2})\s*(EGP)?', line, re.IGNORECASE)
        if not price_match:
            continue

        price = float(price_match.group(2).replace(',', ''))
        line_clean = re.sub(r'(EGP)?\s*[\d,]+\.\d{2}\s*(EGP)?', '', line, flags=re.IGNORECASE).strip()

        qty = 1
        item_name = ""
        qty_match = re.match(r'^(\d+)[\s\-_.xX*]*(.*)', line_clean)
        if qty_match:
            try:
                qty = int(qty_match.group(1))
            except:
                qty = 1
            item_name = qty_match.group(2)
        else:
            if i > 0:
                prev_line = text_lines[i - 1]
                if not any(x.lower() in prev_line.lower() for x in ignore_keywords):
                    item_name = prev_line
            else:
                item_name = line_clean

        item_name = re.sub(r'[^\w\s]', '', item_name)
        item_name = ' '.join(item_name.split())
        item_name = item_name.title()

        unit_price = round(price / qty, 2) if qty > 0 else price

        items.append({
            "Item": item_name if item_name else "Unnamed Item",
            "Qty (Invoice)": qty,
            "Unit Price (EGP)": unit_price,
            "Total (EGP)": price
        })

    return pd.DataFrame(items)

# --- PDF Generator ---
def generate_pdf(df_selected, summary, per_person, filename="invoice.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    logo_path = "logo.png"
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=33)
        pdf.ln(30)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Invoice Summary", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.ln(5)

    for index, row in df_selected.iterrows():
        pdf.cell(200, 10, txt=f"{row['Item']} - Qty: {row['Qty']} - Unit: {row['Unit Price (EGP)']} - Total: {row['Total (EGP)']}", ln=True)

    pdf.ln(5)
    for k, v in summary.items():
        pdf.cell(200, 10, txt=f"{k}: EGP {v:.2f}", ln=True)

    pdf.cell(200, 10, txt=f"Split per person: EGP {per_person:.2f}", ln=True)

    path = os.path.join(tempfile.gettempdir(), filename)
    pdf.output(path)
    return path

# --- Email Invoice ---
def send_email(recipient, subject, body, attachment_path):
    sender = os.environ.get("EMAIL_USER")
    password = os.environ.get("EMAIL_PASS")
    if not sender or not password:
        st.error("Email credentials not set in environment variables.")
        return
    yag = yagmail.SMTP(sender, password)
    yag.send(to=recipient, subject=subject, contents=body, attachments=attachment_path)
    return True

# --- Streamlit UI ---
st.set_page_config(page_title="Yalla Split & Pay", layout="wide")
st.markdown("<style>body { font-family: 'Arial', sans-serif; }</style>", unsafe_allow_html=True)

st.image("logo.png", width=150)
st.title("Yalla Split & Pay")

uploaded_file = st.file_uploader("Upload Invoice Image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    df = extract_items(image)

    if df.empty:
        st.warning("No valid items found. Try uploading a clearer image.")

        st.subheader("📋 Manually Enter Items")
        num_manual_items = st.number_input("How many items do you want to enter?", min_value=1, step=1, value=1)
        manual_items = []

        for i in range(num_manual_items):
            with st.expander(f"Item {i + 1}"):
                item_name = st.text_input(f"Item Name {i + 1}", key=f"name_{i}")
                qty = st.number_input(f"Quantity {i + 1}", min_value=1, step=1, value=1, key=f"qty_{i}")
                unit_price = st.number_input(f"Unit Price (EGP) {i + 1}", min_value=0.0, step=0.1, value=0.0, key=f"price_{i}")
                total = round(qty * unit_price, 2)
                manual_items.append({
                    "Item": item_name.title(),
                    "Qty": qty,
                    "Unit Price (EGP)": unit_price,
                    "Total (EGP)": total
                })

        if manual_items:
            df_selected = pd.DataFrame(manual_items)
    else:
        st.subheader("Extracted Items")
        st.dataframe(df)

        st.subheader("Select Items Taken")
        selected_rows = st.multiselect("Select item rows:", df.index)

        selected_items = []
        for idx in selected_rows:
            item = df.loc[idx]
            qty = st.number_input(f"How many of '{item['Item']}'?", min_value=1, max_value=item["Qty (Invoice)"], value=1)
            total = qty * item["Unit Price (EGP)"]
            selected_items.append({
                "Item": item["Item"],
                "Qty": qty,
                "Unit Price (EGP)": item["Unit Price (EGP)"],
                "Total (EGP)": round(total, 2)
            })

        df_selected = pd.DataFrame(selected_items) if selected_items else None

    if 'df_selected' in locals() and not df_selected.empty:
        st.subheader("Your Selections")
        st.dataframe(df_selected)

        tip = st.number_input("Optional Tip (EGP)", min_value=0.0, value=0.0)
        people = st.number_input("Split between how many people?", min_value=1, step=1, value=1)

        base = df_selected["Total (EGP)"].sum()
        service = round(base * 0.12, 2)
        subtotal = round(base + service, 2)
        vat = round(subtotal * 0.14, 2)
        final = round(subtotal + vat + tip, 2)
        per_person = round(final / people, 2)

        summary = {
            "Base Total": base,
            "Service (12%)": service,
            "Subtotal": subtotal,
            "VAT (14%)": vat,
            "Tip": tip,
            "Final Total": final
        }

        st.subheader("Bill Summary")
        for k, v in summary.items():
            st.write(f"{k}: EGP {v:.2f}")
        st.success(f"Each Person Pays: EGP {per_person:.2f}")

        if st.button("Generate PDF Invoice"):
            pdf_path = generate_pdf(df_selected, summary, per_person)
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", f, file_name="invoice.pdf", mime="application/pdf")

        st.subheader("Email Invoice")
        email_to = st.text_input("Recipient Email")
        if st.button("Send Email") and email_to:
            if send_email(email_to, "Your Invoice", "Please find your invoice attached.", pdf_path):
                st.success("Invoice emailed successfully.")
