from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import stripe

# ===============================
# APP SETUP
# ===============================
app = Flask(__name__)
CORS(app)

# ===============================
# OPENAI
# ===============================
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ===============================
# STRIPE
# ===============================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# ===============================
# ENTITLEMENTS (TEMP / IN-MEMORY)
# ===============================
ENTITLEMENTS = {}
SCREEN_LIMIT_PLUS = 30

def get_user_email():
    email = request.headers.get("X-User-Email")
    return email.lower() if email else None

def get_entitlement(email):
    return ENTITLEMENTS.get(email, {
        "plan": "free",          # free | trial | plus
        "screen_remaining": 0
    })

def ensure_plus_access(email):
    ent = get_entitlement(email)

    if ent["plan"] not in ("plus", "trial"):
        return False, "Upgrade to Plus to use screen share."

    if ent["screen_remaining"] <= 0:
        return False, "Screen share limit reached."

    ent["screen_remaining"] -= 1
    ENTITLEMENTS[email] = ent
    return True, None

# ===============================
# ROUTES
# ===============================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# -------------------------------
# CHAT (FREE)
# -------------------------------
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

# -------------------------------
# SCREEN SHARE (PLUS / TRIAL)
# -------------------------------
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

    return jsonify({
        "reply": response.output_text,
        "remaining": ENTITLEMENTS[email]["screen_remaining"]
    })

# -------------------------------
# STRIPE WEBHOOK (CRITICAL)
# -------------------------------
@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return "Invalid signature", 400

    event_type = event["type"]
    obj = event["data"]["object"]
    email = obj.get("customer_email")

    if not email:
        return "No email", 200

    email = email.lower()

    # ✅ SUBSCRIPTION ACTIVE
    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated"
    ):
        ENTITLEMENTS[email] = {
            "plan": "plus",
            "screen_remaining": SCREEN_LIMIT_PLUS
        }

    # ❌ SUBSCRIPTION CANCELED
    if event_type == "customer.subscription.deleted":
        ENTITLEMENTS[email] = {
            "plan": "free",
            "screen_remaining": 0
        }

    return "ok", 200

# -------------------------------
# ADMIN (MANUAL OVERRIDES)
# -------------------------------
@app.route("/_grant_plus", methods=["POST"])
def grant_plus():
    email = request.json.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    ENTITLEMENTS[email.lower()] = {
        "plan": "plus",
        "screen_remaining": SCREEN_LIMIT_PLUS
    }
    return jsonify({"status": "ok"})

@app.route("/_grant_trial", methods=["POST"])
def grant_trial():
    email = request.json.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    ENTITLEMENTS[email.lower()] = {
        "plan": "trial",
        "screen_remaining": SCREEN_LIMIT_PLUS
    }
    return jsonify({"status": "ok"})

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
