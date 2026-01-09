from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os, stripe

# ================== SETUP ==================
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ================== STRIPE HELPERS ==================
def has_active_subscription(email: str) -> bool:
    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if not customers.data:
            return False

        customer = customers.data[0]
        subs = stripe.Subscription.list(customer=customer.id, limit=10)

        for sub in subs.data:
            if sub.status in ("active", "trialing"):
                return True

        return False

    except Exception as e:
        print("Stripe check failed:", e)
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

# ---------- ENTITLEMENT CHECK ----------
@app.route("/entitlement/check", methods=["GET"])
def entitlement_check():
    email = request.headers.get("X-User-Email")
    if not email:
        return jsonify({"allowed": False}), 401

    allowed = has_active_subscription(email.lower())
    return jsonify({"allowed": allowed}), (200 if allowed else 403)

# ---------- SCREEN SHARE ----------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    email = request.headers.get("X-User-Email")
    if not email:
        return jsonify({"error": "Login required"}), 401

    if not has_active_subscription(email.lower()):
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

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
