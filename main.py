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

# ---------------- AES BYPASS ----------------
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
        'Referer': BASE_URL,
    })
    init_resp = s.get(BASE_URL, params={'i': '1'}, timeout=TIMEOUT)
    solve_aes_challenge(s, init_resp)
    return s

def parse_response(html_text):
    match = re.search(r'class="response-content">\s*(.*?)\s*</div>', html_text, re.DOTALL)
    if match:
        return html_lib.unescape(match.group(1)).replace('<br>', '\n')
    return None

def ask_once(message):
    try:
        s = create_ai_session()
        r = s.post(BASE_URL, params={'i': '1'}, data={'model': BEST_MODEL, 'question': message}, timeout=TIMEOUT)
        solve_aes_challenge(s, r)
        result = parse_response(r.text)
        return result, None if result else ("No response", "No response")
    except Exception as e:
        return None, str(e)

# ---------------- ✅ FIXED ROUTE ----------------
@app.route('/input', methods=['GET', 'POST'])
def input_handler():

    if request.method == "GET":
        message = request.args.get('chat', '').strip()

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        message = str(data.get('chat', '')).strip()

    if not message:
        return jsonify({"error": "Provide chat input"}), 400

    try:
        answer, error = ask_once(message)

        if answer:
            return jsonify({
                "model": BEST_MODEL,
                "answer": answer
            })

        return jsonify({
            "error": error or "No response"
        }), 502

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---------------- ROOT ----------------
@app.route('/')
def home():
    return jsonify({"status": "API Running", "mode": "GET + POST enabled"})

# ---------------- RUN ----------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
