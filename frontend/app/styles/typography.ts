// Unified typography system for ORCA - Claude-inspired consistent sizing
// Ensures readable, accessible text across all personas and components

export const typography = {
  // Response display typography
  response: {
    heading: "text-[18px] sm:text-[20px] font-semibold leading-snug tracking-tight",
    body: "text-[16px] sm:text-[17px] leading-relaxed",
    caption: "text-[14px] sm:text-[15px] leading-normal",
    metadata: "text-[13px] text-ink-dim leading-tight",
  },

  // Data display typography (numbers, measurements, values)
  data: {
    primary: "text-[17px] sm:text-[18px] font-medium",
    secondary: "text-[15px] sm:text-[16px]",
    unit: "text-[14px] text-ink-muted",
  },

  // Chat interface typography
  chat: {
    query: "text-[16px] sm:text-[17px] leading-relaxed",
    history: "text-[15px] sm:text-[16px] leading-relaxed",
    timestamp: "text-[13px] text-ink-dim",
  },

  // Component-specific typography
  badge: {
    default: "text-[14px] font-medium",
    small: "text-[13px] font-medium",
  },

  button: {
    default: "text-[15px] font-medium",
    small: "text-[14px] font-medium",
  },
};

// Minimum font size enforced across the application
export const MIN_FONT_SIZE = "13px";

// Maximum font size for headings
export const MAX_FONT_SIZE = "22px";
