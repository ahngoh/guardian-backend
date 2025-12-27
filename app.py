from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI

# ---------------- APP SETUP ----------------
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ---------------- HEALTH CHECK ----------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

# ---------------- CHAT ENDPOINT ----------------
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


# ---------------- SCREEN ANALYSIS ENDPOINT ----------------
@app.route("/analyze_screen", methods=["POST"])
def analyze_screen():
    data = request.get_json(force=True)

    prompt = data.get("prompt")
    image_b64 = data.get("image")

    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    if not image_b64:
        return jsonify({"error": "No image provided"}), 400

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

        # extract assistant text
        for item in response.output:
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    return jsonify({"reply": part.get("text")})

        return jsonify({"error": "No assistant text returned"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
