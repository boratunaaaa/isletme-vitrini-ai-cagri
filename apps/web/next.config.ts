import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: {
    ignoreDuringBuilds: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  // PRODUCTION_INFRA_REPORT.md: Docker imajını küçültmek için standalone
  // çıktı — yalnız gerçekten kullanılan node_modules dosyalarını
  // `.next/standalone`'a izler, `node server.js` ile bağımsız çalışır
  // (tüm node_modules'ü kopyalamaya gerek kalmaz). pnpm workspace'inde
  // apps/web repo kökünün 2 seviye altında olduğu için trace kökü açıkça
  // monorepo köküne ayarlanmalı — aksi halde hoisted pnpm paketleri
  // standalone çıktıya dahil edilmeyebilir.
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../.."),
};

export default nextConfig;
