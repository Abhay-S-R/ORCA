// P4.1 — `/safety` posted to the same `/query` endpoint as `/ask` with one
// extra param (vessel class); a second page calling the same endpoint is the
// opposite of orca_final §2's directive. Its two genuine carry-overs — the
// vessel selector and the verdict-first card — now live on `/ask` itself
// (VesselChip above the composer; PersonaAnswerMatrix already leads with the
// verdict). The URL stays alive as a redirect so nothing that linked here
// breaks. Points at `/alerts` now that P4.11 has shipped that surface.
import { redirect } from "next/navigation";

export default function SafetyRedirect() {
  redirect("/alerts");
}
