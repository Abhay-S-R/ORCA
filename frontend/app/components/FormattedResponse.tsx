"use client";

import React, { useMemo } from "react";
import {
  Compass,
  Cloud,
  Waves,
  Crosshair,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  FileText,
  CheckCircle2,
  Clock,
  MapPin,
} from "lucide-react";

interface FormattedResponseProps {
  text: string;
  className?: string;
}

/**
 * Parses inline markdown tokens (**bold**, `code`, *italic*) safely into React nodes.
 */
function renderInlineMarkdown(str: string): React.ReactNode[] {
  if (!str) return [];
  // Tokenize bold (**...**), inline code (`...`), and italics (*...*)
  const tokens = str.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);

  return tokens.map((token, idx) => {
    if (token.startsWith("**") && token.endsWith("**") && token.length >= 4) {
      return (
        <strong key={idx} className="font-semibold text-ink">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith("`") && token.endsWith("`") && token.length >= 2) {
      return (
        <code
          key={idx}
          className="rounded-md border border-hairline/80 bg-shelf-2/80 px-1.5 py-0.5 font-mono text-[11px] text-accent font-medium"
        >
          {token.slice(1, -1)}
        </code>
      );
    }
    if (token.startsWith("*") && token.endsWith("*") && token.length >= 2) {
      return (
        <em key={idx} className="italic text-ink-muted">
          {token.slice(1, -1)}
        </em>
      );
    }
    return token;
  });
}

function getSectionIcon(title: string) {
  const lower = title.toLowerCase();
  if (lower.includes("geospatial") || lower.includes("boundary") || lower.includes("imbl")) {
    return <Compass className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("meteorological") || lower.includes("weather") || lower.includes("atmospheric")) {
    return <Cloud className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("oceanographic") || lower.includes("tidal") || lower.includes("tide")) {
    return <Waves className="size-4 text-ocean-cyan" />;
  }
  if (lower.includes("fishing") || lower.includes("pfz") || lower.includes("sector")) {
    return <Crosshair className="size-4 text-go" />;
  }
  if (lower.includes("summary") || lower.includes("directive") || lower.includes("operational")) {
    return <ShieldCheck className="size-4 text-accent" />;
  }
  return <FileText className="size-4 text-ink-dim" />;
}

interface ParsedSection {
  title: string;
  items: string[];
}

export function FormattedResponse({ text, className = "" }: FormattedResponseProps) {
  const parsed = useMemo(() => {
    if (!text) return null;

    let raw = text.trim();

    // 1. Check for leading Verdict banner (e.g. "GO: All Parameters Within Safe Operational Limits")
    let verdictHeader: { type: "GO" | "CAUTION" | "NO_GO"; text: string } | null = null;
    // Non-greedy up to the first sentence break (". " + a capital letter) or
    // end of string — so a terse "GO: reason" still captures the whole
    // reason (no period to stop at), but "GO: reason. Then two more
    // sentences of elaboration." puts only the reason in the banner and
    // leaves the elaboration to flow into the normal paragraph/section
    // parsing below, instead of one banner growing to swallow a whole
    // paragraph.
    const verdictMatch = raw.match(/^(GO|CAUTION|NO_GO):\s*([^\n*]+?)(?:\.\s+(?=[A-Z])|$)/i);
    if (verdictMatch) {
      const vType = verdictMatch[1].toUpperCase() as "GO" | "CAUTION" | "NO_GO";
      verdictHeader = {
        type: vType,
        text: verdictMatch[2].trim(),
      };
      raw = raw.slice(verdictMatch[0].length).trim();
    }

    // 2. Look for sections marked by "### "
    // Note: some responses have " -- ### " or "\n### "
    const hasHeadings = /###\s+/.test(raw);

    if (!hasHeadings) {
      // Fallback: simple text with optional bullets or paragraphs
      const paragraphs = raw.split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
      return { verdictHeader, intro: "", metadata: null, sections: [], paragraphs };
    }

    // Extract intro/metadata before the first "### "
    const firstSectionIdx = raw.search(/(?:--\s*)?###\s+/);
    let intro = "";
    let metadata: { sector?: string; timestamp?: string } | null = null;

    if (firstSectionIdx > 0) {
      intro = raw.substring(0, firstSectionIdx).trim();
      raw = raw.substring(firstSectionIdx).trim();

      // Extract Operational Sector & Timestamp from intro if present
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

      // First line or up to first bullet/break is the title
      const titleMatch = trimmedBlock.match(/^([^\n*]+)/);
      if (!titleMatch) continue;

      const title = titleMatch[1].trim();
      const content = trimmedBlock.slice(titleMatch[0].length).trim();

      // Split content into bullet points
      // Bullet markers can be "* **", "* ", or "\n* "
      const rawItems = content
        .split(/(?:^|\n|\s+)\*\s+/)
        .map((it) => it.trim())
        .filter(Boolean);

      // If no bullets were found, just treat content as a single item
      const items = rawItems.length > 0 ? rawItems : [content];

      sections.push({ title, items });
    }

    return { verdictHeader, intro, metadata, sections, paragraphs: [] };
  }, [text]);

  if (!parsed) return null;

  // Simple unsectioned response (e.g. Fisherman persona or vernacular text)
  if (parsed.sections.length === 0) {
    return (
      <div className={`space-y-3 ${className}`}>
        {parsed.verdictHeader && (
          <div
            className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs font-semibold ${
              parsed.verdictHeader.type === "NO_GO"
                ? "border-no-go/40 bg-no-go/10 text-no-go"
                : parsed.verdictHeader.type === "CAUTION"
                ? "border-caution/40 bg-caution/10 text-caution"
                : "border-go/30 bg-go/10 text-go"
            }`}
          >
            {parsed.verdictHeader.type === "NO_GO" ? (
              <ShieldAlert className="size-4 shrink-0" />
            ) : parsed.verdictHeader.type === "CAUTION" ? (
              <AlertTriangle className="size-4 shrink-0" />
            ) : (
              <CheckCircle2 className="size-4 shrink-0" />
            )}
            <span>
              {parsed.verdictHeader.type}: {parsed.verdictHeader.text}
            </span>
          </div>
        )}
        {parsed.paragraphs.map((p, i) => (
          <p key={i} className="text-[14px] leading-relaxed text-ink">
            {renderInlineMarkdown(p)}
          </p>
        ))}
      </div>
    );
  }

  return (
    <div className={`space-y-3.5 ${className}`}>
      {/* 1. Verdict Banner */}
      {parsed.verdictHeader && (
        <div
          className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 shadow-sm backdrop-blur-md ${
            parsed.verdictHeader.type === "NO_GO"
              ? "border-no-go/40 bg-no-go/15 text-no-go"
              : parsed.verdictHeader.type === "CAUTION"
              ? "border-caution/40 bg-caution/15 text-caution"
              : "border-go/30 bg-go/10 text-go"
          }`}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            {parsed.verdictHeader.type === "NO_GO" ? (
              <ShieldAlert className="size-4 shrink-0" />
            ) : parsed.verdictHeader.type === "CAUTION" ? (
              <AlertTriangle className="size-4 shrink-0" />
            ) : (
              <CheckCircle2 className="size-4 shrink-0" />
            )}
            <span className="truncate text-xs font-semibold tracking-wide">
              {parsed.verdictHeader.type}: {parsed.verdictHeader.text}
            </span>
          </div>
          <span className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-ink-dim shrink-0">
            Directive
          </span>
        </div>
      )}

      {/* 2. Metadata Strip (Sector & Timestamp) */}
      {parsed.metadata && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline/60 bg-shelf-1/40 px-3 py-1.5 text-[11px] text-ink-muted">
          {parsed.metadata.sector && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3 text-accent shrink-0" />
              <strong className="font-medium text-ink-dim">Sector:</strong>{" "}
              {parsed.metadata.sector}
            </span>
          )}
          {parsed.metadata.timestamp && (
            <span className="inline-flex items-center gap-1 font-mono">
              <Clock className="size-3 text-ink-dim shrink-0" />
              {parsed.metadata.timestamp}
            </span>
          )}
        </div>
      )}

      {/* 3. Section Cards */}
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
                  ? "border-go/30 bg-go/5 shadow-md"
                  : "border-hairline/70 bg-shelf-1/60 hover:border-hairline-strong"
              }`}
            >
              {/* Section Header */}
              <div
                className={`flex items-center gap-2 border-b px-3.5 py-2 text-xs font-semibold ${
                  isDirective
                    ? "border-go/20 bg-go/10 text-go"
                    : "border-hairline/60 bg-shelf-2/50 text-ink"
                }`}
              >
                {getSectionIcon(section.title)}
                <span className="tracking-tight">{section.title}</span>
              </div>

              {/* Section Items */}
              <div className="p-3.5 space-y-2">
                {section.items.map((item, iIdx) => {
                  return (
                    <div
                      key={iIdx}
                      className="flex items-start gap-2.5 text-xs leading-relaxed text-ink-muted"
                    >
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent/80" />
                      <div className="min-w-0 flex-1">
                        {renderInlineMarkdown(item)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
