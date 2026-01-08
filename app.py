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

# ---------- INSTANT UNLOCK ----------
@app.route("/subscription/activate", methods=["POST"])
def activate_subscription():
    """
    Called immediately after successful Stripe Checkout.
    Works for BOTH paid subscriptions and free trials.
    """
    session_id = request.json.get("session_id")
    email = request.json.get("email")

    if not session_id or not email:
        return jsonify({"error": "Missing session_id or email"}), 400

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        print("Invalid session:", e)
        return jsonify({"error": "Invalid session"}), 400

    # ACCEPT PAID + TRIAL
    if session.payment_status not in ("paid", "no_payment_required"):
        return jsonify({"error": "Payment not completed"}), 403

    ent = load_entitlements()
    ent[email.lower()] = "active"
    save_entitlements(ent)

    return jsonify({"status": "active"}), 200

# ---------- STRIPE WEBHOOK (AUTHORITATIVE LOCK) ----------
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

    # LOCK CONDITIONS (FINAL AUTHORITY)
    if event_type in (
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        if obj.get("status") != "active" or obj.get("cancel_at_period_end", False):
            ent[email] = "canceled"

    save_entitlements(ent)
    return "", 200

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
