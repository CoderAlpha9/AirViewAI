import { createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { DataReadinessPage } from "../pages/DataReadinessPage";
import { HomePage } from "../pages/HomePage";
import { NotFoundPage } from "../pages/NotFoundPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "data-readiness", element: <DataReadinessPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
