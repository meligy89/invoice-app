import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
import re
import io
from fpdf import FPDF

st.set_page_config(page_title="Yalla Split & Pay", layout="wide")
st.image("https://i.imgur.com/HN0H6qX.png", width=180)
st.title("🧾 Yalla Split & Pay")
st.markdown("""
<style>
    .stButton>button {
        border-radius: 8px;
        padding: 0.5em 1em;
        margin-top: 0.5em;
        font-weight: bold;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.2);
    }
    .stSlider>div[data-baseweb="slider"] {
        margin-top: 1em;
    }
    .stDataFrame {
        border: 1px solid #ccc;
        border-radius: 8px;
        padding: 0.5em;
    }
</style>
""", unsafe_allow_html=True)

# Upload invoice image
uploaded_file = st.file_uploader("Upload an invoice image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Uploaded Invoice", use_column_width=True)

    # OCR configuration
    config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789EGP.,abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ '
    text = pytesseract.image_to_string(image, config=config)

    # Extract items with regex
    cleaned_text = text.replace('\n', ' ').replace('EGP', '|EGP').replace('  ', ' ')
    item_pattern = re.compile(r"(\d*)\s*([A-Za-z\s]+)\|EGP\s*([\d,]+\.\d{2})")
    items = []

    for match in item_pattern.findall(cleaned_text):
        qty = int(match[0]) if match[0].isdigit() else 1
        name = match[1].strip()
        price = float(match[2].replace(',', ''))
        items.append({"Qty": qty, "Item": name, "Price (EGP)": price})

    df_items = pd.DataFrame(items)

    st.subheader("📦 Select Items")
    selected_rows = []
    for idx, row in df_items.iterrows():
        if st.checkbox(f"{row['Qty']} x {row['Item']} - EGP {row['Price (EGP)']}", value=True):
            selected_rows.append(row)

    df_selected = pd.DataFrame(selected_rows)
    st.dataframe(df_selected)

    # Extract totals
    subtotal_match = re.search(r'Subtotal\s*EGP\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    service_match = re.search(r'Service\s*EGP\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    vat_match = re.search(r'([Vv]at).*?([\d,]+\.\d{2})', text)

    subtotal = float(subtotal_match.group(1).replace(',', '')) if subtotal_match else 0
    service = float(service_match.group(1).replace(',', '')) if service_match else 0
    vat = float(vat_match.group(2).replace(',', '')) if vat_match else 0
    total = round(subtotal + service + vat, 2)

    st.subheader("📊 Summary")
    st.write(f"**Subtotal:** EGP {subtotal:,.2f}")
    st.write(f"**Service:** EGP {service:,.2f}")
    st.write(f"**VAT:** EGP {vat:,.2f}")
    st.write(f"**Total:** EGP {total:,.2f}")

    # Optional tip
    tip = st.number_input("Add a tip (EGP):", min_value=0.0, step=1.0)
    grand_total = total + tip
    st.write(f"**Grand Total (with tip):** EGP {grand_total:,.2f}")

    # Split the bill
    num_people = st.slider("Split between how many people?", min_value=1, max_value=20, value=1)
    split_amount = grand_total / num_people
    st.write(f"Each person pays: EGP {split_amount:,.2f}")

    # Export CSV
    if st.button("Export to CSV"):
        export_df = df_selected.copy()
        export_df.loc[len(export_df.index)] = ["", "Subtotal", subtotal]
        export_df.loc[len(export_df.index)] = ["", "Service", service]
        export_df.loc[len(export_df.index)] = ["", "VAT", vat]
        export_df.loc[len(export_df.index)] = ["", "Tip", tip]
        export_df.loc[len(export_df.index)] = ["", "Grand Total", grand_total]

        csv = export_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download Invoice CSV", data=csv, file_name="invoice_summary.csv", mime="text/csv")

    # Export PDF
    if st.button("Export to PDF"):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        pdf.cell(200, 10, txt="Invoice Summary", ln=True, align='C')
        pdf.ln(10)

        for index, row in df_selected.iterrows():
            pdf.cell(200, 10, txt=f"{row['Qty']} x {row['Item']} - EGP {row['Price (EGP)']}", ln=True)

        pdf.ln(5)
        pdf.cell(200, 10, txt=f"Subtotal: EGP {subtotal:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Service: EGP {service:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"VAT: EGP {vat:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Tip: EGP {tip:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Grand Total: EGP {grand_total:,.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Split Between {num_people}: EGP {split_amount:,.2f} each", ln=True)

        pdf_output = io.BytesIO()
        pdf.output(pdf_output)
        st.download_button("Download Invoice PDF", data=pdf_output.getvalue(), file_name="invoice_summary.pdf", mime="application/pdf")
