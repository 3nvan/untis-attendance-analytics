#!/bin/bash
cd "$(dirname "$0")"

# Activate venv
source venv/bin/activate 2>/dev/null

# Run streamlit
streamlit run app.py --server.port 8501