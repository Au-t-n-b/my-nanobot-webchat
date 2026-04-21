import { IBM_Plex_Sans, Noto_Sans_SC } from "next/font/google";

/** 仅保留落地页实际用到的字重，减少首屏字体下载与解析时间。 */
export const landingPlex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--landing-font-sans",
  display: "swap",
  preload: true,
});

export const landingNoto = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--landing-font-cjk",
  display: "swap",
  preload: true,
});
