import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { DataReadinessPage } from "../pages/DataReadinessPage";
import { HomePage } from "../pages/HomePage";
import { ForecastEvaluationPage } from "../pages/ForecastEvaluationPage";
import { SourceIntelligencePage } from "../pages/SourceIntelligencePage";
import { CommandCentrePage } from "../pages/CommandCentrePage";
import { CitizenAdvisoryPage } from "../pages/CitizenAdvisoryPage";
import { IndiaCoveragePage } from "../pages/IndiaCoveragePage";
import { AgentAuditPage } from "../pages/AgentAuditPage";
import { NotFoundPage } from "../pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "command-centre", element: <CommandCentrePage /> },
      { path: "citizen-advisory", element: <CitizenAdvisoryPage /> },
      { path: "india-coverage", element: <IndiaCoveragePage /> },
      { path: "agent-audit", element: <AgentAuditPage /> },
      { path: "data-readiness", element: <DataReadinessPage /> },
      { path: "forecast-evaluation", element: <ForecastEvaluationPage /> },
      { path: "source-intelligence", element: <SourceIntelligencePage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
