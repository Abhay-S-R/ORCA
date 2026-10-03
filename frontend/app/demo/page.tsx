"use client";

// P6.6 (orca_final §29.2) — `/demo`: one route, five scenario cards, each a
// one-click run of the real production graph. Deliberately absent from
// NAV_ROUTES (persona/config.ts) — hidden from every persona's nav,
// reachable only by URL or from the tour, per the point's own text.
import { Compass } from "lucide-react";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Panel } from "../components/Panel";
import { GajaReplay } from "./GajaReplay";
import { IMBLCrossing } from "./IMBLCrossing";
import { ScenarioCard } from "./ScenarioCard";
import { SCENARIOS } from "./scenarios";

export default function DemoPage() {
  return (
    <PageBody className="mx-auto max-w-4xl">
      <PageHeader
        title="Scenario demonstrations"
        lede="Five pinned scenarios, each a one-click run of the real production graph — never a video, never a hardcoded string. See docs/competition/DLC_demo_script.md for the recorded shot list this page is built to run."
        action={<Compass className="size-6 text-ocean-cyan" aria-hidden="true" />}
      />
      <div className="space-y-5">
        {SCENARIOS.map((scenario) => {
          // Anchor id, not a Panel prop — lets /reasoning's scenario rail
          // deep-link here as "IMBL Approach — Palk Bay" per the plan's own
          // text, and scroll straight to the card the same way a URL hash
          // always has, no new navigation mechanism invented for it.
          if (scenario.kind === "replay") {
            return (
              <div id={scenario.id} key={scenario.id}>
                <Panel title={scenario.title}>
                  <p className="mb-4 text-sm leading-relaxed text-ink-muted">{scenario.summary}</p>
                  <GajaReplay />
                </Panel>
              </div>
            );
          }
          if (scenario.kind === "stepper") {
            return (
              <div id={scenario.id} key={scenario.id}>
                <Panel title={scenario.title}>
                  <p className="mb-4 text-sm leading-relaxed text-ink-muted">{scenario.summary}</p>
                  <IMBLCrossing />
                </Panel>
              </div>
            );
          }
          return (
            <div id={scenario.id} key={scenario.id}>
              <ScenarioCard scenario={scenario} />
            </div>
          );
        })}
      </div>
    </PageBody>
  );
}
