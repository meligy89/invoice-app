import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract
import pandas as pd
import re
from fpdf import FPDF
import tempfile
import os
import yagmail

# --- Enhance and OCR ---
def enhance_image(image):
    image = image.convert('L')
    image = image.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(2)

import re
import pandas as pd
import pytesseract
from PIL import ImageEnhance, ImageFilter

def extract_items(image):
    # Enhance image for OCR
    image = image.convert('L')
    image = image.filter(ImageFilter.SHARPEN)
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(2)

    # Extract OCR text
    text = pytesseract.image_to_string(image)
    
    # Debug outputs (comment out if not needed)
    # import streamlit as st
    # st.subheader("🔍 OCR Debug Output")
    # st.text(text)
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Debug: show cleaned lines for parsing
    # st.write("🧾 Cleaned Lines for Parsing:", lines)
    
    items = []

    # Loop through lines to parse items
    for i, line in enumerate(lines):
        # Only consider lines containing EGP that aren't summary lines
        if "EGP" in line and not any(x in line for x in ["Subtotal", "Service", "Total", "VAT", "%", "Count"]):
            # Extract price using a regex pattern
            price_match = re.search(r'EGP\s*([\d,]+\.\d{2})', line)
            if not price_match:
                continue
            price = float(price_match.group(1).replace(',', ''))

            # Remove price portion from line
            line_clean = re.sub(r'EGP\s*[\d,]+\.\d{2}', '', line).strip()
            
            qty = 1
            item_name = ""
            
            # Try to extract quantity and item from the current line
            qty_match = re.match(r'^(\d+)[\s\-_.]*(.*)', line_clean)
            if qty_match:
                try:
                    qty = int(qty_match.group(1))
                except:
                    qty = 1
                item_name = qty_match.group(2)
            # Fallback: check previous line if not found in current line
            elif i > 0:
                prev_line = lines[i - 1]
                prev_match = re.match(r'^(\d+)[\s\-_.]*(.*)', prev_line)
                if prev_match:
                    try:
                        qty = int(prev_match.group(1))
                    except:
                        qty = 1
                    item_name = prev_match.group(2)
                else:
                    item_name = line_clean
            else:
                item_name = line_clean

            # Clean item name: remove non-alphanumeric characters (except spaces) and normalize spaces
            item_name = re.sub(r'[^\w\s]', '', item_name)
            item_name = ' '.join(item_name.split())
            item_name = item_name.title()  # Convert to title case

            # Calculate unit price
            unit_price = round(price / qty, 2) if qty > 0 else price

            items.append({
                "Item": item_name,
                "Qty (Invoice)": qty,
                "Unit Price (EGP)": unit_price,
                "Total (EGP)": price
            })

    return pd.DataFrame(items)

# --- PDF Generator with Logo and Sans-Serif Font ---
def generate_pdf(df_selected, summary, per_person, filename="invoice.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Logo
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

# --- Send Email ---
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
st.set_page_config(page_title="Invoice Splitter", layout="wide")
st.markdown("<style>body { font-family: 'Arial', sans-serif; }</style>", unsafe_allow_html=True)

st.image("logo.png", width=150)
st.title("Yalla Split")

uploaded_file = st.file_uploader("Upload Invoice Image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    df = extract_items(image)

    if df.empty:
        st.warning("No valid items found.")
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

        if selected_items:
            df_selected = pd.DataFrame(selected_items)
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
