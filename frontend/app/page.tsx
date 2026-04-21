import type { Metadata } from "next";
import LandingClient from "./LandingClient";
import { landingNoto, landingPlex } from "./landing-fonts";

export const metadata: Metadata = {
  title: "Nanobot AGUI",
  description: "Nanobot web UI — 作业管理 · 智慧工勘 · 建模仿真",
};

export default function LandingPage() {
  return (
    <div className={`${landingPlex.variable} ${landingNoto.variable}`}>
      <LandingClient />
    </div>
  );
}
