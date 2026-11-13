import streamlit as st
import pdfplumber
import io
import os
import re
import requests
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import json

# --- CONFIG ---
FOLDER_ID = "1hoL2SpFLRy1LpRDkHHXNbdQEyQGFOEqn"
SHEET_ID = "14zsPHEUSkl4O_uYKbetJ8MKL2R9hmK3Wq42Sc8PmFx8"
SHEET_TAB = "Invoices"

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = "https://e40917e1-1bdd-46b5-9070-cc27c4f45171-00-18a7kuhead3e6.kirk.replit.dev/"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
SCOPE_STR = " ".join(SCOPES)

def get_google_services():
    if "credentials" not in st.session_state:
        return None, None
    creds = Credentials(**st.session_state.credentials)
    drive = build("drive", "v3", credentials=creds)
    sheets = build("sheets", "v4", credentials=creds)
    return drive, sheets

def extract_line_items(pdf_bytes, filename):
    items = []
    vendor = "Unknown"
    invoice_num = ""
    rate = ""
    invoice_date = ""

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

    lines = [l.strip() for l in full_text.splitlines() if l.strip()]

    # Vendor detection + basic header fields
    if "Anthony Espinoza" in full_text or "ANTHONYESPINOZA" in full_text:
        vendor = "AnthonyEspinoza"
        invoice_num = "70"
        rate = 50
        # Try to find invoice date from text (fallback to submitted date)
        for line in lines:
            if re.search(r"\d{1,2}/\d{1,2}/\d{4}", line) or "2026" in line:
                invoice_date = "2026"
                break
    elif "Mandy Saenz" in full_text or "MANDY SAENZ" in full_text:
        vendor = "MandySaenz"
        rate = 80
        invoice_date = "2026-09"
    elif "WellSaid" in full_text or "Well Said" in full_text:
        vendor = "WellSaid"
        invoice_num = "2026-0930"
        rate = 80
        invoice_date = "2026-10-01"

    # Layout-specific extraction
    if vendor == "AnthonyEspinoza":
        for line in lines:
            # Look for lines that end with hours + $rate + $amount
            m = re.search(r"(.+?)\s+(\d+\.?\d*)\s+\$50\.00\s+\$([\d,]+\.\d{2})", line)
            if m:
                title = m.group(1).strip()
                hours = m.group(2)
                amount = m.group(3).replace(",", "")
                items.append({
                    "Date": invoice_date,
                    "Work Type": "Web",
                    "Client": "Durotech",
                    "Title": title[:100],
                    "Hours": hours,
                    "Vendor": "Anthony Espinoza",
                    "Invoice #": invoice_num,
                    "Rate": rate,
                    "Amount": amount,
                    "PDF Link": "",
                    "Submitted At": datetime.now().strftime("%Y-%m-%d")
                })
    elif vendor == "MandySaenz":
        for line in lines:
            # Pattern: date client project hours
            m = re.search(r"(\d+\.\d+)\s+(\w+)\s+(.+?)\s+(\d+\.?\d*)$", line)
            if m:
                date_part = m.group(1)
                client = m.group(2)
                title = m.group(3).strip()
                hours = m.group(4)
                items.append({
                    "Date": f"2026-{date_part.replace('.', '-')}",
                    "Work Type": "",
                    "Client": client,
                    "Title": title[:100],
                    "Hours": hours,
                    "Vendor": "Mandy Saenz",
                    "Invoice #": "",
                    "Rate": rate,
                    "Amount": str(float(hours) * rate) if hours else "",
                    "PDF Link": "",
                    "Submitted At": datetime.now().strftime("%Y-%m-%d")
                })
    elif vendor == "WellSaid":
        for line in lines:
            m = re.search(r"(\d+\.?\d*)\s+(.+?)\s+80\.00\s+(\d+\.\d{2})", line)
            if m:
                hours = m.group(1)
                title = m.group(2).strip()
                amount = m.group(3)
                items.append({
                    "Date": invoice_date,
                    "Work Type": "",
                    "Client": "Made More Marketing",
                    "Title": title[:100],
                    "Hours": hours,
                    "Vendor": "WellSaid",
                    "Invoice #": invoice_num,
                    "Rate": rate,
                    "Amount": amount,
                    "PDF Link": "",
                    "Submitted At": datetime.now().strftime("%Y-%m-%d")
                })

    if not items:
        items.append({
            "Date": invoice_date,
            "Work Type": "",
            "Client": "",
            "Title": filename,
            "Hours": "",
            "Vendor": vendor,
            "Invoice #": invoice_num,
            "Rate": rate,
            "Amount": "",
            "PDF Link": "",
            "Submitted At": datetime.now().strftime("%Y-%m-%d")
        })
    return items, vendor

def upload_pdf(drive, pdf_bytes, filename):
    media = MediaIoBaseUpload(io.BytesIO(pdf_bytes), mimetype="application/pdf", resumable=True)
    file_metadata = {"name": filename, "parents": [FOLDER_ID]}
    file = drive.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    return file.get("webViewLink")

def append_to_sheet(sheets, rows):
    header_resp = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=f"{SHEET_TAB}!1:1"
    ).execute()
    headers = header_resp.get("values", [[]])[0]

    values = []
    for row in rows:
        mapped = []
        for h in headers:
            mapped.append(row.get(h, ""))
        values.append(mapped)

    body = {"values": values}
    sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

# --- UI ---
st.title("Invoice Intake — Made More Marketing")
st.write("Upload one or more PDF invoices. Each will be archived to Drive and line items appended to the Sheet.")
st.info("For best performance, do not exceed 10 PDFs at a time.")

# Handle OAuth callback (manual, no PKCE)
query_params = st.query_params
if "code" in query_params and "credentials" not in st.session_state:
    try:
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": query_params["code"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
        resp = requests.post(token_url, data=data)
        resp.raise_for_status()
        token_data = resp.json()

        st.session_state.credentials = {
            "token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "token_uri": token_url,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scopes": SCOPES
        }
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Login failed: {e}")
        if "resp" in locals():
            st.error(resp.text)

# OAuth login
if "credentials" not in st.session_state:
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error("Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET secrets.")
    else:
        auth_url = (
            "https://accounts.google.com/o/oauth2/auth"
            f"?client_id={CLIENT_ID}"
            f"&redirect_uri={REDIRECT_URI}"
            f"&scope={SCOPE_STR}"
            "&response_type=code"
            "&access_type=offline"
            "&prompt=consent"
        )
        st.link_button("Login with Google", auth_url)
        st.stop()
else:
    st.success("Logged in with Google")

uploaded_files = st.file_uploader("Choose PDF(s)", type="pdf", accept_multiple_files=True)

if uploaded_files and st.button("Process Invoices"):
    drive, sheets = get_google_services()
    all_items = []
    success_count = 0

    for uploaded in uploaded_files:
        pdf_bytes = uploaded.read()
        items, vendor = extract_line_items(pdf_bytes, uploaded.name)
        st.write(f"**{uploaded.name}** — detected vendor: {vendor} — {len(items)} line item(s)")

        if drive and sheets:
            date_str = datetime.now().strftime("%Y-%m-%d")
            safe_vendor = vendor.replace(" ", "")
            archive_name = f"{safe_vendor}_{date_str}.pdf"
            link = upload_pdf(drive, pdf_bytes, archive_name)
            for item in items:
                item["PDF Link"] = link
            append_to_sheet(sheets, items)
            success_count += 1
        all_items.extend(items)

    if drive and sheets:
        st.success(f"Processed {success_count} file(s) and appended {len(all_items)} total row(s) to the Sheet.")
    else:
        st.warning("Not logged in — extraction preview only.")

    if all_items:
        st.dataframe(all_items)
