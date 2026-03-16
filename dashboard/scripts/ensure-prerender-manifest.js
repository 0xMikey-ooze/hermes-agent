const fs = require('fs');
const path = require('path');
const p = path.join(__dirname, '../.next/prerender-manifest.json');
if (!fs.existsSync(p)) {
  fs.writeFileSync(p, JSON.stringify({
    version: 4,
    routes: {},
    dynamicRoutes: {},
    notFoundRoutes: [],
    preview: {
      previewModeId: 'dev',
      previewModeSigningKey: 'dev',
      previewModeEncryptionKey: 'dev'
    }
  }));
  console.log('Created prerender-manifest.json');
}
