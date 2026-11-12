# King Labs Invoice Intake — Replit Setup

## 1. Create the Replit project
- Go to replit.com → Create Repl → Python
- Name it something like `kinglabs-invoice-intake`

## 2. Add the files
- Paste `requirements.txt` into the root
- Paste `app.py` into the root (overwrite the default main.py or rename)

## 3. Add the service account secret
- In Replit: Tools → Secrets
- Key: `GOOGLE_SERVICE_ACCOUNT_JSON`
- Value: the full contents of your Google service-account JSON key
  (Create one in Google Cloud Console with Drive + Sheets scopes, then share the Drive folder and Sheet with the service-account email)

## 4. Run
- Click Run
- Replit will install the requirements and start Streamlit
- Open the webview and upload one of the sample PDFs

## Notes
- Folder ID and Sheet ID are already hardcoded to the ones we created.
- The append is header-aware: you can delete columns in the Sheet and the app will still write correctly to the remaining headers.
- Extraction is intentionally light and tuned to the three samples. Expand the rules in `extract_line_items` as more invoices arrive.
- After testing, you can share the Replit URL with Jessie or move the project later.
