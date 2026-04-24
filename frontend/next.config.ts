import type { NextConfig } from "next";

const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8765").replace(/\/$/, "");

/** 仅由 ``scripts/export-desktop.mjs`` 设置，用于生成纯静态 HTML（与 ``app/api`` 路由互斥）。 */
const staticExport = process.env.NANOBOT_STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  /** 让 Turbopack/打包器显式处理 jszip，避免仅拉代码未装依赖或解析异常时出现 Module not found */
  transpilePackages: ["jszip"],
  ...(staticExport
    ? {
        output: "export" as const,
        images: { unoptimized: true },
      }
    : {}),
  webpack: (config, { isServer, dev }) => {
    /** 单文件 HTML 打包：合并为少量 chunk，便于内联为单个 .html */
    if (staticExport && !isServer && !dev) {
      config.optimization = {
        ...config.optimization,
        splitChunks: false,
        runtimeChunk: false,
      };
    }
    return config;
  },
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
