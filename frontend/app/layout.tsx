import type { Metadata } from "next";
import "./globals.css";
import "frappe-gantt/dist/frappe-gantt.css";
import { ThemeProvider } from "@/components/ThemeProvider";

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
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        {/* Prevent theme flash: read localStorage before first paint */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var ls=window.localStorage;if(ls&&typeof ls.getItem==='function'){var t=ls.getItem('nanobot_agui_theme')||'dark';document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="antialiased font-sans" style={{ transition: "background-color 0.25s ease, color 0.25s ease" }}>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
