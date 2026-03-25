import type { NextConfig } from "next";

const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
