#!/usr/bin/env python3
"""Initialize local configuration and a hashed web account without publishing."""
import getpass,hashlib,json,pathlib,secrets,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'studio'))
import auth

def main():
 config=ROOT/'daily-config.json'
 if not config.exists():config.write_bytes((ROOT/'daily-config.example.json').read_bytes());config.chmod(0o600)
 auth.FILE.parent.mkdir(parents=True,exist_ok=True)
 if auth.FILE.exists():print('Web account already exists; not overwritten.');return
 username=input('Web username: ').strip()
 password=getpass.getpass('Web password: ')
 confirm=getpass.getpass('Confirm password: ')
 if not username or len(password)<10 or password!=confirm:raise SystemExit('Use a username and matching password of at least 10 characters.')
 salt=secrets.token_hex(24)
 auth.save({'username':username,'salt':salt,'hash':hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex(),'sessions':{}})
 print('Account initialized. Publishing and email notifications are disabled by default.')

if __name__=='__main__':main()
