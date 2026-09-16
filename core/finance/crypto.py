"""Reuse installed cryptography; secrets remain in NAS runtime storage."""
import hashlib
import hmac
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet


def secret():
    return json.loads(Path(os.getenv('CORE_FINANCE_SECRET_FILE', '/run/finance/secret.json')).read_text('utf-8'))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def encrypt(value):
    return Fernet(secret()['data_key'].encode()).encrypt(canonical(value).encode()).decode()


def decrypt(value):
    return json.loads(Fernet(secret()['data_key'].encode()).decrypt(value.encode()))


def fingerprint(domain, value):
    return hmac.new(secret()['identity_key'].encode(), (domain+'\0'+canonical(value)).encode(), hashlib.sha256).hexdigest()
