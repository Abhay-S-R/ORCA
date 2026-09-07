import type { Metadata, Viewport } from "next";
import { Barlow, Fraunces, IBM_Plex_Mono, Noto_Sans_Tamil } from "next/font/google";
import { AppChrome } from "./components/AppChrome";
import { PersonaProvider } from "./persona/context";
import "./globals.css";

// Barlow: a slightly condensed grotesque from transit-signage lineage —
// built to be read fast, at a glance, at an angle, which is the actual
// reading condition on a boat. Its narrow set width also keeps bilingual
// English/Tamil labels on one line in a 60px rail.
const barlow = Barlow({
  variable: "--font-barlow",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

// Fraunces: the wordmark and section heads only (globals.css scopes it to
// h1/h2/.font-display) — a chart-room serif with real character, standing
// in for the hand-lettered titles on a paper chart without going full
// blackletter about it.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["600", "700", "900"],
  style: ["normal"],
});

// Mono is for numeric readouts ONLY — depths, bearings, coordinates, wave
// heights. Tabular figures so a streaming value does not reflow its column.
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

// Tamil is a product requirement, not a nicety: the primary persona reads it.
const notoTamil = Noto_Sans_Tamil({
  variable: "--font-noto-tamil",
  subsets: ["tamil"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "ORCA — Marine decision support",
  description: "Go / no-go verdicts, fishing zones and hazard charts for the Tamil Nadu coast.",
};

export const viewport: Viewport = {
  themeColor: "#f2ead4",
  // The chart is edge-to-edge; let it run under the notch.
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${barlow.variable} ${fraunces.variable} ${plexMono.variable} ${notoTamil.variable} h-full antialiased`}
    >
      <body className="h-full overflow-hidden">
        {/* §4.11 — keyboard users reach content without tabbing the rail. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-100 focus:rounded-sm focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-on-accent"
        >
          Skip to content
        </a>
        <PersonaProvider>
          <AppChrome>{children}</AppChrome>
        </PersonaProvider>
      </body>
    </html>
  );
}
