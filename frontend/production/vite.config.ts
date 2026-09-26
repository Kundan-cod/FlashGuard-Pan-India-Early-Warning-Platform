import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Track B frontend build config (pending local run).
export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173 },
});
