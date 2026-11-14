import type { ReactNode } from "react";
import { DemoBadge } from "./DemoBadge";

interface Props {
  title: string;
  subtitle?: string;
  /** Show the dashed DEMO DATA label under the title (as on the Patients and Analyses frames). */
  demo?: boolean;
  /** Right-hand actions, e.g. the primary button. */
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, demo = false, actions }: Props) {
  return (
    <div className="page-head">
      <div className="page-head-text">
        <h1>{title}</h1>
        {demo && <DemoBadge />}
        {subtitle && <p className="muted page-sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}