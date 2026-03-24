import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nanobot AGUI",
  description: "Nanobot web UI (local API, no CDN)",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased font-sans">{children}</body>
    </html>
  );
}
