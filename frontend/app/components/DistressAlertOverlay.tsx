"use client";

import React, { useEffect, useRef, useState } from "react";
import { Phone, Volume2, VolumeX, X, ShieldAlert, LifeBuoy } from "lucide-react";

export interface DistressOverlayData {
  isOpen: boolean;
  queryId?: string;
  distressType?: string | null;
  matchedPhrase?: string | null;
  mrccContact?: {
    primary?: { name?: string; phone?: string | null; vhf_channel?: string };
    nationwide_fallback?: { name?: string; phone?: string | null };
    nearest_station?: { station?: string; coordinating_mrcc?: string; straight_line_distance_km?: number } | null;
  } | null;
  targetAuthority?: {
    port_name?: string;
    display_name?: string;
    authority_name?: string;
    email?: string;
    phone?: string;
    emergency_unit?: string;
  } | null;
  survivalAdvice?: {
    category_key?: string;
    category?: string;
    steps?: string[];
  } | null;
  survivalSuggestions?: string[] | null;
  position?: { lat?: number | null; lon?: number | null; place_name?: string | null } | null;
  rawText?: string;
}

interface DistressAlertOverlayProps {
  data: DistressOverlayData | null;
  onClose: () => void;
}

/**
 * Web Audio API synthesizer for an authentic maritime emergency alarm siren.
 * Operates purely client-side without external asset dependencies or network delay.
 */
class EmergencySirenSynthesizer {
  private ctx: AudioContext | null = null;
  private osc: OscillatorNode | null = null;
  private gain: GainNode | null = null;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private isMuted: boolean = false;

  start() {
    if (this.ctx) return;
    try {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtx) return;
      this.ctx = new AudioCtx();
      this.gain = this.ctx.createGain();
      this.gain.gain.setValueAtTime(this.isMuted ? 0 : 0.18, this.ctx.currentTime);
      this.gain.connect(this.ctx.destination);

      this.osc = this.ctx.createOscillator();
      this.osc.type = "sawtooth";
      this.osc.frequency.setValueAtTime(750, this.ctx.currentTime);
      this.osc.connect(this.gain);
      this.osc.start();

      let toggle = false;
      this.intervalId = setInterval(() => {
        if (!this.ctx || !this.osc) return;
        const targetFreq = toggle ? 650 : 980;
        this.osc.frequency.exponentialRampToValueAtTime(targetFreq, this.ctx.currentTime + 0.35);
        toggle = !toggle;
      }, 420);
    } catch (err) {
      console.warn("AudioContext initialization warning:", err);
    }
  }

  setMuted(muted: boolean) {
    this.isMuted = muted;
    if (this.gain && this.ctx) {
      this.gain.gain.setValueAtTime(muted ? 0 : 0.18, this.ctx.currentTime);
    }
  }

  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    try {
      if (this.osc) {
        this.osc.stop();
        this.osc.disconnect();
        this.osc = null;
      }
      if (this.gain) {
        this.gain.disconnect();
        this.gain = null;
      }
      if (this.ctx) {
        void this.ctx.close();
        this.ctx = null;
      }
    } catch {}
  }
}

export function DistressAlertOverlay({ data, onClose }: DistressAlertOverlayProps) {
  const [isMuted, setIsMuted] = useState(false);
  const sirenRef = useRef<EmergencySirenSynthesizer | null>(null);

  useEffect(() => {
    if (data?.isOpen) {
      const siren = new EmergencySirenSynthesizer();
      sirenRef.current = siren;
      siren.start();

      // Keyboard escape listener to dismiss
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          onClose();
        }
      };
      window.addEventListener("keydown", handleKeyDown);

      return () => {
        window.removeEventListener("keydown", handleKeyDown);
        siren.stop();
        sirenRef.current = null;
      };
    } else {
      if (sirenRef.current) {
        sirenRef.current.stop();
        sirenRef.current = null;
      }
    }
  }, [data?.isOpen, onClose]);

  const toggleSound = () => {
    const next = !isMuted;
    setIsMuted(next);
    sirenRef.current?.setMuted(next);
  };

  if (!data || !data.isOpen) return null;

  // Extract authorities and steps
  const mrcc = data.mrccContact;
  const mrccPhone = mrcc?.primary?.phone ?? "1554";
  const auth = data.targetAuthority;
  const authName = auth?.display_name ?? auth?.authority_name ?? (auth?.port_name ? `${auth.port_name} Coastal Authority` : "Coastal Authority");
  const authPhone = auth?.phone ?? "1093";
  const authUnit = auth?.emergency_unit ?? "Port Control & Marine Police";

  // Resolve survival steps
  let steps: string[] = data.survivalSuggestions ?? data.survivalAdvice?.steps ?? [];
  const categoryTitle = data.survivalAdvice?.category ?? "Emergency Maritime Survival Actions";

  // Fallback parsing from raw text if steps were packed into text
  if (steps.length === 0 && data.rawText) {
    const lines = data.rawText.split("\n");
    const extracted: string[] = [];
    for (const l of lines) {
      const match = l.match(/^\s*\d+\.\s*(.+)/);
      if (match) {
        extracted.push(match[1].trim());
      }
    }
    if (extracted.length > 0) {
      steps = extracted;
    }
  }

  // Fallback default marine safety steps if none found
  if (steps.length === 0) {
    steps = [
      "DON LIFE JACKETS IMMEDIATELY: Ensure every person aboard fastens a certified life vest (PFD) with whistle attached.",
      "BROADCAST MAYDAY ON VHF CH 16: Transmit 'MAYDAY MAYDAY MAYDAY', state vessel name, exact GPS coordinates, souls aboard, and nature of emergency.",
      "ACTIVATE BILGE PUMPS & CONTAIN LEAK: Power all electric and manual bilge pumps; attempt emergency plugging of hull breach if safe.",
      "PREPARE EMERGENCY GRAB BAG & LIFE RAFT: Keep flares, fresh water, handheld radio and EPIRB ready. Deploy life raft if sinking is imminent.",
      "STAY WITH VESSEL HULL: Do not enter open water unless vessel sinks completely. The boat hull is far more visible to rescue craft.",
      "PREVENT HYPOTHERMIA: If in water, huddle in Heat Escape Lessening Posture (H.E.L.P.) to preserve body core temperature.",
    ];
  }

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="distress-overlay-title"
      className="fixed inset-0 z-[250] flex flex-col justify-between overflow-y-auto bg-gradient-to-b from-[#3a0606] via-[#520909] to-[#250303] text-white p-4 sm:p-8 animate-in fade-in duration-200 border-[6px] border-red-600 shadow-[inset_0_0_120px_rgba(255,0,0,0.55)]"
    >
      {/* Top action bar: siren status, alert title, mute & close buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-red-500/40 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-red-600 text-white shadow-lg shadow-red-600/50 animate-pulse">
            <ShieldAlert className="size-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-block size-2.5 rounded-full bg-red-400 animate-ping" />
              <span className="font-mono text-xs font-bold uppercase tracking-widest text-red-200">
                MARITIME DISTRESS SIGNAL REGISTERED
              </span>
            </div>
            <h1 id="distress-overlay-title" className="text-xl sm:text-2xl font-black tracking-tight text-white drop-shadow">
              COAST GUARD MRCC &amp; COASTAL AUTHORITIES DISPATCHED
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggleSound}
            className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 text-xs font-semibold tracking-wide transition-all ${
              isMuted
                ? "border-red-400/50 bg-red-950/80 text-red-200 hover:bg-red-900"
                : "border-yellow-400/80 bg-yellow-500/20 text-yellow-200 shadow-md shadow-yellow-500/20 animate-pulse hover:bg-yellow-500/30"
            }`}
            title={isMuted ? "Unmute Alarm" : "Silence Siren Alarm"}
          >
            {isMuted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
            <span>{isMuted ? "SIREN MUTED" : "SIREN ACTIVE"}</span>
          </button>

          <button
            type="button"
            onClick={onClose}
            className="flex items-center gap-1.5 rounded-xl border border-white/30 bg-white/10 px-4 py-2 text-xs font-bold text-white backdrop-blur hover:bg-white/20 active:scale-95 transition-all"
            aria-label="Close emergency screen"
          >
            <X className="size-4" />
            <span>CLOSE</span>
          </button>
        </div>
      </div>

      {/* Dispatched Authorities Cards */}
      <div className="my-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Coast Guard MRCC Card */}
        <div className="rounded-2xl border-2 border-red-500/60 bg-black/40 p-4 sm:p-5 shadow-xl backdrop-blur">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-red-300">
                Primary Search &amp; Rescue Coordinator
              </span>
              <h2 className="text-lg font-bold text-white">
                {mrcc?.primary?.name ?? "Indian Coast Guard MRCC"}
              </h2>
            </div>
            <span className="rounded-lg bg-red-500/30 px-2.5 py-1 text-[11px] font-bold text-red-200 border border-red-400/40">
              VHF CH 16
            </span>
          </div>

          <p className="mt-2 text-xs text-red-100/90 leading-relaxed">
            Coast Guard Search and Rescue Centre has been alerted. Maintain listening watch on international distress frequency.
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            <a
              href={`tel:${mrccPhone}`}
              className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-xs font-bold text-white shadow-lg hover:bg-red-500 transition-colors"
            >
              <Phone className="size-3.5" />
              <span>DIAL MRCC: {mrccPhone}</span>
            </a>
            <a
              href="tel:1554"
              className="inline-flex items-center gap-1.5 rounded-xl border border-red-400/50 bg-black/40 px-3 py-2 text-xs font-semibold text-red-200 hover:bg-white/10"
            >
              <span>1554 (Toll-Free)</span>
            </a>
          </div>
        </div>

        {/* Local Coastal Authority Card */}
        <div className="rounded-2xl border-2 border-red-500/60 bg-black/40 p-4 sm:p-5 shadow-xl backdrop-blur">
          <div className="flex items-start justify-between gap-2">
            <div>
              <span className="text-[11px] font-mono font-bold uppercase tracking-wider text-red-300">
                User Home Port / Coastal Authority
              </span>
              <h2 className="text-lg font-bold text-white">{authName}</h2>
            </div>
            <span className="rounded-lg bg-red-500/30 px-2.5 py-1 text-[11px] font-bold text-red-200 border border-red-400/40">
              ALERT SENT
            </span>
          </div>

          <p className="mt-2 text-xs text-red-100/90 leading-relaxed">
            Emergency alert logged in Coastal Authority console ({authUnit}). Coastal patrol craft and harbor masters mobilized.
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            <a
              href={`tel:${authPhone}`}
              className="inline-flex items-center gap-2 rounded-xl bg-red-700/80 px-4 py-2 text-xs font-bold text-white border border-red-400/50 hover:bg-red-600 transition-colors"
            >
              <Phone className="size-3.5" />
              <span>CALL AUTHORITY: {authPhone}</span>
            </a>
            {data.position?.place_name && (
              <span className="inline-flex items-center gap-1.5 rounded-xl border border-white/20 bg-white/5 px-3 py-2 text-xs font-medium text-white/90">
                Sector: {data.position.place_name}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Centerpiece: CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU */}
      <div className="my-2 rounded-2xl border-2 border-red-400/80 bg-black/50 p-5 sm:p-7 shadow-2xl backdrop-blur-md">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-red-500/40 pb-3 mb-5">
          <div className="flex items-center gap-2.5">
            <LifeBuoy className="size-6 text-red-400 animate-spin" style={{ animationDuration: "8s" }} />
            <div>
              <h2 className="text-lg sm:text-xl font-black uppercase tracking-wide text-white drop-shadow">
                CRITICAL SURVIVAL ACTIONS WHILE AUTHORITIES REACH YOU
              </h2>
              <p className="text-xs font-medium text-red-200">
                Category: <strong className="text-white">{categoryTitle}</strong> — Execute immediately aboard your vessel:
              </p>
            </div>
          </div>
          <span className="font-mono text-xs font-bold px-3 py-1 rounded-full bg-red-600/60 border border-red-400 text-white">
            {steps.length} LIFE-SAVING STEPS
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 sm:gap-4">
          {steps.map((step, idx) => {
            // Split directive from explanation if colon exists
            const colonIdx = step.indexOf(":");
            const title = colonIdx !== -1 ? step.slice(0, colonIdx).trim() : `ACTION STEP ${idx + 1}`;
            const details = colonIdx !== -1 ? step.slice(colonIdx + 1).trim() : step.trim();

            return (
              <div
                key={idx}
                className="flex items-start gap-3.5 rounded-xl border border-red-500/40 bg-gradient-to-br from-red-950/70 to-black/60 p-4 text-left shadow-lg hover:border-red-400 transition-colors"
              >
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-red-600 text-sm font-black text-white shadow-md">
                  {idx + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-bold text-xs sm:text-sm tracking-tight text-white uppercase">
                    {title}
                  </h3>
                  <p className="mt-1 text-xs text-red-100/95 leading-relaxed font-normal">
                    {details}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bottom Dismiss / Acknowledge row */}
      <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-red-500/40 pt-4">
        <p className="text-xs text-red-200/80">
          ⚠️ Keep your VHF set to Channel 16. Do not abandon vessel unless deck submerges. Authorities are tracking your sector.
        </p>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleSound}
            className="rounded-xl border border-red-400/40 bg-black/40 px-4 py-2.5 text-xs font-semibold text-red-200 hover:bg-red-900 transition-colors"
          >
            {isMuted ? "Unmute Alarm" : "Mute Alarm"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-white text-red-950 px-6 py-2.5 text-sm font-black tracking-wide shadow-xl hover:bg-red-100 active:scale-95 transition-all"
          >
            ACKNOWLEDGE &amp; CLOSE SCREEN
          </button>
        </div>
      </div>
    </div>
  );
}
