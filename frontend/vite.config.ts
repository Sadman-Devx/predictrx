import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: /api is proxied to Django so the browser never hits CORS. Override with VITE_API_URL if needed.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
