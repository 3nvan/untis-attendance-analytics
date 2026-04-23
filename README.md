# WebUntis Teacher Absence Analyzer

A Streamlit web application that connects to the WebUntis API and analyzes teacher absence patterns (cancelled lessons) across different school years.

![Python](https://img.shields.io/badge/python-3.x-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-red)

## 🌐 Live Demo

A live instance is available at [untis.dreaming.qzz.io](https://untis.dreaming.qzz.io)

> Note: This instance may require valid WebUntis credentials to use.

## Features

- **Interactive Web Dashboard** - Built with Streamlit
- **Dual Login** - Username/Password or QR/Key (TOTP)
- **Teacher Leaderboard** - Ranked by cancelled lessons and attendance %
- **School Year Filter** - View data by year or all years
- **Minimum Lessons Filter** - Filters out cover/substitute teachers
- **Charts** - Visualize cancellations by teacher and by day
- **Auto-fill** - Uses `.env` file for credentials

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/3nvan/untis-attendance-analytics.git
   cd untis-attendance-analytics
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure credentials**:
   ```bash
   cp .env.example .env
   # Edit .env with your WebUntis credentials:
   ```

   ```
   UNTIS_SERVER=yourschool.webuntis.com
   UNTIS_SCHOOL=yourschool
   UNTIS_USER=yourusername
   UNTIS_PASSWORD=yourpassword
   ```

## How to Run

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

Or use the startup script:
```bash
./start.sh
```

## Login Methods

### Username/Password
Enter your standard WebUntis credentials. Credentials from `.env` auto-fill the form.

### QR/Key
1. In WebUntis web app: Profile > Data Access > Show QR
2. Upload the QR image or paste the data
3. The app extracts server, school, username, and TOTP key automatically

## Project Structure

```
untis-attendance-analytics/
├── app.py              # Main Streamlit application
├── requirements.txt  # Python dependencies
├── .env.example       # Template for credentials
├── README.md           # This file
└── start.sh           # Startup script
```

## Requirements

See `requirements.txt` for full list:
- streamlit
- pandas
- webuntis
- python-dotenv
- pyotp
- requests
- opencv-python-headless
- Pillow

## ⚖️ Legal Disclaimer

> **Educational use only.** Processing personal data (teacher names, absence records) may be subject to GDPR and similar privacy laws. Users are solely responsible for ensuring they have legal authority to process this data.

> **Not affiliated with Untis GmbH.** This tool may violate WebUntis Terms of Service. Use at your own risk.

> **Provided "as is."** No warranty. Authors are not liable for any claims arising from use.

## License

GNU Affero General Public License v3 (AGPL) - See LICENSE file for details.
