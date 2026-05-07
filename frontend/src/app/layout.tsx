import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WoW AI Log Analyzer",
  description: "Analyze your Warcraft Logs reports with AI-driven, actionable feedback.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
