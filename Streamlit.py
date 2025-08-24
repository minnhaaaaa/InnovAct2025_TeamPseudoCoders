import streamlit as st
import pandas as pd
import random
import re
import requests                      # <-- NEW
from datetime import datetime, date, time

# ----- Config -----
BACKEND = "http://127.0.0.1:5000"    # change if your Flask runs elsewhere

# Load stations from CSV
csv_path = r"C:\Users\Dhruvi\.streamlit\stations.csv"
try:
    df = pd.read_csv(csv_path)
    stations = df[df.columns[0]].dropna().tolist()
    stations = ["..." if s.strip().lower() == "agra cantt" else s for s in stations]
except Exception as e:
    st.error(f"Could not load stations.csv: {e}")
    stations = []

# UI
st.set_page_config(page_title="Train Ticket Booking", layout="centered")
st.title("Train Ticket Booking System")

with st.form("booking_form"):
    name = st.text_input("Enter your Name")
    source = st.selectbox("Select Source Station", stations)
    destination = st.selectbox("Select Destination Station", stations)
    travel_date = st.date_input("Select Travel Date", min_value=date.today())
    train_time = st.time_input("Select Preferred Train Time", time(8, 30))  # returns a time object

    submitted = st.form_submit_button("Generate Ticket")

if submitted:
    errors = []

    # Validate name
    if not name.strip() or re.search(r'\d', name):
        errors.append("Name cannot be empty or contain numbers.")

    # Validate source and destination
    if source == destination:
        errors.append("Source and Destination cannot be the same.")

    # Validate travel date
    if travel_date < date.today():
        errors.append("Travel Date cannot be in the past.")

    if errors:
        for err in errors:
            st.error(err)
    else:
        # ---- Build JSON for backend (24h time + ISO date) ----
        payload = {
            "name": name.strip(),
            "start_place": source.strip(),
            "destination": destination.strip(),
            "travel_date": travel_date.strftime("%Y-%m-%d"),  # <-- 2025-12-01
            "travel_time": train_time.strftime("%H:%M")       # <-- 24h HH:MM
        }

        try:
            r = requests.post(f"{BACKEND}/book", json=payload, timeout=10)
        except requests.RequestException as e:
            st.error(f"Could not reach backend: {e}")
        else:
            if r.ok:
                data = r.json()  # expects {"ticket_id": "...", "qr_url": "..."}
                st.success(
                    f"Ticket booked successfully!\n\n"
                    f"**Ticket ID:** {data['ticket_id']}\n\n"
                    f"**Route:** {source} → {destination}\n\n"
                    f"**Date:** {travel_date.strftime('%d-%m-%Y')}\n\n"
                    f"**Train Time (24h):** {train_time.strftime('%H:%M')}"
                )
                # Show QR from backend URL
                st.image(data["qr_url"], caption="Your QR Ticket", width=260)
            else:
                # Show backend error message
                try:
                    err = r.json()
                except Exception:
                    err = {"error": r.text}
                st.error(f"Backend error {r.status_code}: {err}")
