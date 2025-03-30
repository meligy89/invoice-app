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

# Display logo in app (top of page)
logo_path = "logo.png"
if os.path.exists(logo_path):
    st.image(logo_path, width=150)

st.title("💸 Yalla Split & Pay")
st.write("Take or upload a photo of your invoice, choose your items, and get your share!")

# --- Upload OR Take Photo ---
st.write("📸 Upload a receipt or take a photo")
uploaded_image = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg"])
camera_image = st.camera_input("Or take a photo")

image = None
if uploaded_image:
    image = Image.open(uploaded_image)
elif camera_image:
    image = Image.open(camera_image)

if image:
    st.image(image, caption="Your Image", use_column_width=True)

    with st.spinner("🧠 Extracting items from invoice..."):
        df = extract_items(image)

    if not df.empty:
        st.success("✅ Items extracted successfully!")
        st.write("### 🛒 Select your items")

        selected_rows = st.multiselect(
            "Select what you personally ordered:",
            options=df.index,
            format_func=lambda i: f"{df.at[i, 'Qty']}x {df.at[i, 'Item']} - EGP {df.at[i, 'Total (EGP)']:.2f}"
        )

        if selected_rows:
            df_selected = df.loc[selected_rows]
            st.dataframe(df_selected)

            st.subheader("💰 Your Personal Summary")
            service_charge = st.number_input("Service Charge %", value=12.0, key="your_service")
            vat = st.number_input("VAT %", value=14.0, key="your_vat")
            tip = st.number_input("Optional Tip (EGP)", value=0.0, key="your_tip")

            personal_subtotal = df_selected["Total (EGP)"].sum()
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
        st.warning("⚠️ No items were detected. Try a clearer image.")
