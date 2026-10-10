import '@ant-design/v5-patch-for-react-19';
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { queryClient } from "@/api/queryClient";
import "@/index.css";
import "@/styles/globalMotion.css";
import "@/styles/globalInteractionMotion.css";
import App from "@/App";
// PUBLIC_DIRECT_AUTH_HASH_REDIRECT_START
const PUBLIC_DIRECT_AUTH_HASH_PATHS = new Set([
  "/login",
  "/forgot-password",
  "/password/setup",
  "/help/onboarding",
]);

if (typeof window !== "undefined") {
  const { pathname, search, hash, origin } = window.location;

  if (PUBLIC_DIRECT_AUTH_HASH_PATHS.has(pathname) && !hash.startsWith("#/")) {
    window.location.replace(`${origin}/#${pathname}${search}`);
  }
}
// PUBLIC_DIRECT_AUTH_HASH_REDIRECT_END


createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </StrictMode>,
);
