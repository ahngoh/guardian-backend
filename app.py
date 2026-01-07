from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import time
from openai import OpenAI
raise RuntimeError("ACTIVE BACKEND")

# ---------------- APP SETUP ----------------
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---------------- SIMPLE ENTITLEMENTS STORE ----------------
# TEMP / IN-MEMORY (OK FOR NOW)
# email -> entitlement
ENTITLEMENTS = {
    # Example Plus user
    # "test@example.com": {
    #     "plan": "plus",
    #     "screen_remaining": 30,
    #     "renews_at": 9999999999
    # }
}

SCREEN_LIMIT_PLUS = 30


def get_user_email():
    email = request.headers.get("X-User-Email")
    if not email:
        return None
    return email.lower()


def get_entitlement(email):
    ent = ENTITLEMENTS.get(email)
    if not ent:
        # default FREE user
        return {
            "plan": "free",
            "screen_remaining": 0,
            "renews_at": 0
        }
    return ent


def ensure_plus_screen_access(email):
    ent = get_entitlement(email)

    if ent["plan"] != "plus":
        return False, "Upgrade to Plus to use screen share."

    if ent["screen_remaining"] <= 0:
        return False, "Screen share limit reached. Upgrade or wait for reset."

    # decrement usage
    ent["screen_remaining"] -= 1
    ENTITLEMENTS[email] = ent
    return True, None


# ---------------- HEALTH ----------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------------- CHAT (TEXT ONLY) ----------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = data.get("message")

    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are Guardian, a calm, direct, step-by-step assistant. Give one clear step at a time."
                },
                {"role": "user", "content": message}
            ]
        )

        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- SCREEN ANALYSIS ----------------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    email = get_user_email()
    if not email:
        return jsonify({"error": "Unauthorized"}), 401

    allowed, reason = ensure_plus_screen_access(email)
    if not allowed:
        return jsonify({"error": reason}), 403

    data = request.get_json(force=True)
    prompt = data.get("prompt")
    image_b64 = data.get("image")

    if not prompt or not image_b64:
        return jsonify({"error": "Missing prompt or image"}), 400

    try:
        response = client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    ]
                }
            ]
        )

        reply = response.output_text
        if not reply:
            return jsonify({"error": "Empty response from OpenAI"}), 500

        return jsonify({
            "reply": reply,
            "screen_remaining": ENTITLEMENTS[email]["screen_remaining"]
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- TEMP ADMIN ENDPOINT ----------------
# Use this to manually grant Plus during testing
@app.route("/_grant_plus", methods=["POST"])
def grant_plus():
    data = request.get_json(force=True)
    email = data.get("email")

    if not email:
        return jsonify({"error": "Email required"}), 400

    ENTITLEMENTS[email.lower()] = {
        "plan": "plus",
        "screen_remaining": SCREEN_LIMIT_PLUS,
        "renews_at": int(time.time()) + 30 * 24 * 60 * 60
    }

    return jsonify({"status": "plus granted", "email": email})


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
