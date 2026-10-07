// Runnable check for app/lib/verdictHeader.ts (no test framework in this package).
// Run: node scripts/check-verdict-header.mjs   (Node 22.18+ strips the TypeScript types itself)
//
// The Indic cases are the real backend answers that went blank on the card on 2026-10-07:
// the old rule took the whole answer as the "GO: reason" header in all nine languages.
import assert from "node:assert/strict";
import { splitVerdictHeader } from "../app/lib/verdictHeader.ts";

const KANNADA =
  "GO: ಸುರಕ್ಷಿತ ಕಾರ್ಯಾಚರಣೆಯ ಮಿತಿಯೊಳಗಿನ ಎಲ್ಲಾ ನಿಯತಾಂಕಗಳು ನಾಳೆ ರಾಮೇಶ್ವರಂನ ಸಮುದ್ರವು ಲಘು ಗಾಳಿ, ಕಡಿಮೆ ಅಲೆಗಳು ಮತ್ತು ಏರುತ್ತಿರುವ ಉಬ್ಬರವಿಳಿತದಿಂದ ಶಾಂತವಾಗಿದೆ ಮತ್ತು ಯಾವುದೇ ಮಿಂಚಿನ ಮುನ್ಸೂಚನೆ ಇಲ್ಲ. ಹೊರಗೆ ಹೋಗುವುದು ಸುರಕ್ಷಿತವಾಗಿದೆ.";
const TAMIL =
  "GO: பாதுகாப்பான செயல்பாட்டு வரம்புகளுக்குள் உள்ள அனைத்து அளவுருக்களும் நாளை காலை ஒரு சிறிய மீன்பிடிக் கப்பலுக்கு பாதுகாப்பானவை; அலைகள் குறைவாக உள்ளன. அருகிலுள்ள மீன்பிடி மண்டலம் சென்னையின் கிழக்கே 23 km ஆகும்.";
const HINDI = "GO: सुरक्षित परिचालन सीमाओं के भीतर सभी मापदंड। कम ज्वार लगभग 1.5 घंटे में आएगा; लहरें कम हैं और हवा शांत है।";

let checks = 0;
function check(name, fn) {
  fn();
  checks += 1;
  console.log("ok -", name);
}

// 1. A native-script answer is never hidden: the body keeps the text, only the label goes.
for (const [name, text] of [["Kannada", KANNADA], ["Tamil", TAMIL], ["Hindi", HINDI]]) {
  check(`${name}: body is the whole answer minus the GO: label`, () => {
    const out = splitVerdictHeader(text);
    assert.equal(out.verdict, "GO");
    assert.equal(out.body, text.slice("GO: ".length).trim());
    assert.ok(out.body.length > 50);
  });
}

// 2. English keeps its old behaviour: header off, body kept.
check("English with a blank line keeps the body", () => {
  const out = splitVerdictHeader("GO: All Parameters Within Safe Operational Limits\n\nThe sea is calm near Kochi.");
  assert.deepEqual(out, { verdict: "GO", reason: "All Parameters Within Safe Operational Limits", body: "The sea is calm near Kochi." });
});
check("English on one line splits at the sentence", () => {
  const out = splitVerdictHeader("GO: All Parameters Within Safe Operational Limits. It is safe to head out near Kochi.");
  assert.equal(out.reason, "All Parameters Within Safe Operational Limits");
  assert.equal(out.body, "It is safe to head out near Kochi.");
});
check("CAUTION and NO_GO split the same way", () => {
  assert.equal(splitVerdictHeader("CAUTION: Rough Sea State\n\nWaves 2.4 m.").body, "Waves 2.4 m.");
  assert.equal(splitVerdictHeader("no_go: Lightning active. Stay in port.").verdict, "NO_GO");
});

// 3. A header with nothing after it is shown, not blanked.
check("a bare header still shows its text", () => {
  assert.equal(splitVerdictHeader("GO: All Parameters Within Safe Operational Limits").body, "All Parameters Within Safe Operational Limits");
});

// 4. Text without a verdict is untouched.
check("no verdict label: text unchanged", () => {
  assert.deepEqual(splitVerdictHeader("  The nearest zone is 49 km WNW.  "), { verdict: null, reason: "", body: "The nearest zone is 49 km WNW." });
  assert.equal(splitVerdictHeader("Go fishing north of the harbour.").verdict, null);
  assert.equal(splitVerdictHeader("").body, "");
});

console.log(`\n${checks} checks passed`);
