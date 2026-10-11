import "@fontsource-variable/noto-sans-tc";
import "@fontsource/barlow-condensed/600.css";
import "@fontsource/barlow-condensed/800.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { I18nProvider } from "./i18n";
import "./styles/app.css";

const client = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <I18nProvider>
        <App />
      </I18nProvider>
    </QueryClientProvider>
  </StrictMode>,
);
