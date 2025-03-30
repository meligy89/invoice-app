import streamlit as st
from PIL import Image
import pandas as pd
import pytesseract
import re
from fpdf import FPDF
import tempfile
import os
import io
import yagmail

# --- OCR with Tesseract ---
def extract_text_tesseract(image):
    text = pytesseract.image_to_string(image)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return lines

# --- Extract Items ---
def extract_items(image):
    text_lines = extract_text_tesseract(image)
    ignore_keywords = ["subtotal", "vat", "total", "service", "thank", "count", "cash", "payment", "balance", "%", "tip", "delivery"]
    currency_variants = ["EGP", "LE", "L.E.", "L.E", "\u062c\u0646\u064a\u0647"]

    items = []

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
            "Qty": qty,
            "Unit Price (EGP)": unit_price,
            "Total (EGP)": price
        })

    return pd.DataFrame(items)

# --- PDF Generator ---
def generate_pdf(df_selected, summary, per_person, filename="invoice.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # --- Add Logo if available ---
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

    pdf.cell(200, 10, txt=f"Split per person: EGP {per_person:.2f}", ln=True)

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

# Display logo in app (top of page)
logo_path = "logo.png"
if os.path.exists(logo_path):
    st.image(logo_path, width=150)

st.title("💸 Yalla Split & Pay")
st.write("Upload your invoice image, extract items, split the bill, and send via email!")

uploaded_image = st.file_uploader("📸 Upload an invoice image", type=["png", "jpg", "jpeg"])

if uploaded_image:
    image = Image.open(uploaded_image)
    st.image(image, caption="Uploaded Image", use_container_width=True)

    with st.spinner("🧠 Extracting items from invoice..."):
        df = extract_items(image)

    if not df.empty:
        st.success("✅ Items extracted successfully!")
        st.dataframe(df)

        st.subheader("🔢 Invoice Summary")
        service_charge = st.number_input("Service Charge %", value=12.0)
        vat = st.number_input("VAT %", value=14.0)
        tip = st.number_input("Optional Tip (EGP)", value=0.0)

        subtotal = df["Total (EGP)"].sum()
        service_amt = subtotal * (service_charge / 100)
        vat_amt = (subtotal + service_amt) * (vat / 100)
        total = subtotal + service_amt + vat_amt + tip

        summary = {
            "Subtotal": subtotal,
            "Service Charge": service_amt,
            "VAT": vat_amt,
            "Tip": tip,
            "Grand Total": total
        }

        st.write(summary)

        people = st.number_input("Number of People to Split With", min_value=1, value=2, step=1)
        per_person = round(total / people, 2)
        st.write(f"Each person pays: **EGP {per_person:.2f}**")

        if st.button("📄 Generate PDF Invoice"):
            pdf_path = generate_pdf(df, summary, per_person)
            with open(pdf_path, "rb") as f:
                st.download_button("Download Invoice PDF", f, file_name="invoice.pdf")

        with st.expander("📧 Send via Email"):
            email = st.text_input("Recipient Email")
            subject = st.text_input("Subject", value="Your Shared Invoice")
            body = st.text_area("Message", value="Here's your split invoice summary.")
            if st.button("Send Email"):
                pdf_path = generate_pdf(df, summary, per_person)
                result = send_email(email, subject, body, pdf_path)
                if result:
                    st.success("📤 Email sent successfully!")
                else:
                    st.error("Failed to send email.")
    else:
        st.warning("⚠️ No items were detected. Try a clearer image.")
