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

def get_sheet_id(sheets):
    """Look up the numeric sheetId for the Invoices tab."""
    meta = sheets.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == SHEET_TAB:
            return s["properties"]["sheetId"]
    return None

def extract_invoice_summary(pdf_bytes, filename):
    """One row per invoice: total hours + total amount."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

    vendor = "Unknown"
    invoice_num = ""
    rate = ""
    hours = ""
    amount = ""
    date = ""
    client = ""
    title = filename
    work_type = ""

    # Anthony Espinoza — multi-month invoice (Feb–Oct 2026); use end of period
    if "Anthony Espinoza" in full_text or "ANTHONYESPINOZA" in full_text:
        vendor = "Anthony Espinoza"
        invoice_num = "70"
        rate = 50
        client = "Durotech"
        title = "Durotech Email Campaigns"
        work_type = "Web"
        date = "2026-10-31"  # end of the work period covered
        m = re.search(r"Total Overall Hours:\s*([\d.]+)", full_text)
        if m:
            hours = m.group(1)
        m = re.search(r"Subtotal\s*\$([\d,]+\.\d{2})", full_text)
        if m:
            amount = m.group(1).replace(",", "")

    # Mandy Saenz — September 2026 work, invoice dated Oct 6
    elif "Mandy Saenz" in full_text or "MANDY SAENZ" in full_text:
        vendor = "Mandy Saenz"
        rate = 80
        title = "September 2026 Services"
        work_type = "Design"
        date = "2026-10-06"  # invoice date from the PDF
        m = re.search(r"TOTAL HOURS\s*([\d.]+)\s*hrs", full_text, re.I)
        if m:
            hours = m.group(1)
        m = re.search(r"AMOUNT DUE\s*\$([\d,]+\.\d{2})", full_text, re.I)
        if m:
            amount = m.group(1).replace(",", "")

    # WellSaid — dated 10/01/2026
    elif "WellSaid" in full_text or "Well Said" in full_text:
        vendor = "WellSaid"
        invoice_num = "2026-0930"
        rate = 80
        title = "Field Focus & Foundation"
        work_type = "Email"
        date = "2026-10-01"
        m = re.search(r"\$([\d,]+\.\d{2})", full_text)
        if m:
            amount = m.group(1).replace(",", "")
        hours = "1.25"

    # Fallback if no date was set
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # General fallback: if no client was found, use the vendor name
    if not client:
        client = vendor

    row = {
        "Date": date,
        "Work Type": work_type,
        "Client": client,
        "Title": title,
        "Hours": hours,
        "Vendor": vendor,
        "Invoice #": invoice_num,
        "Rate": rate,
        "Amount": amount,
        "PDF Link": "",
        "Submitted At": datetime.now().strftime("%Y-%m-%d")
    }
    return [row], vendor.replace(" ", "")

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
        mapped = [row.get(h, "") for h in headers]
        values.append(mapped)

    body = {"values": values}
    result = sheets.spreadsheets().values().append(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_TAB}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

    # Force normal (non-bold) formatting on the newly added rows
    sheet_id = get_sheet_id(sheets)
    updated_range = result.get("updates", {}).get("updatedRange", "")
    if updated_range and sheet_id is not None:
        match = re.search(r"!([A-Z]+)(\d+):([A-Z]+)(\d+)", updated_range)
        if match:
            start_row = int(match.group(2))
            end_row = int(match.group(4))
            requests_body = {
                "requests": [{
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row - 1,
                            "endRowIndex": end_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": len(headers)
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {"bold": False}
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold"
                    }
                }]
            }
            sheets.spreadsheets().batchUpdate(
                spreadsheetId=SHEET_ID,
                body=requests_body
            ).execute()

# --- UI ---
st.title("Invoice Intake — Made More Marketing")
st.write("Upload one or more PDF invoices. Each will be archived to Drive and a summary row appended to the Sheet.")
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
        items, vendor_safe = extract_invoice_summary(pdf_bytes, uploaded.name)
        st.write(f"**{uploaded.name}** — vendor: {items[0]['Vendor']} — hours: {items[0]['Hours']} — amount: {items[0]['Amount']}")

        if drive and sheets:
            date_str = datetime.now().strftime("%Y-%m-%d")
            archive_name = f"{vendor_safe}_{date_str}.pdf"
            link = upload_pdf(drive, pdf_bytes, archive_name)
            for item in items:
                item["PDF Link"] = link
            append_to_sheet(sheets, items)
            success_count += 1
        all_items.extend(items)

    if drive and sheets:
        st.success(f"Processed {success_count} file(s) and appended {len(all_items)} row(s) to the Sheet.")
    else:
        st.warning("Not logged in — extraction preview only.")

    if all_items:
        st.dataframe(all_items)
