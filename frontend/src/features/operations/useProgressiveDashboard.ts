import { useCallback, useEffect, useRef, useState } from "react";

import {
  contextMatches,
  getLivePanel,
  liveError,
  type Horizon,
  type LiveContext,
  type LivePanel,
  type PanelDataMap,
  type Pollutant,
} from "../../api/live";

export interface ActiveCity {
  query: string;
  cityId?: string;
  name: string;
  state?: string | null;
}

export type PanelState<P extends LivePanel> =
  | { status: "loading"; data?: PanelDataMap[P]; context?: LiveContext; error?: never }
  | { status: "ready"; data: PanelDataMap[P]; context: LiveContext; error?: never }
  | { status: "error"; data?: PanelDataMap[P]; context?: LiveContext; error: string };

export type ProgressivePanels = { [P in LivePanel]: PanelState<P> };

const panels: LivePanel[] = [
  "current",
  "stations",
  "forecast",
  "map",
  "source-intelligence",
  "actions",
  "advisory",
];

function loadingPanels(): ProgressivePanels {
  return Object.fromEntries(panels.map((panel) => [panel, { status: "loading" }])) as ProgressivePanels;
}

export function useProgressiveDashboard(
  city: ActiveCity,
  pollutant: Pollutant,
  horizon: Horizon,
) {
  const [states, setStates] = useState<ProgressivePanels>(loadingPanels);
  const generation = useRef(0);
  const controllers = useRef(new Map<LivePanel, AbortController>());

  const loadPanel = useCallback(
    async <P extends LivePanel>(panel: P, requestGeneration: number, preserve: boolean) => {
      controllers.current.get(panel)?.abort();
      const controller = new AbortController();
      controllers.current.set(panel, controller);
      setStates((previous) => ({
        ...previous,
        [panel]: {
          status: "loading",
          ...(preserve && previous[panel].data
            ? { data: previous[panel].data, context: previous[panel].context }
            : {}),
        },
      }));
      try {
        const response = await getLivePanel(
          panel,
          { city: city.query, pollutant, horizon },
          controller.signal,
        );
        if (controller.signal.aborted || requestGeneration !== generation.current) return;
        if (!contextMatches(response.context, { cityId: city.cityId, cityName: city.name, pollutant, horizon })) {
          throw new Error("context_mismatch");
        }
        setStates((previous) => {
          const existingSnapshot = Object.values(previous).find(
            (state) => state.status === "ready" && state.context,
          )?.context?.snapshot_id;
          if (existingSnapshot && existingSnapshot !== response.context.snapshot_id) {
            return {
              ...previous,
              [panel]: { status: "error", error: "This panel received a newer snapshot. Retry to synchronise it." },
            };
          }
          return {
            ...previous,
            [panel]: { status: "ready", data: response.data, context: response.context },
          };
        });
      } catch (error) {
        if (controller.signal.aborted || requestGeneration !== generation.current) return;
        const message = error instanceof Error && error.message === "context_mismatch"
          ? "This response did not match the selected city. Retry the panel."
          : liveError(error);
        setStates((previous) => ({
          ...previous,
          [panel]: {
            status: "error",
            error: message,
            ...(preserve && previous[panel].data
              ? { data: previous[panel].data, context: previous[panel].context }
              : {}),
          },
        }));
      }
    },
    [city.cityId, city.name, city.query, horizon, pollutant],
  );

  useEffect(() => {
    generation.current += 1;
    const requestGeneration = generation.current;
    controllers.current.forEach((controller) => controller.abort());
    controllers.current.clear();
    setStates(loadingPanels());
    panels.forEach((panel) => void loadPanel(panel, requestGeneration, false));
    const activeControllers = controllers.current;
    return () => {
      activeControllers.forEach((controller) => controller.abort());
    };
  }, [loadPanel]);

  const retry = useCallback(
    (panel: LivePanel) => void loadPanel(panel, generation.current, true),
    [loadPanel],
  );

  const snapshotId = Object.values(states).find(
    (state) => state.status === "ready" && state.context,
  )?.context?.snapshot_id;

  return { states, retry, snapshotId };
}
