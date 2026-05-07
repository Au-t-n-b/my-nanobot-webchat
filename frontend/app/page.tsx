import type { Metadata } from "next";
import LandingClient from "./LandingClient";

export const metadata: Metadata = {
  title: "交付claw AGUI",
  description: "交付claw 工作台 — 作业管理 · 智慧工勘 · 建模仿真",
};

export default function LandingPage() {
  return <LandingClient />;
}
