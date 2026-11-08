import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ApplyPilot AI",
  description: "AI-powered personal job application assistant: one profile, one job URL, you approve the important decisions.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#2953e0" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
