import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В разработке API живёт на 8000; в проде FastAPI раздаёт dist/ сам.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8010" },
  },
  build: { outDir: "dist", sourcemap: false },
});
