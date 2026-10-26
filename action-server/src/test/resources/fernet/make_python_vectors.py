"""Regenerates python-vectors.json with Python cryptography.Fernet.

Run from the repo root:
    .venv/bin/python3 -I action-server/src/test/resources/fernet/make_python_vectors.py

The key is a throwaway TEST key generated here. It is not a key from system.yaml.
Each token is what kairon.shared.utils.Utility.encrypt_message produces for the plaintext.
"""
import json
import os
import time

import cryptography
from cryptography.fernet import Fernet

HERE = os.path.dirname(os.path.abspath(__file__))

key = Fernet.generate_key()
other = Fernet.generate_key()
fernet = Fernet(key)

claims = {
    "sub": "default",
    "bot": "6697add6b8e47524eb983373",
    "exp": 1761475200,
    "iat": 1761474300,
    "jti": "019a1f6e-7c3b-7a2d-8e4f-0123456789ab",
    "access-limit": [
        "/api/bot/.+/customer_data/.*",
        "/api/bot/.+/store_page/metadata",
        "/api/bot/.+/data/collection/.*",
        "/api/bot/.+/store_page/exec/flow",
    ],
    "type": "store_page",
}

plaintexts = [
    "hello",
    "",
    "AC1234567890abcdef",
    "unicode: café नमस्ते \U0001F600",
    "x" * 1000,
    json.dumps(claims),
    json.dumps({"sub": "default", "bot": "6697add6b8e47524eb983373", "type": "integration"}),
]

cases = [{"plaintext": text, "token": fernet.encrypt(text.encode("utf-8")).decode("utf-8")} for text in plaintexts]

# A token minted long ago. Python decrypt_message passes no ttl, so it still decrypts.
old_time = int(time.time()) - 365 * 24 * 3600
old = {"plaintext": "minted a year ago", "issued_at": old_time,
       "token": fernet.encrypt_at_time(b"minted a year ago", old_time).decode("utf-8")}

out = {
    "generator": f"python cryptography {cryptography.__version__}",
    "key": key.decode("utf-8"),
    "wrong_key": other.decode("utf-8"),
    "cases": cases,
    "old_token": old,
}
with open(os.path.join(HERE, "python-vectors.json"), "w", encoding="utf-8") as handle:
    json.dump(out, handle, indent=2, ensure_ascii=False)
    handle.write("\n")
print(f"wrote {len(cases)} cases")
