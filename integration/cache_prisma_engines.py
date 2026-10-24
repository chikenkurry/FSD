"""Cache the installed Prisma version's Linux engines over verified HTTPS."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'participation-service-main'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True, help='Prisma binary target reported by the Linux build image')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9.-]{1,80}', args.target):
        parser.error('Invalid binary target')
    version = subprocess.check_output(['node', '-p', "require('@prisma/engines-version').enginesVersion"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r'[a-f0-9]{40}', version):
        raise ValueError('Unexpected installed Prisma engine version')
    directory = ROOT / '.engine-artifacts'
    directory.mkdir(exist_ok=True)
    manifest = {'version': version, 'target': args.target, 'sha256': {}}
    with tempfile.TemporaryDirectory() as temporary:
        for name in ('schema-engine', 'libquery_engine.so.node'):
            url = f'https://binaries.prisma.sh/all_commits/{version}/{args.target}/{name}.gz'
            archive = Path(temporary) / (name+'.gz')
            checksum = Path(temporary) / (name+'.sha256')
            for source, target in ((url, archive), (url+'.sha256', checksum)):
                subprocess.run(['curl','--fail','--silent','--show-error',source,'--output',str(target)], check=True)
            if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum.read_text().split()[0]:
                raise ValueError(f'Checksum mismatch for {name}')
            content = gzip.decompress(archive.read_bytes())
            (directory/name).write_bytes(content)
            manifest['sha256'][name] = hashlib.sha256(content).hexdigest()
    (directory/'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
    print('Verified Prisma engines cached for '+args.target)


if __name__ == '__main__':
    main()
