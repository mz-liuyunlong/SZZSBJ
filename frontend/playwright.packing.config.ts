/** Focused approval acceptance using the same Node executable as the test runner. */
import base from "./playwright.config";

export default {
  ...base,
  webServer: {
    command: `"${process.execPath}" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort`,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
};
