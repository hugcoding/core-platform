"""Initialize local owner credentials without printing or overwriting secrets."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from cryptography.fernet import Fernet


def main():
    root=Path(os.getenv('CORE_FINANCE_SECRET_DIR','/run/finance'))
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=root/'secret.json'
    if target.exists():
        print('finance_secrets_already_initialized');return
    code=secrets.token_urlsafe(24)
    values={'data_key':Fernet.generate_key().decode(),'session_key':Fernet.generate_key().decode(),
        'identity_key':secrets.token_hex(32),'access_hash':hashlib.sha256(code.encode()).hexdigest(),'key_version':1}
    with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        json.dump(values,stream)
    with os.fdopen(os.open(root/'access-code.txt',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:
        stream.write('CORE Finance - persoonlijke toegangscode\n\n'+code+'\n\nNiet delen of in Jira/Git plaatsen.\n')
    print('finance_secrets_initialized')


if __name__=='__main__':main()
