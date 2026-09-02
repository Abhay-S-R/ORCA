import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { NavRail, SosButton } from "./nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "ORCA",
  description: "Marine decision support for the Tamil Nadu coast",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        {/* Skip link — §4.11 accessibility baseline, keyboard nav requirement */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-2"
        >
          Skip to content
        </a>
        <div className="flex flex-1">
          <NavRail />
          <main id="main-content" className="flex-1 p-6">
            {children}
          </main>
        </div>
        <SosButton />
      </body>
    </html>
  );
}
