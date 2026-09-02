// Honest stub for surfaces whose agent or algorithm is a later phase.
//
// Ground Rule 3 applied to empty screens: a fake chart or a mock route would
// make this product look more finished than it is, and a reviewer who spots
// it stops believing the real surfaces too. So these say plainly what is
// missing, what it depends on, and what to use meanwhile.
import type { ReactNode } from "react";
import { PageBody, PageHeader } from "./PageHeader";
import { EmptyState } from "./States";

export function Planned({
  title,
  lede,
  needs,
  meanwhile,
  icon,
}: {
  title: string;
  lede: string;
  needs: string;
  meanwhile?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <PageBody className="mx-auto max-w-3xl">
      <PageHeader title={title} lede={lede} />
      <EmptyState icon={icon} title="Not built yet" body={needs} action={meanwhile} />
    </PageBody>
  );
}
