"use client";

import { useMemo, type ReactNode } from "react";
import {
  Compass,
  Cloud,
  Waves,
  Crosshair,
  ShieldCheck,
  FileText,
  Clock,
  MapPin,
  AlertTriangle,
} from "lucide-react";
import { fontClassForLanguage } from "../i18n/languages";
import { splitVerdictHeader } from "../lib/verdictHeader";
import { useT } from "../i18n/useT";
import { typography } from "../styles/typography";

interface FormattedResponseProps {
  text: string;
  className?: string;
  language?: string | null;
  large?: boolean;
}

/**
 * Renders a modern colored directional pointer in ocean-cyan accent.
 * Distinct from a black dot, and clean without busy weather icons.
 */
function PointPointer() {
  return (
    <span className="mt-1.5 flex size-3.5 shrink-0 items-center justify-center text-ocean-cyan" aria-hidden="true">
      <svg className="size-2.5 fill-current" viewBox="0 0 10 10">
        <path d="M2.5 1.5l5 3.5-5 3.5V1.5z" />
      </svg>
    </span>
  );
}

/**
 * Repairs smashed tokens, unclosed/inverted asterisks, and ensures that:
 * 1. Numbers and measurements with units (e.g. "53 to 58 km SW", "0.52 m", "10.1 km/h", "06:00 to 18:00 IST")
 * 2. Key operational statuses & terms (e.g. "Yes, sea conditions are safe and favorable", "All Clear", "calm and favorable conditions", "Within state waters (0–12 NM)", "No active ban")
 * 3. Specific zone names (e.g. "Belapur offshore zone", "Sector MAHARASHTRA")
 * are properly wrapped in markdown bold (**...**) so they render in clean brown highlight.
 * Fish species names (e.g. "Indian mackerel", "Bombay duck") are explicitly kept plain text.
 */
function formatAndHighlightContent(str: string): string {
  if (!str) return "";
  let text = str;

  // 1. Spacing repair
  text = text.replace(/,([^\s])/g, ", $1");
  text = text.replace(/([NESW]{1,3})\s*(of|off)\b/gi, "$1 $2");
  text = text.replace(/\b(km|NM|nm)\s*([NESW]{1,3})/gi, "$1 $2");
  text = text.replace(/(\d+(?:\.\d+)?)\s*(km\/h|kmh|km\/hr|kph|km|NM|nm|knots|kt|hPa|m\/s|hours?|hrs?|mins?|minutes?|days?)(?=[A-Za-z\s\d,;().\-]|$)/gi, "$1 $2");
  text = text.replace(/(\d+(?:\.\d+)?)\s*m(?=[A-Z\s,;().\-]|$)(?![a-zA-Z]{2,})/g, "$1 m");
  text = text.replace(/\b(km|NM|nm)\s*([NESW]{1,3})/gi, "$1 $2");
  text = text.replace(/([a-zA-Z])(\d+(?:\.\d+)?\s*(?:km\/h|km|NM|nm|knots|kt|hPa|m\/s|m|hours?|hrs?|days?))/gi, "$1 $2");
  text = text.replace(/(\d{1,2}:\d{2})\s*(?:to|-|–)\s*(\d{1,2}:\d{2})\s*(IST|UTC|AM|PM)?/gi, "$1 to $2 $3");
  text = text.replace(/(\d{1,2}:\d{2})(IST|UTC|AM|PM)\b/gi, "$1 $2");
  text = text.replace(/(\d+)\s*-\s*(\d+)\s*(km|m|NM|nm|hours?|hrs?)/gi, "$1–$2 $3");
  text = text.replace(/[ \t]{2,}/g, " ");

  // 2. Fix inverted / broken asterisks
  text = text.replace(/(\d{1,2}:\d{2})\s*\*\*to\*\*\s*(\d{1,2}:\d{2})\s*(?:\*\*([A-Za-z]+)\*\*)?/gi, "**$1 to $2 $3**");
  text = text.replace(/\*\*(\d+(?:\.\d+)?)\*\*\s*(km|NM|nm|m|km\/h|knots|hPa|hours?|hrs?)\s*\*\*([NESW]{1,3})\*\*/gi, "**$1 $2 $3**");
  text = text.replace(/\*\*(\d+(?:\.\d+)?)\*\*\s*(km|NM|nm|m|km\/h|knots|hPa|hours?|hrs?)\b/gi, "**$1 $2**");
  text = text.replace(/\*\*(\d+(?:\.\d+)?)\s*(?:to|–|-)\s*(\d+(?:\.\d+)?)\*\*\s*(km|NM|nm|m|km\/h|knots|hPa|hours?|hrs?)\b/gi, "**$1 to $2 $3**");
  text = text.replace(/\*\*(wave height|wind speed|water depth)\*\*\s*([0-9.]+)\s*\*\*([a-z/]+)\*\*/gi, "$1 **$2 $3**");
  text = text.replace(/\*\*([NESW]{1,3})\s*(?:of|off)\s+([A-Za-z]+),\s*(\d+[–-]\d+\s*km)\*\*/gi, "**$1** of $2, **$3**");

  // 3. Unbold fish names
  text = text.replace(
    /\*\*(Indian\s+mackerel|Bombay\s*duck|Silver\s*pomfret|Sardine[s]?|Tuna|Mackerel|Ribbonfish|Seer\s*fish|Anchov(?:y|ies)|Squid|Cuttlefish|Shrimp|Prawn[s]?|Carangid[s]?)\*\*/gi,
    "$1"
  );

  // 4. Helper to apply highlight pattern only to non-bold parts of text
  function highlightMatches(input: string, regex: RegExp, replacement: string) {
    const parts = input.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
    return parts
      .map((part) => {
        if (!part || (part.startsWith("**") && part.endsWith("**")) || (part.startsWith("`") && part.endsWith("`"))) {
          return part;
        }
        return part.replace(regex, replacement);
      })
      .join("");
  }

  // Time window e.g. 06:00 to 18:00 IST
  text = highlightMatches(text, /\b(\d{1,2}:\d{2}\s+to\s+\d{1,2}:\d{2}(?:\s*(?:IST|UTC|AM|PM))?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(\d{1,2}:\d{2}\s*(?:IST|UTC))\b/gi, "**$1**");
  text = highlightMatches(text, /\b(\d{1,3}°T)\b/g, "**$1**");

  // Legal / State jurisdiction bounds
  text = highlightMatches(text, /\b(Within state waters(?:\s*\(\s*0[–-]12\s*NM\s*\))?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(No active ban)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Active [A-Za-z]+ ban)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Zero tolerance border)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(strictly prohibited)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(ZERO TOLERANCE)\b/g, "**$1**");

  // Operational verdicts and affirmations
  text = highlightMatches(text, /\b(Yes,\s+sea conditions are safe and favorable(?: for [^.,;()]+)?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Passage approved and hydrographically clear(?: for [^.,;()]+)?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Normal maritime operations permitted)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Fisheries exploitation permitted)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Caution advised)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Unsafe\s*[—–-]\s*remain in harbor)\b/gi, "**$1**");

  // Alerts & tiers
  text = highlightMatches(text, /\b(All Clear(?:\s*\/\s*Green Tier)?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Green Tier|Yellow Tier|Orange Tier|Red Tier)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(No active (?:lightning|cyclone|severe storm)[^.,;()]*)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(No severe marine meteorological hazards in force)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(No severe weather warnings active)\b/gi, "**$1**");

  // Sea conditions & trends
  text = highlightMatches(text, /\b(calm and favorable(?: conditions)?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Calm, safe, and favorable(?: \([^)]+\))?)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Gentle and safe breeze)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Steady)\b/g, "**$1**");
  text = highlightMatches(text, /\b(Oligotrophic|Mesotrophic|Eutrophic)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(permitted with standard vigilance)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(fully cleared)\b/gi, "**$1**");

  // Window phrases
  text = highlightMatches(text, /\b(Optimal departure window)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Advisory validity timeframe)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Tidal departure & daylight passage window)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(Optimal oceanographic observation window)\b/gi, "**$1**");

  // Zone names in phrases like "Belapur offshore zone" or "of Belapur"
  text = highlightMatches(text, /\b([A-Z][a-zA-Z]+(?:\s+[a-zA-Z]+)*\s+offshore zone)\b/gi, "**$1**");
  text = highlightMatches(text, /\b(located\s+[0-9–\sA-Za-z]+?\s+of\s+)([A-Z][a-zA-Z]+)\b/gi, "$1**$2**");
  text = highlightMatches(text, /\bSector\s+([A-Z_]+)\b/g, "Sector **$1**");

  // Measurements with units (e.g. 53 to 58 km SW, 25 to 30 m, 0.52 m, 10.1 km/h, 14 knots, 1012 hPa)
  text = highlightMatches(text, /(^|[\s(])([<>]?\s*\d+(?:\.\d+)?(?:\s*(?:to|–|-)\s*\d+(?:\.\d+)?)?\s*(?:km\/h|kmh|km|NM|nm|knots|kt|hPa|m\/s|°C\/km|°C|mg\/m³|s|m)\b(?:\s+[NESW]{1,3}\b)?)/gi, "$1**$2**");

  // Durations (e.g. 2 to 3 hours, 1 day old)
  text = highlightMatches(text, /(^|[\s(])(\d+(?:\.\d+)?(?:\s*(?:to|–|-)\s*\d+(?:\.\d+)?)?\s*(?:hours?|hrs?|minutes?|mins?))\b/gi, "$1**$2**");
  text = highlightMatches(text, /\b(\d+\s+days?\s+old)\b/gi, "**$1**");

  // Date/advisory integer (e.g. 20261013)
  text = highlightMatches(text, /\b(20\d{6})\b/g, "**$1**");

  // Prices (e.g. ₹180–220/kg, ₹200/kg)
  text = highlightMatches(text, /(₹\s*\d+(?:[–-]\d+)?(?:\/kg)?)/g, "**$1**");

  // Ensure fish names stay unbolded
  text = text.replace(
    /\*\*(Indian\s+mackerel|Bombay\s*duck|Silver\s*pomfret|Sardine[s]?|Tuna|Mackerel|Ribbonfish|Seer\s*fish|Anchov(?:y|ies)|Squid|Cuttlefish|Shrimp|Prawn[s]?|Carangid[s]?)\*\*/gi,
    "$1"
  );

  return text;
}

/**
 * Sanitizes item text by:
 * 1. Removing scientific/Latin names in parentheses following fish/species names
 * 2. Unbolding fish species names so they are not highlighted
 * 3. Ensuring parameter labels before a colon are highlighted in bold
 * 4. Applying comprehensive spacing repair and brown highlighting
 */
function cleanItemContent(text: string): string {
  // Strip any leading bullet markers, dashes, or asterisks: e.g. "* Wave...", "* * Wave...", "• * Wave..."
  let cleaned = text.replace(/^[•*\-\s]+/, "").replace(/\*\s+\*/g, "**").trim();
  cleaned = cleaned.replace(/^\*+\s*/, "");

  // Strip "All Parameters Within Safe Operational Limits"
  cleaned = cleaned.replace(/\bAll Parameters Within Safe Operational Limits\b[.:]?/gi, "").trim();

  // Remove scientific binomials in parentheses, e.g. "(Rastrelliger kanagurta)" or "(Harpadon nehereus)"
  cleaned = cleaned.replace(/\s*\([A-Z][a-z]+(?:\s+[a-z]+)?\)/g, "");

  // Unbold fish names if they are bolded: **Indian mackerel** -> Indian mackerel
  cleaned = cleaned.replace(
    /\*\*(Indian\s+mackerel|Bombay\s*duck|Silver\s*pomfret|Sardine[s]?|Tuna|Mackerel|Ribbonfish|Seer\s*fish|Anchov(?:y|ies)|Squid|Cuttlefish|Shrimp|Prawn[s]?|Carangid[s]?)\*\*/gi,
    "$1"
  );

  // Clean any duplicated labels at the start, e.g. "**Safe Operating Window**: Safe Operating Window: "
  cleaned = cleaned.replace(/^(\*\*([\p{L}\p{M}\p{N}\s&/—–\-_()]+?)\*\*:\s*)(?:[•*\-]\s*)?(?:\*\*)?\2(?:\*\*)?:\s*/iu, "$1");

  // Ensure parameter label before colon is bolded and clean of leading asterisks
  if (!cleaned.startsWith("**") && cleaned.includes(":")) {
    cleaned = cleaned.replace(/^[*•\-\s]*([\p{L}\p{M}\p{N}\s&/—–\-_()]+?):\s*/u, "**$1**: ");
  }

  // If there's an odd count of '**', balance missing opening or remove dangling '**'
  const starMatches = cleaned.match(/\*\*/g);
  if (starMatches && starMatches.length % 2 !== 0) {
    if (/(?<!\*\*)\b(\d{2}:\d{2}(?:\s+to\s+\d{2}:\d{2})?\s*(?:IST|UTC|AM|PM)?)\*\*/i.test(cleaned)) {
      cleaned = cleaned.replace(/(?<!\*\*)\b(\d{2}:\d{2}(?:\s+to\s+\d{2}:\d{2})?\s*(?:IST|UTC|AM|PM)?)\*\*/gi, "**$1**");
    } else {
      const lastIdx = cleaned.lastIndexOf("**");
      if (lastIdx !== -1) {
        cleaned = cleaned.slice(0, lastIdx) + cleaned.slice(lastIdx + 2);
      }
    }
  }

  return cleaned.trim();
}

/**
 * Parses inline markdown tokens (**bold**, `code`, *italic*) safely into React nodes.
 * Bold text (**...**) is rendered with brown highlighting (`font-semibold text-accent`).
 */
function renderInlineMarkdown(str: string, defaultBoldColor: "brown" | "black" = "brown"): ReactNode[] {
  if (!str) return [];
  // 1. Triple or more asterisks -> double asterisks
  let normalized = str.replace(/\*{3,}/g, "**");
  // 2. Spaced asterisks from translation -> double asterisks
  normalized = normalized.replace(/\*\s+\*/g, "**");

  // Fix unmatched '**' (e.g. "** ஆம், ...")
  const boldMatches = normalized.match(/\*\*/g);
  if (boldMatches && boldMatches.length % 2 !== 0) {
    if (/^\s*\*\*[^*]+$/.test(normalized)) {
      normalized = normalized.replace(/^\s*\*\*([^\n,.]+)([,.]?)/, "**$1**$2");
    } else {
      normalized = normalized.replace(/\*\*/, "");
    }
  }

  // Tokenize bold (**...**) and inline code (`...`)
  const tokens = normalized.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);

  return tokens.map((token, idx) => {
    if (token.startsWith("**") && token.endsWith("**") && token.length >= 4) {
      const content = token.slice(2, -2).replace(/[*#•\-]/g, "").trim();
      if (defaultBoldColor === "brown") {
        return (
          <strong key={idx} className="font-semibold text-accent tracking-tight">
            {content}
          </strong>
        );
      }
      return (
        <strong key={idx} className="font-bold text-ink tracking-tight">
          {content}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`") && token.length >= 2) {
      return (
        <code
          key={idx}
          className="rounded border border-hairline/70 bg-shelf-2/60 px-1 py-0.5 font-mono text-xs text-accent font-medium"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    // Clean any stray asterisks or hashes from plain text token
    const cleanedToken = token.replace(/[*#]/g, "");
    return cleanedToken;
  });
}

/**
 * Renders an inline key point item:
 * - Subheading before the colon (e.g. "**Safe Operating Window**:" or "Significant Wave Height:")
 *   is rendered in BLACK ONLY (`font-bold text-ink`).
 * - Any highlighted content in the key point after the subheading is rendered in BROWN ONLY (`font-semibold text-accent`).
 */
function renderPointItem(itemText: string): ReactNode {
  const cleaned = itemText.replace(/\*\s+\*/g, "**");
  const colonIdx = cleaned.indexOf(":");
  if (colonIdx === -1) {
    return renderInlineMarkdown(formatAndHighlightContent(cleaned), "brown");
  }

  const labelRaw = cleaned.slice(0, colonIdx);
  const valueRaw = cleaned.slice(colonIdx + 1);

  // Clean label of any *, #, •, or - markers: NO asterisk mark in headings
  const labelClean = labelRaw.replace(/[*#•\-]/g, "").trim();

  return (
    <>
      <strong className="font-bold text-ink tracking-tight">{labelClean}: </strong>
      {renderInlineMarkdown(formatAndHighlightContent(valueRaw), "brown")}
    </>
  );
}

/**
 * Renders a paragraph block:
 * - Leading heading before a colon (e.g. "**Safety Verdict**:" or "**Key Environmental Parameters**:")
 *   is rendered in BLACK ONLY (`font-bold text-ink`).
 * - Any highlighted metrics or text in the rest of the paragraph is rendered in BROWN ONLY (`font-semibold text-accent`).
 */
function renderParagraphBlock(paraText: string): ReactNode {
  const normalized = paraText.replace(/\*\s+\*/g, "**");
  const match = normalized.match(/^(?:\*\*)?([\p{L}\p{M}\p{N}\s&/—–\-_()]+?)(?:\*\*)?:\s*([\s\S]*)$/u);
  if (match && match[1].trim().length < 60) {
    const headingClean = match[1].replace(/[*#•\-]/g, "").trim();
    const rest = match[2];
    return (
      <>
        <strong className="font-bold text-ink tracking-tight">{headingClean}: </strong>
        {renderInlineMarkdown(formatAndHighlightContent(rest), "brown")}
      </>
    );
  }
  return renderInlineMarkdown(formatAndHighlightContent(normalized), "brown");
}

function getSectionIcon(title: string) {
  const lower = title.toLowerCase();
  if (lower.includes("hazard") || lower.includes("warning") || lower.includes("lightning") || lower.includes("cyclone")) {
    return <AlertTriangle className="size-4 text-caution" />;
  }
  if (lower.includes("route") || lower.includes("course") || lower.includes("geospatial") || lower.includes("boundary") || lower.includes("imbl") || lower.includes("navigation")) {
    return <Compass className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("meteorological") || lower.includes("weather") || lower.includes("atmospheric") || lower.includes("day 1") || lower.includes("day 2") || lower.includes("day 3")) {
    return <Cloud className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("oceanographic") || lower.includes("tidal") || lower.includes("tide") || lower.includes("current")) {
    return <Waves className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("fishing") || lower.includes("pfz") || lower.includes("sector") || lower.includes("aggregation") || lower.includes("species")) {
    return <Crosshair className="size-4 text-go" />;
  }
  if (lower.includes("summary") || lower.includes("directive") || lower.includes("operational") || lower.includes("price") || lower.includes("market") || lower.includes("fuel")) {
    return <ShieldCheck className="size-4 text-accent" />;
  }
  return <FileText className="size-4 text-ink-dim" />;
}

type BlockElement =
  | { type: "paragraph"; text: string }
  | { type: "points"; items: string[] };

/**
 * Normalizes text to ensure headings and parameter labels are consistently highlighted,
 * and fixes broken linebreaks where a label was split from its answer.
 */
function normalizeResponseText(raw: string): string {
  if (!raw) return "";
  let text = raw.replace(/\*\s+\*/g, "**");

  // LLMs sometimes attach a word to a bold numeric token ("speed**0.12m/s**setting")
  // or omit the space after a closing parenthesis. Repair those boundaries
  // before tokenizing markdown so the styled spans cannot hide the separator.
  text = text
    .replace(/([\p{L}\p{N}])(?=\*\*(?=[+\-−]?\d))/gu, "$1 ")
    .replace(/(\*\*[^*]+\*\*)(?=[\p{L}\p{N}])/gu, "$1 ")
    .replace(/(\*\*[^*]+\*\*)(?=\*\*[^*]+\*\*)/g, "$1 ")
    .replace(/([)])(?=[\p{L}\p{N}])/gu, "$1 ")
    // Separate a metric label accidentally joined to a numeric measurement.
    .replace(/\b(speed|depth|height|temperature|current|wave|wind)(?=[+\-−]?\d)/giu, "$1 ");

  // Narrative text should use the same concise date style in every persona.
  // Keep time/zone suffixes intact when formatting ISO calendar dates.
  text = text
    .replace(/\b(20\d{2})-(\d{2})-(\d{2})\b/g, "$3/$2/$1")
    .replace(/\b(20\d{2})(\d{2})(\d{2})\b/g, "$3/$2/$1");

  // Keep date/time ranges readable even when the model wraps each value in
  // its own adjacent bold span: **14/10/2026****00:00to** ...
  text = text
    .replace(/(\d{2}\/\d{2}\/\d{4})(\*\*)(?=\*\*\d{2}:\d{2}\b)/g, "$1$2 ")
    .replace(/(\d{2}\/\d{2}\/\d{4})(?=(?:\*\*)?\d{2}:\d{2}\b)/g, "$1 ")
    .replace(/(\d{2}:\d{2})(?=to\b)/gi, "$1 ");

  // Split accidental combined headers like "Hazard Parameters: Alert Classification: ..."
  text = text.replace(
    /(?:^|\n)\s*(?:\*\*)?([\p{L}\p{M}\p{N}\s&/—–\-_()]+?\s+Parameters)(?:\*\*)?:\s*(?:\*\*)?([\p{L}\p{M}\p{N}\s&/—–\-_()]+?)(?:\*\*)?:\s*/giu,
    "\n\n**$1**:\n• **$2**: "
  );

  // Clean up bullet markers followed by stray asterisks before labels:
  // e.g. "• * Heading: value" or "* * Heading: value" -> "\n• **Heading**: value"
  text = text.replace(/(?:^|\n)\s*[•*\-]?\s*\*+\s*([\p{L}\p{M}\p{N}\s&/—–\-_()]+?):\s*/gu, "\n• **$1**: ");

  // 1. Clean up duplicate consecutive labels
  text = text.replace(
    /(?:^|\n)\s*(?:[•*\-]|\d+\.)?\s*(?:\*\*)?([\p{L}\p{M}\p{N}\s&/—–\-_()]+?)(?:\*\*)?:\s*\n+\s*(?:[•*\-]|\d+\.)?\s*(?:\*\*)?\1(?:\*\*)?:\s*/giu,
    "\n• **$1**: "
  );

  // 2. Fix broken labels where answer was placed on next line
  text = text.replace(
    /(?:^|\n)\s*(?:[•*\-]|\d+\.)?\s*(?:\*\*)?([\p{L}\p{M}\p{N}\s&/—–\-_()]+?)(?:\*\*)?:\s*\n+([^\n]+)/gu,
    (match, label, value) => {
      const trimmedLabel = label.trim();
      if (/parameters|points|findings|assessment|directives|details|overview|summary/i.test(trimmedLabel)) {
        return `\n\n**${trimmedLabel}**:\n${value.trim().startsWith("•") || value.trim().startsWith("*") ? value.trim() : "• " + value.trim()}`;
      }
      if (/verdict/i.test(trimmedLabel)) {
        return `\n\n**${trimmedLabel}**: ${value.trim()}`;
      }
      return `\n• **${trimmedLabel}**: ${value.trim().replace(/^[•*\-]\s*/, "")}`;
    }
  );

  // 3. Ensure Safety Verdict, Operational Verdict, Alert Status, etc. are highlighted in bold (NEVER bullet points)
  text = text.replace(
    /(?:^|\n)\s*[•*\-]?\s*(?:\*\*)?(Safety Verdict|Operational Verdict|Passage Verdict|Route Verdict|Diagnostic Verdict|Official Directive|Threat Assessment|Alert Status|Headline Alert Status|Direct Summary|Summary)(?:\*\*)?:\s*/gi,
    "\n\n**$1**: "
  );

  // If a response says "Headline Alert Status: *ACTIVE WEATHER WARNING" right next to safe/mild watches, normalize it to clean status
  text = text.replace(/\*\*Headline Alert Status\*\*:\s*\*?ACTIVE WEATHER WARNING\s*/gi, "**Alert Status**: ");

  // 4. Ensure Safe Operating Window, etc. are highlighted in bold with a bullet
  text = text.replace(
    /(?:^|\n)\s*(?:[•*\-]|\d+\.)?\s*(?:\*\*)?(Safe Operating Window|Operating Window|Passage Window|Departure Window|Validity Window)(?:\*\*)?:\s*/gi,
    "\n• **$1**: "
  );

  // 5. Clean up any accidental double bullets or duplicated labels created by consecutive replacements
  text = text.replace(
    /(?:•\s*)+\*\*(Safe Operating Window|Operating Window|Passage Window|Departure Window|Validity Window)\*\*:\s*(?:[•*\-]\s*)?(?:\*\*)?\1(?:\*\*)?:\s*/gi,
    "• **$1**: "
  );
  text = text.replace(
    /\*\*(Safe Operating Window|Operating Window|Passage Window|Departure Window|Validity Window)\*\*:\s*(?:[•*\-]\s*)+/gi,
    "**$1**: "
  );

  // 4. Ensure Key Parameters / Environmental Parameters are clean bold headings
  text = text.replace(
    /(?:^|\n)\s*(?:[•*\-]|\d+\.)?\s*(?:\*\*)?(Key Environmental Parameters|Key Parameters|Navigational Parameters|Physical & Biological Parameters|Measured Marine Parameters|Hazard Parameters)(?:\*\*)?:\s*/gi,
    "\n\n**$1**:\n"
  );

  return text.trim();
}

/**
 * Parses unsectioned raw text into paragraphs and structured point lists.
 * Filters out "Advisory Recency" points as requested.
 */
function parseTextBlocks(raw: string): BlockElement[] {
  const normalized = normalizeResponseText(raw);
  const rawParagraphs = normalized.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const elements: BlockElement[] = [];

  for (const para of rawParagraphs) {
    const cleanedPara = para.replace(/\bAll Parameters Within Safe Operational Limits\b[.:]?/gi, "").trim();
    if (!cleanedPara) continue;

    const lines = cleanedPara.split("\n").map((l) => l.trim()).filter(Boolean);
    const hasPoints = lines.some((l) => /^(?:[•*\-]|\d+\.)\s+/.test(l));

    if (!hasPoints) {
      elements.push({ type: "paragraph", text: cleanedPara });
      continue;
    }

    let currentPara: string[] = [];
    let currentPoints: string[] = [];

    for (const line of lines) {
      const pointMatch = line.match(/^(?:[•*\-]|\d+\.)\s+(.+)$/);
      if (pointMatch) {
        const itemText = pointMatch[1].trim();
        // Remove "Advisory Recency" completely
        if (/^\**advisory\s+recency\**/i.test(itemText) || /all parameters within safe operational limits/i.test(itemText)) {
          continue;
        }

        if (currentPara.length > 0) {
          elements.push({ type: "paragraph", text: currentPara.join(" ") });
          currentPara = [];
        }
        const cleaned = cleanItemContent(itemText);
        if (cleaned) currentPoints.push(cleaned);
      } else {
        if (currentPoints.length > 0) {
          elements.push({ type: "points", items: currentPoints });
          currentPoints = [];
        }
        currentPara.push(line);
      }
    }

    if (currentPara.length > 0) {
      elements.push({ type: "paragraph", text: currentPara.join(" ") });
    }
    if (currentPoints.length > 0) {
      elements.push({ type: "points", items: currentPoints });
    }
  }

  return elements;
}

interface ParsedSection {
  title: string;
  items: string[];
}

export function FormattedResponse({ text, className = "", language, large = false }: FormattedResponseProps) {
  const t = useT();
  const langClass = fontClassForLanguage(language);
  const parsed = useMemo(() => {
    if (!text) return null;

    // 1. The leading "GO: reason", split off so the verdict is not said twice.
    const split = splitVerdictHeader(text);
    let raw = normalizeResponseText(split.body);
    const verdictHeader: { type: "GO" | "CAUTION" | "NO_GO"; text: string } | null =
      split.verdict ? { type: split.verdict, text: split.reason } : null;

    // 2. Look for sections marked by "### "
    const hasHeadings = /###\s+/.test(raw);

    if (!hasHeadings) {
      const blocks = parseTextBlocks(raw);
      return { verdictHeader, intro: "", metadata: null, sections: [], blocks };
    }

    // Extract intro/metadata before the first "### "
    const firstSectionIdx = raw.search(/(?:--\s*)?###\s+/);
    let intro = "";
    let metadata: { sector?: string; timestamp?: string } | null = null;

    if (firstSectionIdx > 0) {
      intro = raw.substring(0, firstSectionIdx).trim();
      raw = raw.substring(firstSectionIdx).trim();

      const sectorMatch = intro.match(/\*Operational Sector:\*\s*([^*]+)/i);
      const timeMatch = intro.match(/\*Timestamp:\*\s*([^*]+)/i);
      if (sectorMatch || timeMatch) {
        metadata = {
          sector: sectorMatch ? sectorMatch[1].trim() : undefined,
          timestamp: timeMatch ? timeMatch[1].trim() : undefined,
        };
      }
    }

    // Clean up leading "--" or dashes before first section
    raw = raw.replace(/^--\s*/, "");

    // Split into sections by "### "
    const sectionBlocks = raw.split(/(?:^|\n|\s+--\s*|\s+)###\s+/).filter(Boolean);
    const sections: ParsedSection[] = [];

    for (const block of sectionBlocks) {
      const trimmedBlock = block.trim();
      if (!trimmedBlock) continue;

      const titleMatch = trimmedBlock.match(/^([^\n*]+)/);
      if (!titleMatch) continue;

      const title = titleMatch[1].trim();
      const content = trimmedBlock.slice(titleMatch[0].length).trim();

      // Split content into bullet points
      const rawItems = content
        .split(/(?:^|\n|\s+)(?:[•*\-]|\d+\.)\s+/)
        .map((it) => it.trim())
        .filter(Boolean);

      const items = (rawItems.length > 0 ? rawItems : [content])
        .filter((it) => !/^\**advisory\s+recency\**/i.test(it))
        .map(cleanItemContent);

      sections.push({ title, items });
    }

    return { verdictHeader, intro, metadata, sections, blocks: [] };
  }, [text]);

  if (!parsed) return null;

  // Unsectioned response (e.g. Fisherman persona or conversational reply)
  if (parsed.sections.length === 0) {
    return (
      <div lang={language ?? undefined} className={`space-y-3 ${className} ${langClass}`}>
        {parsed.blocks.map((block, idx) => {
          if (block.type === "paragraph") {
            return (
              <p
                key={idx}
                className={`${typography.response.body} text-ink/90 leading-relaxed ${large ? "text-lg font-medium" : ""}`}
              >
                {renderParagraphBlock(block.text)}
              </p>
            );
          }

          // Simple, clean parameter list — with colored directional pointer
          return (
            <div key={idx} className="my-2.5 space-y-2.5 pl-0.5">
              {block.items.map((item, itemIdx) => (
                <div
                  key={itemIdx}
                  className="flex items-start gap-2.5 py-0.5 text-ink/90"
                >
                  <PointPointer />
                  <div
                    className={`min-w-0 flex-1 leading-relaxed ${typography.response.body} ${large ? "text-lg font-medium" : ""}`}
                  >
                    {renderPointItem(item)}
                  </div>
                </div>
              ))}
            </div>
          );
        })}
      </div>
    );
  }

  // Sectioned response with markdown headers
  return (
    <div lang={language ?? undefined} className={`space-y-3.5 ${className} ${langClass}`}>
      {/* Metadata Strip (Sector & Timestamp) */}
      {parsed.metadata && (
        <div className={`flex flex-wrap items-center gap-3 rounded-lg border border-hairline/60 bg-shelf-1/40 px-3 py-1.5 ${typography.response.metadata}`}>
          {parsed.metadata.sector && (
            <span className="inline-flex items-center gap-1.5">
              <MapPin className="size-3 text-accent shrink-0" />
              <strong className="font-medium text-ink-dim">{t("chatTurn.sector")}</strong>{" "}
              {parsed.metadata.sector}
            </span>
          )}
          {parsed.metadata.timestamp && (
            <span className="inline-flex items-center gap-1.5 font-mono">
              <Clock className="size-3 text-ink-dim shrink-0" />
              {parsed.metadata.timestamp}
            </span>
          )}
        </div>
      )}

      {/* Section Cards */}
      <div className="grid gap-3">
        {parsed.sections.map((section, sIdx) => {
          const isDirective =
            section.title.toLowerCase().includes("directive") ||
            section.title.toLowerCase().includes("summary");

          return (
            <div
              key={sIdx}
              className={`overflow-hidden rounded-xl border backdrop-blur-md transition-all ${
                isDirective
                  ? "border-go/30 bg-go/5 shadow-xs"
                  : "border-hairline/70 bg-shelf-1/40 hover:border-hairline-strong"
              }`}
            >
              {/* Section Header */}
              <div
                className={`flex items-center gap-2.5 border-b px-4 py-2.5 ${typography.response.heading} ${
                  isDirective
                    ? "border-go/20 bg-go/10 text-go"
                    : "border-hairline/60 bg-shelf-2/50 text-ink"
                }`}
              >
                {getSectionIcon(section.title)}
                <span>{section.title}</span>
              </div>

              {/* Section Items in Simple Clean List */}
              <div className="p-3.5 space-y-2.5">
                {section.items.map((item, iIdx) => (
                  <div
                    key={iIdx}
                    className={`flex items-start gap-2.5 py-0.5 text-ink/90 ${typography.response.body} ${large ? "text-lg font-medium" : ""}`}
                  >
                    <PointPointer />
                    <div className="min-w-0 flex-1 leading-relaxed">
                      {renderPointItem(item)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
