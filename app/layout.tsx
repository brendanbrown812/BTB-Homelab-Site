import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BTB League",
  description: "The home of the BTB fantasy football league.",
  other: {
    "codex-preview": "development",
  },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
