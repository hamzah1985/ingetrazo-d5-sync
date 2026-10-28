"""Refresh hashes for the explicit package allowlist; never auto-add files."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
path = root / 'CONTENTS.json'
manifest = json.loads(path.read_text(encoding='utf8'))
for entry in manifest['files']:
    target = (root / entry['path']).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError('Invalid package entry: ' + entry['path'])
    if target.suffix.lower() in ('.exe', '.dll', '.pyd', '.whl'):
        raise ValueError('Vendor binaries are not part of this package')
    data = target.read_bytes()
    entry['bytes'] = len(data)
    entry['sha256'] = hashlib.sha256(data).hexdigest()
path.write_text(json.dumps(manifest, indent=2), encoding='utf8', newline='\n')
print('Updated %d explicitly listed package hashes.' % len(manifest['files']))
