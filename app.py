import streamlit as st
from PIL import Image
import pandas as pd
import pytesseract
import re
from fpdf import FPDF
import tempfile
import os
import yagmail

# --- OCR with Tesseract ---
def extract_text_tesseract(image):
    if not isinstance(image, Image.Image):
        image = Image.open(image)
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
        qty_match = re.match(r'^(\d+)[\s\-_.xX*]*(.*)', line_clean)
        if qty_match:
            qty = int(qty_match.group(1))
            item_name = qty_match.group(2)
        else:
            item_name = text_lines[i - 1] if i > 0 else line_clean

        item_name = re.sub(r'[^\w\s]', '', item_name).title().strip()
        unit_price = round(price / qty, 2) if qty > 0 else price

        items.append({
            "Item": item_name or "Unnamed Item",
            "Qty": qty,
            "Unit Price (EGP)": unit_price,
            "Total (EGP)": price
        })

    return pd.DataFrame(items)

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

    with st.spinner("🧠 Extracting items from invoice..."):
        df = extract_items(image)

    if not df.empty:
        st.success("✅ Items extracted successfully!")
        selected_rows = st.multiselect(
            "Select what you personally ordered:",
            options=df.index,
            format_func=lambda i: f"{df.at[i, 'Qty']}x {df.at[i, 'Item']} - EGP {df.at[i, 'Total (EGP)']:.2f}"
        )

        if selected_rows:
            df_selected = df.loc[selected_rows]
            st.dataframe(df_selected)

            st.subheader("💰 Your Personal Summary")
            service_charge = st.number_input("Service Charge %", value=12.0)
            vat = st.number_input("VAT %", value=14.0)
            tip = st.number_input("Optional Tip (EGP)", value=0.0)

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
        else:
            st.info("Select the items you personally ordered to see your total.")
    else:
        st.warning("⚠️ No items were detected. Try a clearer image.")
