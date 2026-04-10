import os
import re
import html as html_lib
import time
import requests
from flask import Flask, jsonify, request
from Crypto.Cipher import AES

app = Flask(__name__)
app.secret_key = "deepseek-api-secret-key"

MODELS = [
    "DeepSeek-V1", "DeepSeek-V2", "DeepSeek-V2.5", "DeepSeek-V3", "DeepSeek-V3-0324",
    "DeepSeek-V3.1", "DeepSeek-V3.2", "DeepSeek-R1", "DeepSeek-R1-0528", "DeepSeek-R1-Distill",
    "DeepSeek-Prover-V1", "DeepSeek-Prover-V1.5", "DeepSeek-Prover-V2", "DeepSeek-VL",
    "DeepSeek-Coder", "DeepSeek-Coder-V2", "DeepSeek-Coder-6.7B-base", "DeepSeek-Coder-6.7B-instruct"
]

BEST_MODEL = "DeepSeek-V3-0324"

BASE_URL = 'https://asmodeus.free.nf/deepseek.php'
TIMEOUT = 25

USER_AGENTS = [
    'Mozilla/5.0 (Android 12; Mobile; rv:97.0) Gecko/97.0 Firefox/97.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]

sessions = {}


def solve_aes_challenge(session, response):
    text = response.text
    if 'slowAES' not in text and 'aes.js' not in text:
        return False
    match = re.search(
        r'toNumbers\("([0-9a-f]+)"\)\s*,\s*b\s*=\s*toNumbers\("([0-9a-f]+)"\)\s*,\s*c\s*=\s*toNumbers\("([0-9a-f]+)"\)',
        text
    )
    if not match:
        return False
    key = bytes.fromhex(match.group(1))
    iv  = bytes.fromhex(match.group(2))
    ct  = bytes.fromhex(match.group(3))
    cipher = AES.new(key, AES.MODE_CBC, iv)
    cookie_val = cipher.decrypt(ct).hex()
    redirect_match = re.search(r'location\.href\s*=\s*"([^"]+)"', text)
    redirect_path = redirect_match.group(1) if redirect_match else '/?i=1'
    from urllib.parse import urljoin
    redirect_url = urljoin(BASE_URL, redirect_path)
    session.cookies.set('__test', cookie_val, domain='asmodeus.free.nf')
    session.get(redirect_url, timeout=TIMEOUT)
    return True


def create_ai_session(ua_index=0):
    s = requests.Session()
    s.headers.update({
        'User-Agent': USER_AGENTS[ua_index % len(USER_AGENTS)],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': BASE_URL,
    })
    init_resp = s.get(BASE_URL, params={'i': '1'}, timeout=TIMEOUT)
    solve_aes_challenge(s, init_resp)
    return s


def parse_response(html_text):
    patterns = [
        r'class="response-content">\s*(.*?)\s*</div>',
        r'class=\'response-content\'>\s*(.*?)\s*</div>',
        r'response-content[^>]*>\s*(.*?)\s*</div>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, re.DOTALL)
        if match:
            raw = match.group(1).strip()
            if raw:
                return html_lib.unescape(raw).replace('<br />', '\n').replace('<br>', '\n')
    return None


def ask_once(message, model=BEST_MODEL):
    last_error = None
    for attempt in range(len(USER_AGENTS)):
        try:
            s = create_ai_session(ua_index=attempt)
            r = s.post(
                BASE_URL,
                params={'i': '1'},
                data={'model': model, 'question': message},
                timeout=TIMEOUT
            )
            if solve_aes_challenge(s, r):
                r = s.post(
                    BASE_URL,
                    params={'i': '1'},
                    data={'model': model, 'question': message},
                    timeout=TIMEOUT
                )
            result = parse_response(r.text)
            if result is not None:
                return result, None
            last_error = f"Response parsing failed (HTTP {r.status_code}). The upstream service may be blocking this server's IP."
        except requests.exceptions.Timeout:
            last_error = "Request timed out — the upstream service took too long to respond."
        except requests.exceptions.RequestException as e:
            last_error = f"Network error: {str(e)}"
    return None, last_error


@app.route('/input', methods=['GET'])
def quick_input():
    message = request.args.get('chat', '').strip()
    if not message:
        return jsonify({"error": "Provide a question using ?chat=your question"}), 400
    try:
        answer, error = ask_once(message)
        if answer is not None:
            return jsonify({
                "model": BEST_MODEL,
                "question": message,
                "answer": answer
            })
        return jsonify({
            "error": error or "No response received from upstream service.",
            "model": BEST_MODEL,
            "question": message
        }), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug', methods=['GET'])
def debug_upstream():
    message = request.args.get('chat', 'hello').strip()
    try:
        s = create_ai_session()
        init_resp = s.get(BASE_URL, params={'i': '1'}, timeout=TIMEOUT)
        aes_triggered = 'aes.js' in init_resp.text or 'slowAES' in init_resp.text
        aes_solved = solve_aes_challenge(s, init_resp) if aes_triggered else False
        r = s.post(
            BASE_URL,
            params={'i': '1'},
            data={'model': BEST_MODEL, 'question': message},
            timeout=TIMEOUT
        )
        post_aes = solve_aes_challenge(s, r)
        if post_aes:
            r = s.post(BASE_URL, params={'i': '1'}, data={'model': BEST_MODEL, 'question': message}, timeout=TIMEOUT)
        parsed = parse_response(r.text)
        return jsonify({
            "http_status": r.status_code,
            "response_length": len(r.text),
            "parsed_answer": parsed,
            "aes_challenge_on_init": aes_triggered,
            "aes_challenge_solved": aes_solved or post_aes,
            "has_response_content_class": 'response-content' in r.text,
            "raw_snippet": r.text[:600],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "name": "DeepSeek AI API — Freight & Logistics",
        "version": "1.1.0",
        "default_model": BEST_MODEL,
        "endpoints": {
            "GET /input?chat=...": "Quick one-shot question using DeepSeek-V3-0324",
            "GET /models": "List all available AI models",
            "GET /debug?chat=...": "Debug upstream service response (use to diagnose Vercel issues)",
            "POST /init": "Initialize a chat session. Body: {\"model\": \"DeepSeek-V3-0324\"}",
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
    model = body.get('model', BEST_MODEL)

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
        return jsonify({"error": "Session not found. Call POST /init first. Note: sessions are not persisted across serverless restarts."}), 404

    sess_data = sessions[session_id]
    s = sess_data['session']
    model = sess_data['model']
    sess_data['message_count'] += 1

    try:
        r = s.post(
            BASE_URL,
            params={'i': '1'},
            data={'model': model, 'question': message},
            timeout=TIMEOUT
        )
        response_text = parse_response(r.text)

        if response_text is None:
            return jsonify({
                "error": "No response received from upstream service. The upstream service may be blocking this server's IP.",
                "session_id": session_id,
                "model": model,
            }), 502

        return jsonify({
            "session_id": session_id,
            "model": model,
            "message_number": sess_data['message_count'],
            "question": message,
            "answer": response_text
        })
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timed out — the upstream service took too long to respond."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/session/<session_id>', methods=['DELETE'])
def end_session(session_id):
    if session_id not in sessions:
        return jsonify({"error": "Session not found"}), 404
    del sessions[session_id]
    return jsonify({"status": "session ended", "session_id": session_id})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
