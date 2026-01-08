from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os

# ---------------- APP SETUP ----------------
app = Flask(__name__)
CORS(app)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ---------------- IN-MEMORY ENTITLEMENTS ----------------
# NOTE:
# - This is TEMP
# - Survives requests but NOT restarts
# - Cancel does NOTHING (by design)
ENTITLEMENTS = {}
SCREEN_LIMIT_PLUS = 999999  # effectively unlimited

def get_user_email():
    email = request.headers.get("X-User-Email")
    return email.lower() if email else None

def ensure_plus_access(email):
    ent = ENTITLEMENTS.get(email)

    if not ent:
        return False, "Upgrade to Plus to use screen share."

    if ent["plan"] != "plus":
        return False, "Upgrade to Plus to use screen share."

    return True, None

# ---------------- ROUTES ----------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# -------- CHAT (ALWAYS FREE) --------
@app.route("/chat", methods=["POST"])
def chat():
    if not client:
        return jsonify({"error": "OpenAI not configured"}), 500

    data = request.json
    user_message = data.get("message") if data else None

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a calm step-by-step assistant."},
            {"role": "user", "content": user_message}
        ]
    )

    return jsonify({"reply": response.choices[0].message.content})

# -------- SCREEN SHARE (PLUS ONLY) --------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    if not client:
        return jsonify({"error": "OpenAI not configured"}), 500

    email = get_user_email()
    if not email:
        return jsonify({"error": "Login required"}), 401

    allowed, reason = ensure_plus_access(email)
    if not allowed:
        return jsonify({"error": reason}), 403

    data = request.json
    prompt = data.get("prompt")
    image_b64 = data.get("image")

    if not prompt or not image_b64:
        return jsonify({"error": "Missing prompt or image"}), 400

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image_b64}"
                }
            ]
        }]
    )

    return jsonify({"reply": response.output_text})

# -------- MANUAL GRANT (WHAT MADE IT WORK) --------
@app.route("/_grant_plus", methods=["POST"])
def grant_plus():
    data = request.json
    email = data.get("email")

    if not email:
        return jsonify({"error": "email required"}), 400

    ENTITLEMENTS[email.lower()] = {
        "plan": "plus"
    }

    return jsonify({"status": "ok"})

# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
