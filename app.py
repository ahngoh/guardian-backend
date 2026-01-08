from flask import Flask, request, jsonify
from flask_cors import CORS
import stripe
import os
from openai import OpenAI

# ---------------- CONFIG ----------------
app = Flask(__name__)
CORS(app)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# email -> active(bool)
ENTITLEMENTS = {}

# ---------------- HELPERS ----------------
def get_email():
    e = request.headers.get("X-User-Email")
    return e.lower() if e else None

def has_plus(email):
    return ENTITLEMENTS.get(email, False)

# ---------------- ROUTES ----------------
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/chat", methods=["POST"])
def chat():
    msg = request.json.get("message")
    if not msg:
        return {"error": "No message"}, 400

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":msg}]
    )

    return {"reply": res.choices[0].message.content}

@app.route("/analyze_screen", methods=["POST"])
def analyze():
    email = get_email()
    if not email or not has_plus(email):
        return {"error": "Upgrade to Plus to use screen share."}, 403

    data = request.json
    if not data.get("prompt") or not data.get("image"):
        return {"error":"Missing data"}, 400

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role":"user",
            "content":[
                {"type":"input_text","text":data["prompt"]},
                {"type":"input_image","image_url":f"data:image/jpeg;base64,{data['image']}"}
            ]
        }]
    )

    return {"reply": res.output_text}

# ---------------- STRIPE WEBHOOK ----------------
@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")
    endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)

    if event["type"] in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted"
    ):
        sub = event["data"]["object"]
        email = sub["customer_email"].lower()
        active = sub["status"] == "active"
        ENTITLEMENTS[email] = active

    return "", 200

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
