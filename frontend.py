import streamlit as st
import pandas as pd
import random
import re
import requests                     
from datetime import datetime, date, time

#Configuration
BACKEND = "http://127.0.0.1:5000"    # change if your Flask runs elsewhere
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

# Load stations from CSV
csv_path = r"C:\Users\Asus\Downloads\stations.csv" #change path for stations.csv
try:
    df = pd.read_csv(csv_path)
    stations = df[df.columns[0]].dropna().tolist()
    stations = ["..." if s.strip().lower() == "agra cantt" else s for s in stations]
except Exception as e:
    st.error(f"Could not load stations.csv: {e}")
    stations = []


#video processing
class QRVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.qr_text = None

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        decoded_objects = decode(gray)
        if decoded_objects:
            try:
                self.qr_text = decoded_objects[0].data.decode("utf-8")
            except Exception:
                self.qr_text = decoded_objects[0].data.decode(errors="ignore")
            # Draw bounding box
            pts = decoded_objects[0].polygon
            if len(pts) > 4:
                hull = cv2.convexHull(np.array([pt for pt in pts], dtype=np.float32))
                hull = list(map(tuple, np.squeeze(hull)))
            else:
                hull = pts
            for j in range(len(hull)):
                cv2.line(img, hull[j], hull[(j + 1) % len(hull)], (0, 255, 0), 3)
            x, y, w, h = decoded_objects[0].rect
            cv2.putText(img, self.qr_text, (x, max(10, y - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")
    
#UI Tabs
tab1, tab2 = st.tabs(["Ticket Booking", "QR Scanner"])
with tab1:
#Ticket Booking Page
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

        if not name.strip() or re.search(r'\d', name):
            errors.append("Name cannot be empty or contain numbers.")

        if source == destination:
            errors.append("Source and Destination cannot be the same.")

        if travel_date < date.today():
            errors.append("Travel Date cannot be in the past.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            payload = {
                "name": name.strip(),
                "start_place": source.strip(),
                "destination": destination.strip(),
                "travel_date": travel_date.strftime("%Y-%m-%d"),  
                "travel_time": train_time.strftime("%H:%M")       
            }

            try:
                r = requests.post(f"{BACKEND}/book", json=payload, timeout=10)
            except requests.RequestException as e:
                st.error(f"Could not reach backend: {e}")
            else:
                if r.ok:
                    data = r.json()
                    st.success(
                        f"Ticket booked successfully!\n\n"
                        f"**Ticket ID:** {data['ticket_id']}\n\n"
                        f"**Route:** {source} → {destination}\n\n"
                        f"**Date:** {travel_date.strftime('%d-%m-%Y')}\n\n"
                        f"**Train Time (24h):** {train_time.strftime('%H:%M')}"
                    )
                    st.image(data["qr_url"], caption="Your QR Ticket", width=260)
                else:
                    try:
                        err = r.json()
                    except Exception:
                        err = {"error": r.text}
                    st.error(f"Backend error {r.status_code}: {err}")
#QR Gate Simulator
with tab2:
    st.title("IoT QR Validator Gate")
    st.write("Align your QR code with the camera")

    qr_display = st.empty()
    status_display = st.empty()
    raw_resp_display = st.empty()

    if "last_qr" not in st.session_state:
        st.session_state.last_qr = None
    if "checked" not in st.session_state:
        st.session_state.checked = False

    webrtc_ctx = webrtc_streamer(
        key="qr-scanner",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTC_CONFIGURATION,
        video_processor_factory=QRVideoProcessor,
        media_stream_constraints={"video": True, "audio": False},
        async_processing=True,
    )

    if webrtc_ctx.video_processor and webrtc_ctx.video_processor.qr_text:
        qr_value = webrtc_ctx.video_processor.qr_text
        qr_display.code(qr_value)

        if qr_value != st.session_state.last_qr:
            st.session_state.checked = False
            st.session_state.last_qr = qr_value

        if not st.session_state.checked:
            status_display.info("⏳ Verifying ticket…")
            try:
                resp = requests.post(f"{BACKEND}/validate", json={"ticket_id": qr_value}, timeout=5)
                raw_resp_display.text(resp.text)
                if resp.ok:
                    data = resp.json()
                    if data.get("valid"):
                        status_display.success("✅ Verified! Gate Open")
                    else:
                        reason = data.get("reason", "unknown")
                        status_display.error(f"❌ Access Denied: {reason}")
                else:
                    status_display.error(f"Error: {resp.status_code}")
            except Exception as e:
                status_display.error(f"Request failed: {e}")
            st.session_state.checked = True
    else:
        status_display.info("Waiting for QR code…")
