from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, json, stripe

# ================== SETUP ==================
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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

def get_customer_by_email(email):
    customers = stripe.Customer.list(email=email, limit=1)
    return customers.data[0] if customers.data else None

def has_active_subscription(email):
    customer = get_customer_by_email(email)
    if not customer:
        return False

    subs = stripe.Subscription.list(customer=customer.id, limit=10)
    for sub in subs.data:
        if sub.status in ("active", "trialing"):
            return True

    return False

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

# ---------- SCREEN SHARE (LIVE STRIPE CHECK) ----------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    email = request.headers.get("X-User-Email")
    if not email:
        return jsonify({"error": "Login required"}), 401

    email = email.lower()

    # 🔥 LIVE STRIPE CHECK (SOURCE OF TRUTH)
    if not has_active_subscription(email):
        return jsonify({"error": "Upgrade to Plus to use screen share."}), 403

    # Cache entitlement for performance (optional)
    ent = load_entitlements()
    ent[email] = "active"
    save_entitlements(ent)

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

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
