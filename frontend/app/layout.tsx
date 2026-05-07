import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";
/* package exports 未声明 ./dist/*.css，裸包子路径在 Turbopack 下会解析失败 */
import "../node_modules/frappe-gantt/dist/frappe-gantt.css";
import { ThemeProvider } from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "交付claw AGUI",
  description: "交付claw 工作台（local API, no CDN）",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <Script id="theme-init" strategy="beforeInteractive">
          {`(function(){try{var ls=window.localStorage;if(ls&&typeof ls.getItem==='function'){var t=ls.getItem('nanobot_agui_theme')||'dark';document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`}
        </Script>
      </head>
      <body className="antialiased font-sans" style={{ transition: "background-color 0.25s ease, color 0.25s ease" }}>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
