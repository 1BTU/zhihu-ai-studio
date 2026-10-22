#!/usr/bin/env python3
"""Audit the tracked release, reporting paths/line numbers without printing secrets."""
import pathlib,re,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
names=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
forbidden={'private','artifacts','reports','articles','node_modules','output','site','.venv','__pycache__'}
patterns=[re.compile(r'sk-[A-Za-z0-9]{20,}'),re.compile(r'gh[pousr]_[A-Za-z0-9]{25,}'),re.compile(r'github_pat_[A-Za-z0-9_]{25,}'),re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----')]
problems=[];count=0
for name in filter(None,names):
 p=pathlib.PurePosixPath(name)
 if any(part in forbidden for part in p.parts) or name in ('.env','daily-config.json') or p.suffix in ('.sqlite','.sqlite3','.db','.pem','.key'):
  problems.append((name,0,'private/runtime file'));continue
 data=(root/name).read_bytes();count+=1
 if b'\0' in data:
  if not name.startswith('docs/images/'):problems.append((name,0,'unexpected binary'))
  continue
 text=data.decode('utf-8',errors='replace')
 for no,line in enumerate(text.splitlines(),1):
  if any(pattern.search(line) for pattern in patterns):problems.append((name,no,'possible credential'))
for name,no,reason in problems:print(f'{name}:{no}: {reason}')
if problems:raise SystemExit(1)
print(f'Distribution audit passed: {count} tracked files; no private paths or credential patterns.')
