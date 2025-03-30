import streamlit as st
from PIL import Image
import pytesseract
import pandas as pd
import re
from fpdf import FPDF
import smtplib
from email.message import EmailMessage
import tempfile
import os

# --- Helper Functions ---
def extract_items_from_text(text):
    lines = text.splitlines()
    items, totals, metadata = [], {}, {}

    for line in lines:
        if "Date" in line and "Time" in line:
            match = re.search(r'Date\s*[:\-]\s*(\d{4}/\d{2}/\d{2}).*Time\s*[:\-]\s*(\d{1,2}:\d{2}:\d{2}\s*[APMapm]*)', line)
            if match:
                metadata["Date"] = match.group(1)
                metadata["Time"] = match.group(2)

        match = re.match(r"(.+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line)
        if match:
            items.append({
                "Item": match.group(1).strip(),
                "Qty": int(match.group(2)),
                "Unit Price": float(match.group(3)),
                "Total": float(match.group(4))
            })

        if "Net Price" in line:
            totals["Net Price"] = float(re.findall(r"[\d.]+", line)[-1])
        if "VAT" in line:
            totals["VAT"] = float(re.findall(r"[\d.]+", line)[-1])
        if "Discount" in line:
            totals["Discount"] = float(re.findall(r"[\d.]+", line)[-1])
        if re.search(r'Total\s*[:\-]', line):
            values = re.findall(r"[\d.]+", line)
            if values:
                totals["Total"] = float(values[-1])
    
    return items, totals, metadata

def generate_pdf(df, summary, split_total, per_person, email=None):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Yalla Split & Pay - Final Bill", ln=True, align='C')
    pdf.ln(5)

    # Items
    for i, row in df.iterrows():
        pdf.cell(200, 10, txt=f"{row['Item']} x{row['Qty']} - {row['Total']:.2f}", ln=True)

    pdf.ln(5)
    for key, value in summary.items():
        pdf.cell(200, 10, txt=f"{key}: {value:.2f}", ln=True)

    pdf.ln(5)
    pdf.cell(200, 10, txt=f"Total with Tip/Service: {split_total:.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Per Person: {per_person:.2f}", ln=True)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(temp_file.name)
    return temp_file.name

def send_email(recipient, file_path):
    msg = EmailMessage()
    msg["Subject"] = "Yalla Split & Pay - Your Final Bill"
    msg["From"] = "your_email@example.com"
    msg["To"] = recipient
    msg.set_content("Attached is your split bill PDF.")

    with open(file_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="application", subtype="pdf", filename="bill.pdf")

    # Replace with actual SMTP settings
    with smtplib.SMTP_SSL("smtp.example.com", 465) as smtp:
        smtp.login("your_email@example.com", "your_password")
        smtp.send_message(msg)

# --- Streamlit UI ---
st.title("Yalla Split & Pay")

uploaded_file = st.file_uploader("Upload invoice image", type=["jpg", "jpeg", "png"])
if uploaded_file:
    image = Image.open(uploaded_file)
    st.image(image, caption="Invoice Image", use_column_width=True)

    text = pytesseract.image_to_string(image)
    items, totals, metadata = extract_items_from_text(text)

    df = pd.DataFrame(items)
    selected_rows = st.multiselect("Select items to include in split", df.index, format_func=lambda x: df.iloc[x]['Item'])

    if selected_rows:
        selected_df = df.loc[selected_rows]
        selected_total = selected_df["Total"].sum()

        st.subheader("Summary")
        tip_percent = st.slider("Tip (%)", 0, 20, 10)
        service_percent = st.slider("Service Charge (%)", 0, 15, 5)
        num_people = st.number_input("Split among how many people?", min_value=1, value=2)

        tip = selected_total * tip_percent / 100
        service = selected_total * service_percent / 100
        grand_total = selected_total + tip + service
        per_person = grand_total / num_people

        summary = {
            "Selected Total": selected_total,
            "Tip": tip,
            "Service Charge": service,
            "Grand Total": grand_total,
            "Per Person": per_person
        }

        st.write(summary)

        # Export to PDF
        if st.button("Generate PDF"):
            pdf_path = generate_pdf(selected_df, summary, grand_total, per_person)
            with open(pdf_path, "rb") as f:
                st.download_button("Download PDF", f, file_name="split_bill.pdf")

        # Email PDF
        email_to = st.text_input("Send PDF to email:")
        if st.button("Send Email"):
            if email_to:
                send_email(email_to, pdf_path)
                st.success("Email sent successfully.")
            else:
                st.error("Please enter a valid email.")
