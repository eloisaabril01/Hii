import re
import time
import requests
from flask import Flask, jsonify, request, session
from Crypto.Cipher import AES

app = Flask(__name__)
app.secret_key = "deepseek-api-secret-key"

MODELS = [
    "DeepSeek-V1", "DeepSeek-V2", "DeepSeek-V2.5", "DeepSeek-V3", "DeepSeek-V3-0324",
    "DeepSeek-V3.1", "DeepSeek-V3.2", "DeepSeek-R1", "DeepSeek-R1-0528", "DeepSeek-R1-Distill",
    "DeepSeek-Prover-V1", "DeepSeek-Prover-V1.5", "DeepSeek-Prover-V2", "DeepSeek-VL",
    "DeepSeek-Coder", "DeepSeek-Coder-V2", "DeepSeek-Coder-6.7B-base", "DeepSeek-Coder-6.7B-instruct"
]

sessions = {}


def create_ai_session():
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Android 12; Mobile; rv:97.0) Gecko/97.0 Firefox/97.0'
    })
    r = s.get('https://asmodeus.free.nf/')
    nums = re.findall(r'toNumbers\("([a-f0-9]+)"\)', r.text)
    key, iv, data = [bytes.fromhex(n) for n in nums[:3]]
    s.cookies.set(
        '__test',
        AES.new(key, AES.MODE_CBC, iv).decrypt(data).hex(),
        domain='asmodeus.free.nf'
    )
    s.get('https://asmodeus.free.nf/index.php?i=1')
    time.sleep(0.8)
    return s


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "name": "DeepSeek AI API",
        "version": "1.0.0",
        "endpoints": {
            "GET /models": "List all available AI models",
            "POST /init": "Initialize a chat session. Body: {\"model\": \"DeepSeek-V3\"}",
            "POST /chat": "Send a message. Body: {\"session_id\": \"...\", \"message\": \"...\"}",
            "DELETE /session/<session_id>": "End a chat session"
        }
    })


@app.route('/models', methods=['GET'])
def get_models():
    return jsonify({
        "models": [{"id": i + 1, "name": m} for i, m in enumerate(MODELS)]
    })


@app.route('/init', methods=['POST'])
def init_session():
    body = request.get_json(silent=True) or {}
    model = body.get('model', 'DeepSeek-V3')

    if model not in MODELS:
        return jsonify({"error": f"Invalid model. Choose from: {MODELS}"}), 400

    try:
        s = create_ai_session()
        session_id = f"sess_{int(time.time() * 1000)}"
        sessions[session_id] = {"session": s, "model": model, "message_count": 0}
        return jsonify({
            "session_id": session_id,
            "model": model,
            "status": "initialized"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/chat', methods=['POST'])
def chat():
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id')
    message = body.get('message', '').strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not message:
        return jsonify({"error": "message is required"}), 400
    if session_id not in sessions:
        return jsonify({"error": "Session not found. Call POST /init first."}), 404

    sess_data = sessions[session_id]
    s = sess_data['session']
    model = sess_data['model']
    sess_data['message_count'] += 1

    try:
        r = s.post(
            'https://asmodeus.free.nf/deepseek.php',
            params={'i': '1'},
            data={'model': model, 'question': message}
        )
        reply = re.search(r'<div class="response-content">(.*?)</div>', r.text, re.DOTALL)
        response_text = reply.group(1).strip() if reply else 'No response received'

        return jsonify({
            "session_id": session_id,
            "model": model,
            "message_number": sess_data['message_count'],
            "question": message,
            "answer": response_text
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/session/<session_id>', methods=['DELETE'])
def end_session(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    del sessions[session_id]
    return jsonify({"status": "session ended", "session_id": session_id})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
