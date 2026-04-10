import re
import html as html_lib
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.secret_key = "deepseek-api-secret-key"

MODELS = [
    "DeepSeek-V1", "DeepSeek-V2", "DeepSeek-V2.5", "DeepSeek-V3", "DeepSeek-V3-0324",
    "DeepSeek-V3.1", "DeepSeek-V3.2", "DeepSeek-R1", "DeepSeek-R1-0528", "DeepSeek-R1-Distill",
    "DeepSeek-Prover-V1", "DeepSeek-Prover-V1.5", "DeepSeek-Prover-V2", "DeepSeek-VL",
    "DeepSeek-Coder", "DeepSeek-Coder-V2", "DeepSeek-Coder-6.7B-base", "DeepSeek-Coder-6.7B-instruct"
]

BEST_MODEL = "DeepSeek-V3-0324"

# ─────────────────────────────────────────────
# NOTE: Vercel is STATELESS — no in-memory session store.
# All endpoints are stateless. The /init + /chat flow
# is kept for API compatibility but each call is independent.
# ─────────────────────────────────────────────


def create_ai_session():
    """Create a fresh requests session with browser-like headers."""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://asmodeus.free.nf/deepseek.php',
        'Origin': 'https://asmodeus.free.nf',
        'Connection': 'keep-alive',
    })
    # Initialize session cookie (some PHP pages require a GET first)
    try:
        s.get('https://asmodeus.free.nf/deepseek.php', params={'i': '1'}, timeout=15)
    except Exception:
        pass  # Continue even if init GET fails
    return s


def parse_response(html_text):
    """
    Try multiple patterns to extract AI response from the PHP page HTML.
    Falls back gracefully with a raw snippet for debugging.
    """
    # Pattern 1: original
    match = re.search(r'class="response-content">\s*(.*?)\s*</div>', html_text, re.DOTALL)
    if match:
        raw = match.group(1).strip()
        return html_lib.unescape(raw).replace('<br />', '\n').replace('<br>', '\n')

    # Pattern 2: id-based
    match = re.search(r'id="response"[^>]*>\s*(.*?)\s*</div>', html_text, re.DOTALL)
    if match:
        raw = match.group(1).strip()
        return html_lib.unescape(raw).replace('<br />', '\n').replace('<br>', '\n')

    # Pattern 3: any <p> tag content
    match = re.search(r'<p[^>]*>(.*?)</p>', html_text, re.DOTALL)
    if match:
        raw = match.group(1).strip()
        return html_lib.unescape(raw).replace('<br />', '\n').replace('<br>', '\n')

    # No match — return raw snippet to help debug
    return f"PARSE_FAILED — raw snippet: {html_text[:500]}"


def ask_once(message, model=BEST_MODEL):
    """Send one stateless question to the AI backend and return the answer."""
    s = create_ai_session()
    r = s.post(
        'https://asmodeus.free.nf/deepseek.php',
        params={'i': '1'},
        data={'model': model, 'question': message},
        timeout=30
    )
    r.raise_for_status()
    return parse_response(r.text)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "name": "DeepSeek AI API — Freight & Logistics",
        "version": "2.0.0",
        "note": "Hosted on Vercel (stateless). Sessions are per-request only.",
        "default_model": BEST_MODEL,
        "endpoints": {
            "GET  /input?chat=...":             "Quick one-shot question",
            "GET  /input?chat=...&model=...":   "Quick question with specific model",
            "GET  /models":                     "List all available AI models",
            "GET  /debug?chat=...":             "Show raw HTML from backend (for debugging)",
            "POST /init":                       "Initialize session (compatibility stub)",
            "POST /chat":                       "Send a message (stateless on Vercel)",
            "DELETE /session/<session_id>":     "End session (no-op on Vercel)"
        }
    })


@app.route('/models', methods=['GET'])
def get_models():
    return jsonify({
        "models": [{"id": i + 1, "name": m} for i, m in enumerate(MODELS)]
    })


@app.route('/input', methods=['GET'])
def quick_input():
    message = request.args.get('chat', '').strip()
    model = request.args.get('model', BEST_MODEL).strip()

    if not message:
        return jsonify({"error": "Provide a question using ?chat=your question"}), 400
    if model not in MODELS:
        return jsonify({"error": f"Invalid model. Choose from: {MODELS}"}), 400

    try:
        answer = ask_once(message, model)
        return jsonify({
            "model": model,
            "question": message,
            "answer": answer
        })
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to AI backend timed out. Try again."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/debug', methods=['GET'])
def debug():
    """
    Returns the raw HTML from the AI backend so you can inspect
    what the PHP page is actually returning on Vercel.
    """
    message = request.args.get('chat', 'hello').strip()
    try:
        s = create_ai_session()
        r = s.post(
            'https://asmodeus.free.nf/deepseek.php',
            params={'i': '1'},
            data={'model': BEST_MODEL, 'question': message},
            timeout=30
        )
        return jsonify({
            "status_code": r.status_code,
            "response_url": r.url,
            "content_type": r.headers.get('Content-Type', ''),
            "raw_html_snippet": r.text[:3000],
            "parsed_answer": parse_response(r.text)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/init', methods=['POST'])
def init_session():
    """
    Compatibility stub. On Vercel (stateless), we can't store sessions
    in memory across requests. Returns a fake session_id that encodes
    the model choice. Use /input for true stateless calls.
    """
    body = request.get_json(silent=True) or {}
    model = body.get('model', BEST_MODEL)

    if model not in MODELS:
        return jsonify({"error": f"Invalid model. Choose from: {MODELS}"}), 400

    session_id = f"sess_{int(time.time() * 1000)}_{model}"
    return jsonify({
        "session_id": session_id,
        "model": model,
        "status": "initialized",
        "warning": "Vercel is stateless — pass session_id + model in every /chat call."
    })


@app.route('/chat', methods=['POST'])
def chat():
    """
    Stateless chat endpoint. Since Vercel resets memory between requests,
    pass 'model' in the body every time. session_id is accepted but ignored.
    """
    body = request.get_json(silent=True) or {}
    message = body.get('message', '').strip()
    model = body.get('model', BEST_MODEL).strip()

    if not message:
        return jsonify({"error": "message is required"}), 400
    if model not in MODELS:
        return jsonify({"error": f"Invalid model. Choose from: {MODELS}"}), 400

    try:
        answer = ask_once(message, model)
        return jsonify({
            "model": model,
            "question": message,
            "answer": answer
        })
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request to AI backend timed out. Try again."}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/session/<session_id>', methods=['DELETE'])
def end_session(session_id):
    # No-op on Vercel since there's no persistent session store
    return jsonify({
        "status": "session ended (no-op on Vercel)",
        "session_id": session_id
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
