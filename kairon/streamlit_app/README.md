# Kairon CRM Provisioning Dashboard

A modern, glassmorphism-styled Streamlit dashboard for Kairon administrators to provision and audit private ERPNext instances.

## Setup & Running

1. **Install Dependencies**
   Navigate to this folder and install dependencies in your virtual environment:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   Ensure the following environment variables are set if different from defaults:
   - `API_BASE_URL`: Kairon API endpoint (default: `http://localhost:8000`)
   - `TIMEOUT`: API requests timeout in seconds (default: `30`)

3. **Start the Application**
   Run the Streamlit application:
   ```bash
   streamlit run app.py
   ```
   Open your browser to `http://localhost:8501`.

## Features
- **Authentication**: Connects to Kairon Auth endpoints and securely manages session tokens.
- **Aggregated Stats**: Lists all provisioned ERPNext sites and DB benches with live status color indicators.
- **Onboarding Wizard**: Step-by-step form to launch, deploy, and monitor provisioning workflows.
- **Diagnostics Dashboard**: Diagnostic pings to Postgres, Redis, MongoDB, and ERPNext APIs.
