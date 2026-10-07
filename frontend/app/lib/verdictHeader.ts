// The leading "GO: reason" of an answer, split from the body so the card does not say the
// verdict twice (PersonaAnswerMatrix's chip and reason line already state it).
//
// The header ends at the first line break, or at ". " followed by a capital letter, or at
// the end of the text. That works for English. It does not for a translated answer: Kannada,
// Tamil, Hindi and the other Indic scripts have no capital letters, and translation joins the
// header and the body into one line, so the header ran to the end of the text and the whole
// answer was hidden (found 2026-10-07, all nine languages). Hence the rule below: the split is
// only taken when a body is left; otherwise only the "GO:" label is removed and the rest is
// shown. An answer is never blank because of this function.

export type Verdict = "GO" | "CAUTION" | "NO_GO";

export function splitVerdictHeader(text: string): { verdict: Verdict | null; reason: string; body: string } {
  const raw = (text ?? "").trim();
  const label = raw.match(/^(GO|CAUTION|NO_GO):\s*/i);
  if (!label) return { verdict: null, reason: "", body: raw };

  const verdict = label[1].toUpperCase() as Verdict;
  const header = raw.match(/^(GO|CAUTION|NO_GO):\s*([^\n*]+?)(?:\.\s+(?=[A-Z])|\n|$)/i);
  if (header) {
    const body = raw.slice(header[0].length).trim();
    if (body) return { verdict, reason: header[2].trim(), body };
  }
  // No separable body: keep everything after the label.
  return { verdict, reason: "", body: raw.slice(label[0].length).trim() };
}
