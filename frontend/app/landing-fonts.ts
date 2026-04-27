import { IBM_Plex_Sans, Noto_Sans_SC } from "next/font/google";

export const landingPlex = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-landing-plex",
});

export const landingNoto = Noto_Sans_SC({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
  variable: "--font-landing-noto",
});

