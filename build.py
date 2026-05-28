#!/usr/bin/env python3
"""
build.py - Produce a password-gated, encrypted index.html from the master
Steel-Stud-Leads-Dashboard.html, ready to publish on GitHub Pages.

How it works
------------
The master HTML has a `var DATA=[...]` block with full customer details. This
script:
  1. Reads the password from config.local.txt (gitignored).
  2. Extracts the DATA array (and a few other identifying fields) from the
     master HTML.
  3. Encrypts the data using AES-GCM with a key derived via PBKDF2-SHA256
     (300,000 iterations) from the password and a fresh random salt.
  4. Writes index.html, which on load shows a password screen; once the
     correct password is entered, the data is decrypted in the browser
     (Web Crypto API), assigned to window.DATA, and the dashboard renders.

No password ever leaves the visitor's browser, and the encrypted blob is
useless without it. The repo can therefore be public on GitHub Pages.

Usage
-----
    python build.py                # uses config.local.txt
    python build.py --password X   # one-shot override (CI only)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    print(
        "ERROR: the 'cryptography' package is missing.\n"
        "Install it with:  python -m pip install cryptography",
        file=sys.stderr,
    )
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "Steel-Stud-Leads-Dashboard.html"
OUTPUT = ROOT / "index.html"
CONFIG = ROOT / "config.local.txt"

PBKDF2_ITERATIONS = 300_000
SALT_BYTES = 16
IV_BYTES = 12  # AES-GCM standard nonce length


def load_password(cli_password: str | None) -> str:
    if cli_password:
        return cli_password.strip()
    env_password = os.environ.get("DASHBOARD_PASSWORD")
    if env_password:
        return env_password.strip()
    if not CONFIG.exists():
        raise SystemExit(
            f"Missing {CONFIG}.\n"
            "Create it from config.sample.txt and put the shared password "
            "on the first non-comment line."
        )
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise SystemExit(f"{CONFIG} has no password.")


def encrypt_blob(plaintext: str, password: str) -> dict[str, str]:
    salt = secrets.token_bytes(SALT_BYTES)
    iv = secrets.token_bytes(IV_BYTES)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    key = kdf.derive(password.encode("utf-8"))
    ct = AESGCM(key).encrypt(iv, plaintext.encode("utf-8"), None)
    return {
        "ct": base64.b64encode(ct).decode("ascii"),
        "iv": base64.b64encode(iv).decode("ascii"),
        "salt": base64.b64encode(salt).decode("ascii"),
        "iter": PBKDF2_ITERATIONS,
    }


def extract_data_block(html: str) -> tuple[str, str]:
    """Return (data_array_text, meta_object_text)."""
    m = re.search(r"var\s+DATA\s*=\s*(\[[\s\S]*?\n\]);", html)
    if not m:
        raise SystemExit("Could not locate `var DATA = [...]` in master HTML.")
    data_text = m.group(1)
    m2 = re.search(r"var\s+META\s*=\s*(\{[^}]*\});", html)
    if not m2:
        raise SystemExit("Could not locate `var META = {...}` in master HTML.")
    meta_text = m2.group(1)
    return data_text, meta_text


# The gate UI + Web Crypto decryption shim that gets injected into index.html.
# It replaces the `var DATA=[...]` block (the empty array stays so the existing
# dashboard code still parses), and wraps the page in a login overlay.
GATE_CSS = """
#sg-gate{position:fixed;inset:0;background:#0e1620;z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:#e8eef5}
#sg-gate .sg-card{background:#16212f;border:1px solid #2c3d54;border-radius:14px;padding:30px 32px;max-width:380px;width:100%;box-shadow:0 12px 40px rgba(0,0,0,.5)}
#sg-gate .sg-eb{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#3b82f6;font-weight:700;margin-bottom:6px}
#sg-gate h2{font-size:20px;font-weight:700;margin:0 0 6px}
#sg-gate p.sg-sub{color:#8da2bb;font-size:13px;margin:0 0 22px;line-height:1.5}
#sg-gate label{display:block;font-size:11px;color:#8da2bb;text-transform:uppercase;letter-spacing:.04em;font-weight:600;margin-bottom:5px}
#sg-gate input{width:100%;background:#0e1620;border:1px solid #2c3d54;border-radius:7px;color:#e8eef5;font-size:14px;padding:9px 11px;font-family:inherit;margin-bottom:14px;box-sizing:border-box}
#sg-gate input:focus{outline:none;border-color:#3b82f6}
#sg-gate button{width:100%;background:#3b82f6;border:1px solid #3b82f6;border-radius:8px;color:#fff;font-size:14px;font-weight:600;padding:10px;cursor:pointer;font-family:inherit}
#sg-gate button:hover{background:#2f6fd6}
#sg-gate button:disabled{opacity:.6;cursor:not-allowed}
#sg-gate .sg-err{color:#fca5a5;font-size:12.5px;margin-top:-6px;margin-bottom:12px;min-height:16px}
#sg-gate .sg-foot{font-size:11px;color:#8da2bb;margin-top:16px;text-align:center;line-height:1.6}
body.sg-locked{overflow:hidden}
"""

GATE_HTML = """
<div id="sg-gate"><div class="sg-card">
  <div class="sg-eb">Steel &amp; Stud &middot; Private</div>
  <h2>Leads Dashboard</h2>
  <p class="sg-sub">This dashboard contains customer contact details and is restricted to authorised team members. Enter the shared credentials to continue.</p>
  <form id="sg-form" autocomplete="off">
    <label for="sg-id">User ID</label>
    <input id="sg-id" type="text" autocomplete="username" placeholder="your team handle" required>
    <label for="sg-pw">Password</label>
    <input id="sg-pw" type="password" autocomplete="current-password" placeholder="shared team password" required>
    <div class="sg-err" id="sg-err"></div>
    <button type="submit" id="sg-btn">Unlock dashboard</button>
  </form>
  <div class="sg-foot">Steel &amp; Stud &middot; KD Digital<br>Data is decrypted locally in your browser.</div>
</div></div>
"""

GATE_JS_TEMPLATE = r"""
<script id="sg-encrypted" type="application/json">__BLOB_JSON__</script>
<script>
document.body.classList.add('sg-locked');
(function(){
  var BLOB = JSON.parse(document.getElementById('sg-encrypted').textContent);
  function b64d(s){var bin=atob(s),out=new Uint8Array(bin.length);for(var i=0;i<bin.length;i++)out[i]=bin.charCodeAt(i);return out;}
  async function deriveKey(pw, salt, iter){
    var enc = new TextEncoder();
    var base = await crypto.subtle.importKey('raw', enc.encode(pw), {name:'PBKDF2'}, false, ['deriveKey']);
    return crypto.subtle.deriveKey(
      {name:'PBKDF2', salt: salt, iterations: iter, hash: 'SHA-256'},
      base,
      {name:'AES-GCM', length: 256},
      false,
      ['decrypt']
    );
  }
  function escapeForBoot(s){return s;}
  async function attempt(id, pw){
    try{
      var key = await deriveKey(pw, b64d(BLOB.salt), BLOB.iter);
      var plain = await crypto.subtle.decrypt({name:'AES-GCM', iv: b64d(BLOB.iv)}, key, b64d(BLOB.ct));
      var json = new TextDecoder().decode(plain);
      var payload = JSON.parse(json);
      window.DATA.length = 0;
      payload.DATA.forEach(function(r){ window.DATA.push(r); });
      Object.keys(payload.META).forEach(function(k){ window.META[k] = payload.META[k]; });
      try { sessionStorage.setItem('sg-id', id); } catch(e){}
      var gate = document.getElementById('sg-gate');
      if(gate) gate.parentNode.removeChild(gate);
      document.body.classList.remove('sg-locked');
      if (typeof window.__init === 'function') window.__init();
      return true;
    } catch(e){
      return false;
    }
  }
  document.getElementById('sg-form').addEventListener('submit', async function(ev){
    ev.preventDefault();
    var btn = document.getElementById('sg-btn');
    var err = document.getElementById('sg-err');
    var id = document.getElementById('sg-id').value.trim();
    var pw = document.getElementById('sg-pw').value;
    if(!id || !pw){ err.textContent = 'Both fields are required.'; return; }
    btn.disabled = true; btn.textContent = 'Decrypting…'; err.textContent = '';
    var ok = await attempt(id, pw);
    if(!ok){
      err.textContent = 'Wrong user ID or password. Please try again.';
      btn.disabled = false; btn.textContent = 'Unlock dashboard';
      document.getElementById('sg-pw').value = '';
      document.getElementById('sg-pw').focus();
    }
  });
  setTimeout(function(){ document.getElementById('sg-id').focus(); }, 50);
})();
</script>
"""


def transform(html: str, encrypted: dict) -> str:
    # 1. Replace the DATA array body with an empty placeholder (the gate fills it in).
    html = re.sub(
        r"var\s+DATA\s*=\s*\[[\s\S]*?\n\];",
        "var DATA=[];",
        html,
        count=1,
    )
    # 2. Replace the bare `(function init(){ ... })();` IIFE with a named handler
    #    that the gate can call after decryption. We rename the function and store
    #    a reference on window.__init instead of self-invoking immediately.
    html = re.sub(
        r"\(function\s+init\s*\(\)\s*\{",
        "window.__init=function(){",
        html,
        count=1,
    )
    html = re.sub(
        r"\}\)\(\);\s*</script>",
        "};</script>",
        html,
        count=1,
    )
    # 3. Inject gate CSS into <head>.
    css_tag = "<style id=\"sg-gate-css\">" + GATE_CSS.strip() + "</style>"
    html = html.replace("</head>", css_tag + "</head>", 1)
    # 4. Inject gate overlay HTML immediately after <body ...>.
    html = re.sub(
        r"(<body[^>]*>)",
        r"\1" + GATE_HTML.strip(),
        html,
        count=1,
    )
    # 5. Inject the decryption script before </body>. Blob is embedded as a
    #    <script type="application/json"> so quoting is trivial.
    blob_json = json.dumps(encrypted, separators=(",", ":"))
    gate_js = GATE_JS_TEMPLATE.replace("__BLOB_JSON__", blob_json)
    html = html.replace("</body>", gate_js + "</body>", 1)
    return html


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", help="Override password (CI only).")
    parser.add_argument(
        "--master",
        default=str(MASTER),
        help="Path to the plaintext master HTML.",
    )
    parser.add_argument(
        "--output", default=str(OUTPUT), help="Path to write the gated HTML."
    )
    args = parser.parse_args()

    pw = load_password(args.password)
    master_path = Path(args.master)
    if not master_path.exists():
        raise SystemExit(f"Master HTML not found: {master_path}")

    html = master_path.read_text(encoding="utf-8")
    data_text, meta_text = extract_data_block(html)

    # The DATA and META blocks are JS literals. They are valid JSON in this
    # dashboard (double-quoted keys/values, no trailing commas in objects),
    # but DATA may end with a trailing comma after the last record (allowed
    # in JS, not in JSON). Strip a trailing comma if present.
    data_clean = re.sub(r",(\s*\])\s*$", r"\1", data_text.strip())
    meta_clean = meta_text.strip()
    # META uses JS-style unquoted keys; convert to JSON.
    meta_json = re.sub(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', meta_clean)

    try:
        data_obj = json.loads(data_clean)
        meta_obj = json.loads(meta_json)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse DATA/META as JSON: {e}")

    payload = json.dumps({"DATA": data_obj, "META": meta_obj}, separators=(",", ":"))
    encrypted = encrypt_blob(payload, pw)

    output_html = transform(html, encrypted)
    Path(args.output).write_text(output_html, encoding="utf-8")

    pw_fp = hashlib.sha256(pw.encode("utf-8")).hexdigest()[:12]
    print(
        f"Built {args.output}\n"
        f"  records encrypted:    {len(data_obj)}\n"
        f"  PBKDF2 iterations:    {PBKDF2_ITERATIONS:,}\n"
        f"  password fingerprint: {pw_fp}  (sha256 prefix; same fp = same pw)\n"
    )


if __name__ == "__main__":
    main()
