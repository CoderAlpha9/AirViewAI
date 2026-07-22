import { Navigate, createBrowserRouter } from "react-router-dom";

import { AppLayout } from "../layouts/AppLayout";
import { OperationsDashboardPage } from "../pages/OperationsDashboardPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <OperationsDashboardPage /> },
      { path: "dashboard", element: <OperationsDashboardPage /> },
      { path: "command-centre", element: <Navigate to="/" replace /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
