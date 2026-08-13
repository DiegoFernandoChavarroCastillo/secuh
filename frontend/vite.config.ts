import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// El proxy hace que el panel y la API compartan origen en desarrollo:
// la cookie de sesión viaja sin necesidad de CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
