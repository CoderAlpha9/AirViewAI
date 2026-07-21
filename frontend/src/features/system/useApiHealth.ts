import { useEffect, useState } from "react";

import { getHealth } from "../../api/system";
import type { HealthResponse } from "../../types/domain";

type HealthState =
  | { state: "checking"; data: null }
  | { state: "connected"; data: HealthResponse }
  | { state: "unavailable"; data: null };

export function useApiHealth(): HealthState {
  const [health, setHealth] = useState<HealthState>({ state: "checking", data: null });

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((data) => setHealth({ state: "connected", data }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error("AirView API health check failed", error);
          setHealth({ state: "unavailable", data: null });
        }
      });

    return () => controller.abort();
  }, []);

  return health;
}

