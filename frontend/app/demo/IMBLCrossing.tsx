"use client";

// IMBL Border Bypass — Cinematic Demo (frontend-only, no live alerts)
// Route: Kanyakumari coast → Sri Lanka IMBL in Gulf of Mannar
// Ship SVG icon (shipPin prop) tracks across satellite map.
// Full-screen CRITICAL overlay on boundary breach.
import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Globe2, Play, RotateCcw, Volume2 } from "lucide-react";
import { MapView, type MapPin, type RouteGeoJson, type ShipPin } from "../components/MapView";
import { CHART } from "../map/basemap";
import { LANGUAGES, type LangCode } from "../i18n/languages";
import { useLanguage } from "../language/context";

// ─── Route: Kanyakumari coast NE toward Sri Lanka IMBL (Gulf of Mannar) ──────
// IMBL between India and Sri Lanka lies ~80.5°E in the Gulf of Mannar.
// Start: 8.3°N, 78.7°E (Kanyakumari fishing waters), heading NE at ~052°.
type Band = "CLEAR" | "ADVISORY" | "WATCH" | "WARNING" | "CRITICAL";
type GoNoGo = "GO" | "CAUTION" | "NO_GO";
type Frame = {
  lat: number; lon: number; distance_nm: number;
  band: Band; go_no_go: GoNoGo; reason: string;
  bearing: number; // ship heading in degrees (0=N)
};

const FRAMES: Frame[] = [
  { lat: 8.07, lon: 77.55, distance_nm: 28.5, band: "CLEAR", go_no_go: "GO", reason: "Departing Kanyakumari Port — open sea ahead", bearing: 60 },
  { lat: 8.15, lon: 77.70, distance_nm: 25.8, band: "CLEAR", go_no_go: "GO", reason: "Gulf of Mannar — clear waters, heading NE", bearing: 60 },
  { lat: 8.23, lon: 77.86, distance_nm: 23.1, band: "CLEAR", go_no_go: "GO", reason: "Open sea, no hazards", bearing: 60 },
  { lat: 8.31, lon: 78.01, distance_nm: 20.4, band: "CLEAR", go_no_go: "GO", reason: "Gulf of Mannar — Sri Lanka IMBL well ahead", bearing: 60 },
  { lat: 8.45, lon: 78.22, distance_nm: 17.6, band: "ADVISORY", go_no_go: "GO", reason: "Entering advisory zone — 17 nm from IMBL", bearing: 60 },
  { lat: 8.57, lon: 78.40, distance_nm: 14.9, band: "ADVISORY", go_no_go: "GO", reason: "IMBL advisory active — maintain caution", bearing: 60 },
  { lat: 8.68, lon: 78.57, distance_nm: 12.2, band: "ADVISORY", go_no_go: "GO", reason: "Sri Lanka boundary visible on chart — maintain caution", bearing: 60 },
  { lat: 8.77, lon: 78.71, distance_nm: 9.5, band: "WATCH", go_no_go: "GO", reason: "WATCH: 9.5 nm — voice advisory issued", bearing: 60 },
  { lat: 8.85, lon: 78.84, distance_nm: 7.2, band: "WATCH", go_no_go: "GO", reason: "WATCH: Closing rapidly — reduce speed now", bearing: 60 },
  { lat: 8.92, lon: 78.96, distance_nm: 5.4, band: "WATCH", go_no_go: "GO", reason: "WATCH: 5.4 nm — consider diverting course", bearing: 60 },
  { lat: 8.98, lon: 79.07, distance_nm: 3.8, band: "WARNING", go_no_go: "CAUTION", reason: "WARNING: 3.8 nm — CAUTION verdict, alter course NOW", bearing: 60 },
  { lat: 9.04, lon: 79.17, distance_nm: 2.7, band: "WARNING", go_no_go: "CAUTION", reason: "WARNING: 2.7 nm — turn to reciprocal heading 240°", bearing: 60 },
  { lat: 9.09, lon: 79.25, distance_nm: 1.9, band: "WARNING", go_no_go: "CAUTION", reason: "WARNING: 1.9 nm — last safe diversion window", bearing: 60 },
  { lat: 9.13, lon: 79.32, distance_nm: 1.2, band: "WARNING", go_no_go: "CAUTION", reason: "WARNING: 1.2 nm — reciprocal heading 240°", bearing: 60 },
  { lat: 9.17, lon: 79.39, distance_nm: 0.7, band: "CRITICAL", go_no_go: "NO_GO", reason: "CRITICAL: 0.7 nm — BOUNDARY IMMINENT. Turn 240°", bearing: 60 },
  { lat: 9.20, lon: 79.44, distance_nm: 0.4, band: "CRITICAL", go_no_go: "NO_GO", reason: "CRITICAL: 0.4 nm — NO-GO. Reciprocal heading 240°", bearing: 60 },
  { lat: 9.22, lon: 79.48, distance_nm: 0.1, band: "CRITICAL", go_no_go: "NO_GO", reason: "CRITICAL: 0.1 nm — VESSEL AT BOUNDARY. Turn 240° NOW", bearing: 60 },
];

// ─── Voice alerts ─────────────────────────────────────────────────────────────
const VOICE_WATCH: Record<LangCode, string> = {
  ta: "எச்சரிக்கை. கடல் எல்லைக்கு அருகில் உள்ளீர்கள். உங்கள் திசையை மாற்றவும்.",
  hi: "चेतावनी। आप समुद्री सीमा के पास हैं। कृपया अपना रास्ता बदलें।",
  en: "Warning. You are approaching the Sri Lanka maritime boundary. Please alter your course.",
  te: "హెచ్చరిక. మీరు సముద్ర సరిహద్దుకు దగ్గరగా ఉన్నారు. మీ మార్గాన్ని మార్చండి.",
  ml: "മുന്നറിയിപ്പ്. നിങ്ങൾ സമുദ്ര അതിർത്തിക്ക് അടുത്ത് ആണ്. ദിശ മാറ്റുക.",
  kn: "ಎಚ್ಚರಿಕೆ. ನೀವು ಸಮುದ್ರ ಗಡಿಯ ಬಳಿ ಇದ್ದೀರಿ. ನಿಮ್ಮ ಮಾರ್ಗವನ್ನು ಬದಲಾಯಿಸಿ.",
  bn: "সতর্কতা। আপনি সমুদ্রসীমার কাছাকাছি আছেন। আপনার পথ পরিবর্তন করুন।",
  mr: "सावधान. तुम्ही सागरी सीमेजवळ आहात. तुमचा मार्ग बदला.",
  gu: "ચેતવણી. તમે સમુદ્ર સીમાની નજીક છો. તમારો રસ્તો બદલો.",
  or: "ସତର୍କତା। ଆପଣ ସମୁଦ୍ର ସୀମା ନିକଟରେ ଅଛନ୍ତି। ଦିଗ ବଦଳାନ୍ତୁ।",
};
const VOICE_CRITICAL: Record<LangCode, string> = {
  ta: "அவசர எச்சரிக்கை! கடல் எல்லையை கடக்கிறீர்கள். உடனடியாக 232 டிகிரி திசையில் திரும்புங்கள்!",
  hi: "आपातकालीन चेतावनी! आप समुद्री सीमा पार कर रहे हैं। तुरंत 232 डिग्री की ओर मुड़ें!",
  en: "Emergency alert! You are crossing the Sri Lanka maritime boundary. Immediately turn to heading 232 degrees!",
  te: "అత్యవసర హెచ్చరిక! మీరు సముద్ర సరిహద్దు దాటుతున్నారు. వెంటనే 232 డిగ్రీలకు తిరగండి!",
  ml: "അടിയന്തര മുന്നറിയിപ്പ്! നിങ്ങൾ സമുദ്ര അതിർത്തി കടക്കുകയാണ്. ഉടൻ 232 ഡിഗ്രിയിലേക്ക് തിരിയുക!",
  kn: "ತುರ್ತು ಎಚ್ಚರಿಕೆ! ನೀವು ಸಮುದ್ರ ಗಡಿ ದಾಟುತ್ತಿದ್ದೀರಿ. ತಕ್ಷಣ 232 ಡಿಗ್ರಿಗೆ ತಿರುಗಿ!",
  bn: "জরুরি সতর্কতা! আপনি সমুদ্রসীমা অতিক্রম করছেন। এখনই 232 ডিগ্রিতে ঘুরুন!",
  mr: "आणीबाणी इशारा! तुम्ही सागरी सीमा ओलांडत आहात. तातडीने 232 अंशावर वळा!",
  gu: "કટોકટી ચેતવણી! તમે સમુદ્ર સીમા ઓળંગી રહ્યા છો. તરત 232 ડિગ્રી પર વળો!",
  or: "ଜରୁରୀ ସତର୍କତା! ଆପଣ ସମୁଦ୍ର ସୀମା ଅତିକ୍ରମ କରୁଛନ୍ତି। ତୁରନ୍ତ 232 ଡିଗ୍ରିକୁ ଯାଆନ୍ତୁ!",
};

// ─── Band UI colours ──────────────────────────────────────────────────────────
const BAND_CFG: Record<Band, { bg: string; border: string; text: string; dot: string }> = {
  CLEAR: { bg: "rgba(47,122,79,0.15)", border: "rgba(47,122,79,0.6)", text: "#2f7a4f", dot: "#2f7a4f" },
  ADVISORY: { bg: "rgba(184,134,46,0.15)", border: "rgba(184,134,46,0.6)", text: "#b8862e", dot: "#b8862e" },
  WATCH: { bg: "rgba(14,165,233,0.15)", border: "rgba(14,165,233,0.6)", text: "#0ea5e9", dot: "#0ea5e9" },
  WARNING: { bg: "rgba(220,80,30,0.15)", border: "rgba(220,80,30,0.6)", text: "#dc501e", dot: "#dc501e" },
  CRITICAL: { bg: "rgba(179,64,44,0.2)", border: "rgba(179,64,44,0.85)", text: "#b3402c", dot: "#b3402c" },
};

const STEP_MS = 1800;

function speak(text: string, lang: LangCode) {
  try {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const meta = LANGUAGES.find((l) => l.code === lang);
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(text);
    utt.lang = meta?.bcp47 ?? "en-IN";
    utt.rate = 0.9;
    const voices = window.speechSynthesis.getVoices();
    const match = voices.find((v) => v.lang === utt.lang) ?? voices.find((v) => v.lang.startsWith(lang));
    if (match) utt.voice = match;
    window.speechSynthesis.speak(utt);
  } catch { /* silent */ }
}

// ─── Component ────────────────────────────────────────────────────────────────
export function IMBLCrossing() {
  const { language } = useLanguage();
  const [selectedLang, setSelectedLang] = useState<LangCode>(language as LangCode);
  const [langOpen, setLangOpen] = useState(false);
  const langRef = useRef<HTMLDivElement>(null);

  const [index, setIndex] = useState(-1);
  const [running, setRunning] = useState(false);
  const spokenRef = useRef<Band | null>(null);
  // Track the current app language in a ref so reset() can sync selectedLang
  // without a setState-in-effect (which the linter forbids).
  const languageRef = useRef(language);
  useEffect(() => { languageRef.current = language as LangCode; }, [language]);
  const flashTimerRef = useRef<NodeJS.Timeout | null>(null);
  const flashCountRef = useRef(0);
  const [criticalFlash, setCriticalFlash] = useState(false);
  const [criticalOverlay, setCriticalOverlay] = useState(false);

  // Outside-click closes lang dropdown
  useEffect(() => {
    if (!langOpen) return;
    const fn = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setLangOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, [langOpen]);



  // Auto-advance frames
  useEffect(() => {
    if (!running || index < 0 || index >= FRAMES.length - 1) return;
    const id = setTimeout(() => setIndex((i) => i + 1), STEP_MS);
    return () => clearTimeout(id);
  }, [running, index]);

  // Escalation: voice + red flash + full-screen overlay
  useEffect(() => {
    if (index < 0) return;
    const f = FRAMES[index];
    if (f.band === "WATCH" && spokenRef.current !== "WATCH") {
      spokenRef.current = "WATCH";
      speak(VOICE_WATCH[selectedLang], selectedLang);
    }
    if (f.band === "CRITICAL" && spokenRef.current !== "CRITICAL") {
      spokenRef.current = "CRITICAL";
      speak(VOICE_CRITICAL[selectedLang], selectedLang);
      setCriticalOverlay(true);
      flashCountRef.current = 0;
      setCriticalFlash(true);
      flashTimerRef.current = setInterval(() => {
        flashCountRef.current += 1;
        setCriticalFlash((v) => !v);
        if (flashCountRef.current >= 9) {
          clearInterval(flashTimerRef.current!);
          setCriticalFlash(false);
        }
      }, 400);
    }
  }, [index, selectedLang]);

  useEffect(() => () => { if (flashTimerRef.current) clearInterval(flashTimerRef.current); }, []);

  // Derived state
  const seen = index >= 0 ? FRAMES.slice(0, index + 1) : [];
  const frame = index >= 0 ? FRAMES[index] : null;

  const verdictStatus = (g: GoNoGo): "CLEAR" | "CAUTION" | "BLOCKED" =>
    g === "GO" ? "CLEAR" : g === "CAUTION" ? "CAUTION" : "BLOCKED";
  const verdictColor = (g: GoNoGo) =>
    g === "GO" ? CHART.go : g === "CAUTION" ? CHART.caution : CHART.noGo;

  // Route GeoJSON from frames seen so far
  const routeGeoJson: RouteGeoJson = {
    type: "FeatureCollection",
    features: seen.slice(1).map((f, i) => ({
      type: "Feature",
      geometry: { type: "LineString", coordinates: [[seen[i].lon, seen[i].lat], [f.lon, f.lat]] },
      properties: {
        segment_id: `leg-${i}`, status: verdictStatus(f.go_no_go),
        hazard_class: f.band, detail: f.reason, eta: "", distance_nm: f.distance_nm,
      },
    })),
  };

  // Origin anchor pin (Kanyakumari Port)
  const pins: MapPin[] = frame
    ? [{ lat: 8.07, lon: 77.55, label: "Kanyakumari Port ⚓", color: CHART.eez }]
    : [];

  // Ship icon marker via the new shipPin prop
  const shipPin: ShipPin | null = frame
    ? { lat: frame.lat, lon: frame.lon, color: verdictColor(frame.go_no_go), bearing: frame.bearing }
    : null;

  const band: Band = frame?.band ?? "CLEAR";
  const cfg = BAND_CFG[band];
  const isCritical = band === "CRITICAL";
  const isFinished = index >= FRAMES.length - 1;
  const progress = index < 0 ? 0 : ((index + 1) / FRAMES.length) * 100;

  const start = useCallback(() => {
    spokenRef.current = null;
    setCriticalFlash(false);
    setCriticalOverlay(false);
    if (flashTimerRef.current) clearInterval(flashTimerRef.current);
    window.speechSynthesis?.cancel();
    setIndex(0);
    setRunning(true);
  }, []);

  const reset = useCallback(() => {
    setRunning(false);
    setIndex(-1);
    setSelectedLang(languageRef.current as LangCode);
    spokenRef.current = null;
    setCriticalFlash(false);
    setCriticalOverlay(false);
    if (flashTimerRef.current) clearInterval(flashTimerRef.current);
    window.speechSynthesis?.cancel();
  }, []);

  return (
    // Full height below the site nav bar
    <div className="relative flex h-full min-h-[calc(100vh-56px)] flex-col overflow-hidden bg-[#03111a]">

      {/* ── MAP: fills all available height ──────────────────────────────── */}
      <div className="relative flex-1 overflow-hidden">
        <MapView
          className="h-full w-full rounded-none border-0"
          routeGeoJson={index >= 0 ? routeGeoJson : null}
          pins={pins}
          shipPin={shipPin}
          initialCenter={[79.6, 8.55]}
          initialZoom={7.45}
          initialLayers={{
            boundaries: false,
            boundaryLines: true,
            pfz: false,
            seamarks: false,
            srvBathymetry: false,
            waveForecast: false,
            currents: false,
            wind: false,
            watchBadges: false,
            cyclone: false,
          }}
          showLayerPanel={false}
          showRegionSwitcher={false}
          showLegends={false}
          showSoundingHud={false}
          showCoastalBoundary={false}
          disableRouteAutoZoom
        />

        {/* ── Red border vignette flash on CRITICAL ── */}
        {isCritical && (
          <>
            <div
              className="pointer-events-none absolute inset-0 z-20 transition-opacity duration-200"
              style={{ background: "rgba(160,30,20,0.18)", opacity: criticalFlash ? 1 : 0.28 }}
            />
            <div
              className="pointer-events-none absolute inset-0 z-20"
              style={{
                border: `4px solid ${CHART.noGo}`,
                boxShadow: criticalFlash
                  ? `inset 0 0 70px 14px rgba(200,40,20,0.5), 0 0 40px 8px rgba(200,40,20,0.3)`
                  : `inset 0 0 30px 4px rgba(200,40,20,0.2)`,
                transition: "box-shadow 0.2s",
              }}
            />
          </>
        )}

        {/* ── Band / distance HUD — top-left ── */}
        {frame && !isCritical && (
          <div
            className="pointer-events-none absolute left-4 top-4 z-10 flex items-center gap-2 rounded-xl px-3 py-2 backdrop-blur-md shadow-lg"
            style={{ background: cfg.bg, border: `1.5px solid ${cfg.border}` }}
          >
            <span className="size-2.5 rounded-full animate-pulse shrink-0" style={{ background: cfg.dot }} />
            <span className="text-xs font-bold" style={{ color: cfg.text }}>{band}</span>
            <span className="text-xs text-white/70">{frame.distance_nm.toFixed(1)} nm from IMBL</span>
          </div>
        )}

        {/* ── Coordinates HUD — bottom-left ── */}
        {frame && (
          <div className="pointer-events-none absolute bottom-10 left-4 z-10 rounded-lg border border-white/20 bg-black/50 px-2.5 py-1.5 backdrop-blur-md">
            <span className="font-mono text-[11px] text-white/65">
              {frame.lat.toFixed(4)}°N · {frame.lon.toFixed(4)}°E
            </span>
          </div>
        )}

        {/* ── Language selector — top-right (above nav controls) ── */}
        <div ref={langRef} className="absolute right-14 top-4 z-30">
          <button
            type="button"
            onClick={() => setLangOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded-lg border border-white/20 bg-black/60 px-2.5 py-1.5 text-xs font-medium text-white shadow-lg backdrop-blur-md transition hover:bg-black/75"
          >
            <Volume2 className="size-3.5 text-ocean-cyan shrink-0" />
            <Globe2 className="size-3 text-white/55 shrink-0" />
            <span>{LANGUAGES.find((l) => l.code === selectedLang)?.native ?? "English"}</span>
            <ChevronDown className={`size-3 text-white/45 transition-transform ${langOpen ? "rotate-180" : ""}`} />
          </button>
          {langOpen && (
            <div className="absolute right-0 top-full mt-1.5 z-40 w-44 max-h-64 overflow-y-auto rounded-xl border border-white/15 bg-black/85 backdrop-blur-xl p-1 shadow-2xl">
              <p className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider text-white/35 border-b border-white/10 mb-1">
                Voice Alert Language
              </p>
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  onClick={() => { setSelectedLang(l.code); setLangOpen(false); }}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${selectedLang === l.code
                    ? "bg-ocean-cyan/20 text-ocean-cyan font-semibold"
                    : "text-white/75 hover:bg-white/10"
                    }`}
                >
                  <span>{l.native}</span>
                  <span className="text-[10px] text-white/35">{l.english}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── Full-screen CRITICAL overlay (matches reference image) ─────── */}
        {criticalOverlay && (
          <div
            className="absolute inset-0 z-50 flex flex-col items-center justify-center px-6 text-center"
            style={{
              background: criticalFlash ? "#c0392b" : "#a93226",
              transition: "background 0.25s ease",
            }}
          >
            {/* Octagon warning icon */}
            <div
              className="mb-7 flex size-[88px] items-center justify-center"
              style={{
                border: "3px solid rgba(255,255,255,0.75)",
                borderRadius: "50%",
              }}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="size-11 text-white"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
            </div>

            <h2 className="text-[26px] font-bold text-white mb-3 leading-tight tracking-tight">
              Imminent Boundary or MPA Breach
            </h2>
            <p className="text-white/85 text-[15px] mb-1.5">
              <span className="font-mono font-semibold">{frame?.distance_nm.toFixed(2)} nm</span>{" "}
              from the boundary. Turn back toward open water now.
            </p>
            <p className="text-white font-bold text-[15px] mb-9">
              Turn to 232° to head back to clear water.
            </p>

            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => { /* Demo: no real call */ }}
                className="rounded-full border-2 border-white/75 bg-transparent px-7 py-2.5 text-[14px] font-semibold text-white transition-all hover:bg-white/15 active:scale-95 focus:outline-none"
              >
                Call MRCC · 1554
              </button>
              <button
                type="button"
                onClick={() => setCriticalOverlay(false)}
                className="rounded-full border-2 border-white/75 bg-transparent px-7 py-2.5 text-[14px] font-semibold text-white transition-all hover:bg-white/15 active:scale-95 focus:outline-none"
              >
                Acknowledge
              </button>
            </div>

            <p className="mt-10 text-[11px] text-white/35 tracking-widest uppercase">
              Demo · No real maritime alerts issued
            </p>
          </div>
        )}

        {/* ── Idle overlay (before play) ── */}
        {index === -1 && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/50 backdrop-blur-[2px]">
            {/* Ship icon preview */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/assets/shipicon.png"
              alt="Vessel"
              className="mb-4 size-16 drop-shadow-lg"
              style={{ filter: "drop-shadow(0 3px 10px rgba(0,200,220,0.6))" }}
            />
            <p className="text-sm font-semibold text-white">
              IMBL Boundary Approach · Kanyakumari → Sri Lanka
            </p>
            <p className="mt-1.5 text-xs text-white/50">
              Press Play · Cinematic demo · No real alerts triggered
            </p>
          </div>
        )}
      </div>

      {/* ── BOTTOM CONTROL BAR ────────────────────────────────────────────── */}
      <div className="relative z-10 flex items-center gap-3 border-t border-white/10 bg-[#030d16]/95 px-5 py-3 backdrop-blur-md">

        {/* Play / Replay */}
        {!running || isFinished ? (
          <button
            type="button"
            onClick={start}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-ocean-cyan px-4 py-2 text-sm font-semibold text-white shadow-md transition hover:bg-ocean-cyan/85 active:scale-95"
          >
            <Play className="size-4" />
            {isFinished ? "Replay" : "Play Demo"}
          </button>
        ) : (
          <div className="flex shrink-0 items-center gap-1.5 rounded-xl border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/55">
            <span className="size-2 animate-pulse rounded-full bg-ocean-cyan" />
            Simulating…
          </div>
        )}

        {/* Reset */}
        <button
          type="button"
          onClick={reset}
          className="flex shrink-0 items-center gap-1.5 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-xs font-medium text-white/55 transition hover:bg-white/10"
        >
          <RotateCcw className="size-3.5" />
          Reset
        </button>

        {/* Progress bar + band info */}
        <div className="flex flex-1 flex-col gap-1 min-w-0">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${progress}%`,
                background: isCritical
                  ? CHART.noGo
                  : band === "WARNING"
                    ? "#dc501e"
                    : band === "WATCH"
                      ? "#0ea5e9"
                      : band === "ADVISORY"
                        ? CHART.caution
                        : CHART.go,
              }}
            />
          </div>
          {frame && (
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider text-white"
                style={{ background: cfg.dot }}
              >
                {band}
              </span>
              <span className="truncate text-[11px] text-white/50">{frame.reason}</span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-white/30">
                {index + 1} / {FRAMES.length}
              </span>
            </div>
          )}
        </div>

        {/* Demo badge */}
        <span className="shrink-0 rounded-full border border-white/15 bg-white/5 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-white/30">
          Demo · No live alerts
        </span>
      </div>
    </div>
  );
}
