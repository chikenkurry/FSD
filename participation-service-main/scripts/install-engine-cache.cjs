const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const { enginesVersion } = require('@prisma/engines-version');

async function install() {
  const directory = '/engine-artifacts';
  if (!fs.existsSync(path.join(directory, 'manifest.json'))) return;
  const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json'), 'utf8'));
  const target = await require('@prisma/get-platform').getBinaryTargetForCurrentPlatform();
  if (manifest.version !== enginesVersion || manifest.target !== target) {
    throw new Error('Engine cache does not match the installed Prisma version and platform');
  }
  for (const [source, destination] of [
    ['schema-engine', `schema-engine-${target}`],
    ['libquery_engine.so.node', `libquery_engine-${target}.so.node`],
  ]) {
    const content = fs.readFileSync(path.join(directory, source));
    if (crypto.createHash('sha256').update(content).digest('hex') !== manifest.sha256[source]) {
      throw new Error(`Invalid cached engine checksum: ${source}`);
    }
    const output = path.join('node_modules/@prisma/engines', destination);
    fs.writeFileSync(output, content);
    if (source === 'schema-engine') fs.chmodSync(output, 0o755);
  }
}
install().catch(error => { console.error(error.message); process.exit(1); });
