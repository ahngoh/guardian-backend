from flask import Flask, request, jsonify
from flask_cors import CORS
import os, time
from openai import OpenAI
import stripe

app = Flask(__name__)
CORS(app)

# ---- CONFIG ----
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

ENTITLEMENTS = {}
SCREEN_LIMIT = 30

# ---- HELPERS ----
def email():
    return request.headers.get("X-User-Email")

# ---- HEALTH ----
@app.route("/health")
def health():
    return {"status": "ok"}

# ---- CHAT ----
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    msg = data.get("message")

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are Guardian."},
            {"role": "user", "content": msg},
        ],
    )

    return {"reply": res.choices[0].message.content}

# ---- SCREEN SHARE ----
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    e = email()
    if not e or e not in ENTITLEMENTS:
        return {"error": "Upgrade to Plus to use screen share."}, 403

    ent = ENTITLEMENTS[e]
    if ent["remaining"] <= 0:
        return {"error": "Screen share limit reached."}, 403

    ent["remaining"] -= 1

    data = request.get_json()
    prompt = data["prompt"]
    image = data["image"]

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image",
                 "image_url": f"data:image/jpeg;base64,{image}"}
            ]
        }]
    )

    return {"reply": res.output_text}

# ---- STRIPE WEBHOOK ----
@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    event = stripe.Webhook.construct_event(
        payload, sig, STRIPE_WEBHOOK_SECRET
    )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        email = session["customer_email"]

        ENTITLEMENTS[email] = {
            "plan": "plus",
            "remaining": SCREEN_LIMIT,
            "renews": time.time() + 30 * 86400,
        }

    return {"status": "ok"}
