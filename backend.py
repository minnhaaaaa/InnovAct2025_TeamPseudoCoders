from flask import Flask, request, jsonify, send_file, url_for
from flask_cors import CORS
import mysql.connector as msql
import secrets, io, base64, qrcode
WINDOW_MINUTES = 20  # allow validation only in the last 20 minutes before departure

# ---------- DB ----------
DB = dict(host='localhost', user='root', password='tiger', database='railway')  # your creds

def get_conn():
    return msql.connect(**DB)

def init_db():
    con = msql.connect(host='localhost', user='root', password='tiger')
    cur = con.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS railway")
    cur.execute("USE railway")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        ticket_id VARCHAR(50) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL,
        start_place VARCHAR(255) NOT NULL,
        destination VARCHAR(255) NOT NULL,
        travel_date DATE NOT NULL,
        travel_time TIME NOT NULL,
        used TINYINT(1) NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)
    con.commit()
    cur.close(); con.close()

# ---------- helpers ----------
def gen_ticket_id():
    letters = "".join(secrets.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
    digits  = "".join(secrets.choice("0123456789") for _ in range(4))
    return f"T-{letters}{digits}"

def make_qr_png_bytes(text: str) -> bytes:
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ---------- app ----------
#to create the app
app = Flask(__name__)
#Basically kindof making the API , so that one in frontend using different origi can call your Flask API
#CORS = cross origin resource sharing
CORS(app)

init_db()  # ensure DB/table exists on startup

#To register GET Endpoint at /health
@app.get("/health")
def health():
    return {"status": "ok"}

#GET Endpoint to test the database
@app.get("/db-ping")
def db_ping():
    try:
        con = get_conn()
        con.ping(reconnect=True, attempts=1, delay=0)
        con.close()
        return {"db": "ok"}
    except Exception as e:
        return {"db": "error", "msg": str(e)}, 500

@app.post("/book")
def book():
    data = request.get_json(force=True) or {}
   # data ={'name':'Afrin', 'start_place': 'Katpadi', 'destination':'Kochi','travel_date':'01/12/2025','travel_time':'10.59'}
    for k in ["name", "start_place", "destination", "travel_date", "travel_time"]:
        if not data.get(k):
            return jsonify({"error": f"Missing {k}"}), 400

    tid = gen_ticket_id()

    con = get_conn(); cur = con.cursor()
    cur.execute(
        """INSERT INTO tickets
           (ticket_id, name, start_place, destination, travel_date, travel_time)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (tid, data["name"].strip(), data["start_place"].strip(),
         data["destination"].strip(), data["travel_date"].strip(),
         data["travel_time"].strip())
    )
    con.commit()
    cur.close(); con.close()

    qr_url = url_for("qr_image", ticket_id=tid, _external=True)
    return {"ticket_id": tid, "qr_url": qr_url}



@app.get("/qr/<ticket_id>.png")
def qr_image(ticket_id):
    png = make_qr_png_bytes(ticket_id)
    #here io.BytesIO is an in memory file
    return send_file(io.BytesIO(png), mimetype="image/png",
                     download_name=f"{ticket_id}.png", as_attachment=False)


@app.post("/validate")
def validate_and_mark():
    data = request.get_json(force=True) or {}
    tid = data.get("ticket_id")
    if not tid:
        return {"error": "Missing ticket_id"}, 400

    con = get_conn(); cur = con.cursor()

    # Atomically mark used=1 only if:
    #   - ticket exists
    #   - currently unused
    #   - 0 <= minutes until departure <= WINDOW_MINUTES
    cur.execute("""
        UPDATE tickets
        SET used = 1
        WHERE ticket_id = %s
          AND used = 0
          AND TIMESTAMPDIFF(MINUTE, NOW(), CONCAT(travel_date, ' ', travel_time))
              BETWEEN 0 AND %s
    """, (tid, WINDOW_MINUTES))
    con.commit()
    updated = cur.rowcount

    if updated == 1:
        cur.close(); con.close()
        return {"valid": True, "ticket_id": tid}, 200

    # Not updated: find out why
    cur.execute("""
        SELECT used,
               TIMESTAMPDIFF(MINUTE, NOW(), CONCAT(travel_date, ' ', travel_time)) AS mins_left
        FROM tickets WHERE ticket_id=%s
    """, (tid,))
    row = cur.fetchone()
    cur.close(); con.close()

    if row is None:
        return {"valid": False, "ticket_id": tid, "reason": "not found"}, 404

    used, mins_left = row
    if used == 1:
        return {"valid": False, "ticket_id": tid, "reason": "already used"}, 409
    if mins_left is None:
        return {"valid": False, "ticket_id": tid, "reason": "time error"}, 500
    if mins_left > WINDOW_MINUTES:
        return {"valid": False, "ticket_id": tid, "reason": "too early",
                "mins_until_departure": int(mins_left), "window_minutes": WINDOW_MINUTES}, 403
    if mins_left < 0:
        return {"valid": False, "ticket_id": tid, "reason": "after departure",
                "mins_after_departure": int(-mins_left)}, 403

    # Fallback
    return {"valid": False, "ticket_id": tid, "reason": "unknown"}, 400



if __name__ == "__main__":
    app.run(debug=True)
'''
IN CASE OF POST , THE FRONTEND OR THE USER CAN SEND SOMETHING IN JSON FORMAT
GET → read-only fetch, no side effects
'''
