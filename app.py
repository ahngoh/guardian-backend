from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, stripe

# ================== SETUP ==================
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

ENTITLEMENT_FILE = "entitlements.json"

# ================== HELPERS ==================
def load_entitlements():
    if not os.path.exists(ENTITLEMENT_FILE):
        return {}
    with open(ENTITLEMENT_FILE, "r") as f:
        return json.load(f)

def save_entitlements(data):
    with open(ENTITLEMENT_FILE, "w") as f:
        json.dump(data, f)

def has_plus(email):
    ent = load_entitlements()
    return ent.get(email.lower()) == "active"

def get_customer_email(customer_id):
    try:
        customer = stripe.Customer.retrieve(customer_id)
        return customer.email
    except Exception as e:
        print("Failed to fetch customer email:", e)
        return None

# ================== ROUTES ==================

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

# ---------- CHAT ----------
@app.route("/chat", methods=["POST"])
def chat():
    msg = request.json.get("message")
    if not msg:
        return jsonify({"error": "No message"}), 400

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a calm step-by-step assistant."},
            {"role": "user", "content": msg}
        ]
    )

    return jsonify({"reply": res.choices[0].message.content})

# ---------- SCREEN SHARE ----------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    email = request.headers.get("X-User-Email")
    if not email:
        return jsonify({"error": "Login required"}), 401

    if not has_plus(email):
        return jsonify({"error": "Upgrade to Plus to use screen share."}), 403

    data = request.json
    prompt = data.get("prompt")
    image = data.get("image")

    if not prompt or not image:
        return jsonify({"error": "Missing prompt or image"}), 400

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{image}"}
            ]
        }]
    )

    return jsonify({"reply": res.output_text})

# ---------- STRIPE WEBHOOK ----------
@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print("Webhook verification failed:", e)
        return "", 400

    ent = load_entitlements()
    obj = event["data"]["object"]
    event_type = event["type"]

    if "customer" not in obj:
        return "", 200

    email = get_customer_email(obj["customer"])
    if not email:
        return "", 200

    email = email.lower()

    # INSTANT LOCK RULE:
    # - canceled
    # - unpaid
    # - incomplete
    # - cancel_at_period_end = True
    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        if obj["status"] == "active" and not obj.get("cancel_at_period_end", False):
            ent[email] = "active"
        else:
            ent[email] = "canceled"

    if event_type == "customer.subscription.deleted":
        ent[email] = "canceled"

    save_entitlements(ent)
    return "", 200

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
