import { useState } from "react";
import { useI18n } from "../../i18n";
import type { InteractionMap as InteractionMapData, RiskFinding } from "../../lib/types";
import { Tabs } from "../ui/Tabs";
import { InteractionHeatmap } from "./InteractionHeatmap";
import { InteractionNetworkMap } from "./InteractionNetworkMap";

type ViewId = "network" | "heatmap";

/** Network map and heatmap share the same data (`interaction_map`); the doctor switches between them with a tab. */
export function InteractionViews({ map, findings }: { map: InteractionMapData; findings: RiskFinding[] }) {
  const { t } = useI18n();
  const [view, setView] = useState<ViewId>("network");

  return (
    <Tabs
      label={t("insights.tabs.label")}
      active={view}
      onChange={(id) => setView(id === "heatmap" ? "heatmap" : "network")}
      tabs={[
        { id: "network", label: t("insights.tab.network"), panel: <InteractionNetworkMap map={map} /> },
        { id: "heatmap", label: t("insights.tab.heatmap"), panel: <InteractionHeatmap map={map} findings={findings} /> },
      ]}
    />
  );
}