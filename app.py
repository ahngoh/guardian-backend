from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import stripe

# ---------------- APP SETUP ----------------
app = Flask(__name__)
CORS(app)

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

client = OpenAI(api_key=OPENAI_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# ---------------- HELPERS ----------------
def get_user_email():
    email = request.headers.get("X-User-Email")
    return email.lower() if email else None

def has_active_subscription(email):
    customers = stripe.Customer.list(email=email, limit=1).data
    if not customers:
        return False

    subs = stripe.Subscription.list(
        customer=customers[0].id,
        status="active",
        limit=1
    )
    return len(subs.data) > 0

# ---------------- ROUTES ----------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    message = data.get("message")

    if not message:
        return jsonify({"error": "No message"}), 400

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a calm step-by-step assistant."},
            {"role": "user", "content": message}
        ]
    )

    return jsonify({"reply": resp.choices[0].message.content})

@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    email = get_user_email()
    if not email:
        return jsonify({"error": "Login required"}), 401

    if not has_active_subscription(email):
        return jsonify({"error": "Upgrade to Plus to use screen share."}), 403

    data = request.json
    prompt = data.get("prompt")
    image = data.get("image")

    if not prompt or not image:
        return jsonify({"error": "Missing data"}), 400

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:image/jpeg;base64,{image}"
                }
            ]
        }]
    )

    return jsonify({"reply": resp.output_text})

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
