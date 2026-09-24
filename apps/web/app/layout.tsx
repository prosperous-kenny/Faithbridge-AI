import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FaithBridge AI",
  description: "Transforming faith-based giving into measurable community impact",
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