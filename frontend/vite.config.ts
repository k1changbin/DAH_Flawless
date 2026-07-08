import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  server: {
    // combat_replay.json은 리포 루트의 data/frontend/에 있음
    fs: { allow: [".."] },
  },
  build: {
    target: "esnext",
    chunkSizeWarningLimit: 8000,
  },
});
