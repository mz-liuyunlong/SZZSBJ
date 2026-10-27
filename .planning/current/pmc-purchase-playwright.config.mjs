// Local verification only: isolated port, existing bundled Node, no dependency changes.
export default {
  testDir: 'C:/Users/treas/Desktop/work/SZZSBJ/frontend/e2e',
  outputDir: 'C:/Users/treas/Desktop/work/SZZSBJ/.planning/current/pmc-purchase-e2e-results',
  use: { baseURL: 'http://127.0.0.1:4291', channel: 'msedge' },
  webServer: {
    command: '"C:/Users/treas/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe" "C:/Users/treas/Desktop/work/SZZSBJ/frontend/node_modules/vite/bin/vite.js" --config ../.planning/current/pmc-purchase-vite.config.ts --host 127.0.0.1 --port 4291 --strictPort',
    cwd: 'C:/Users/treas/Desktop/work/SZZSBJ/frontend',
    url: 'http://127.0.0.1:4291',
    reuseExistingServer: false,
  },
};
