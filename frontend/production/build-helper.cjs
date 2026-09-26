const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const prodDir = path.resolve(__dirname);
console.log('[FlashGuard Build Helper] Target directory:', prodDir);

try {
  execSync('npm run build', { cwd: prodDir, stdio: 'inherit' });
} catch (e) {
  console.log('[FlashGuard Build Helper] Retrying with vite build directly...');
  execSync('npx vite build', { cwd: prodDir, stdio: 'inherit' });
}

const srcDist = path.join(prodDir, 'dist');
const nestedDist = path.join(prodDir, 'frontend', 'production', 'dist');

if (fs.existsSync(srcDist)) {
  fs.mkdirSync(nestedDist, { recursive: true });
  fs.cpSync(srcDist, nestedDist, { recursive: true });
  console.log('[FlashGuard Build Helper] Mirrored dist to:', nestedDist);
}
