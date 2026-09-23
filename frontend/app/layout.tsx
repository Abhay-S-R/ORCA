import type { Metadata, Viewport } from "next";
import {
  Barlow,
  Fraunces,
  IBM_Plex_Mono,
  Noto_Sans_Bengali,
  Noto_Sans_Devanagari,
  Noto_Sans_Gujarati,
  Noto_Sans_Kannada,
  Noto_Sans_Malayalam,
  Noto_Sans_Oriya,
  Noto_Sans_Tamil,
  Noto_Sans_Telugu,
} from "next/font/google";
import { AppChrome } from "./components/AppChrome";
import { LanguageProvider } from "./language/context";
import { PersonaProvider } from "./persona/context";
import { CriticalAlertProvider } from "./lib/criticalAlert";
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
//
// No `weight` here, and none on the Noto families below, because all of them
// are variable fonts — `weight` as an array is documented for *non*-variable
// families only (next/dist/docs/.../components/font.md), and omitting it loads
// the whole 100–900 axis instead of a few pinned instances. Pinning weights on
// Fraunces is what produced `next/font/google queries have exactly one entry`
// and a 500 on every dev page load: it carries four axes (SOFT, WONK, opsz,
// wght), so a discrete weight makes Google emit several `src` entries and
// Turbopack accepts only one. The Noto families have two axes and happen to
// survive it today, which is exactly why they are not left as a trap.
// Barlow and IBM Plex Mono keep their arrays — those two really are static.
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
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
});

// P3.12 (orca_final §14.4) — every other core script gets the same
// treatment as Tamil above: a matching Noto family loaded up front, so an
// Indic screen never depends on whatever font happens to already be on the
// handset. Devanagari covers both Hindi and Marathi (module docstring of
// orca/agents/language.py notes the same script is shared by both).
const notoDevanagari = Noto_Sans_Devanagari({
  variable: "--font-noto-devanagari",
  subsets: ["devanagari"],
});
const notoTelugu = Noto_Sans_Telugu({
  variable: "--font-noto-telugu",
  subsets: ["telugu"],
});
const notoMalayalam = Noto_Sans_Malayalam({
  variable: "--font-noto-malayalam",
  subsets: ["malayalam"],
});
const notoKannada = Noto_Sans_Kannada({
  variable: "--font-noto-kannada",
  subsets: ["kannada"],
});
const notoBengali = Noto_Sans_Bengali({
  variable: "--font-noto-bengali",
  subsets: ["bengali"],
});
const notoGujarati = Noto_Sans_Gujarati({
  variable: "--font-noto-gujarati",
  subsets: ["gujarati"],
});
const notoOriya = Noto_Sans_Oriya({
  variable: "--font-noto-oriya",
  subsets: ["oriya"],
});

export const metadata: Metadata = {
  title: "ORCA — Marine decision support",
  description: "Marine safety intelligence, fishing zones and hazard charts for the Indian coastline.",
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
      className={`${barlow.variable} ${fraunces.variable} ${plexMono.variable} ${notoTamil.variable} ${notoDevanagari.variable} ${notoTelugu.variable} ${notoMalayalam.variable} ${notoKannada.variable} ${notoBengali.variable} ${notoGujarati.variable} ${notoOriya.variable} h-full antialiased`}
    >
      <body className="h-full overflow-hidden">
        {/* §4.11 — keyboard users reach content without tabbing the rail. */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-100 focus:rounded-sm focus:bg-accent focus:px-3 focus:py-2 focus:text-sm focus:font-semibold focus:text-on-accent"
        >
          Skip to content
        </a>
        <LanguageProvider>
          <PersonaProvider>
            <CriticalAlertProvider>
              <AppChrome>{children}</AppChrome>
            </CriticalAlertProvider>
          </PersonaProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
