import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { Layout } from "./components/Layout";
import { useScheme } from "./lib/colorScheme";
import { Batches } from "./pages/Batches";
import { ExportPage } from "./pages/Export";
import { Monitoring } from "./pages/Monitoring";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Overview";
import { PackDetailPage } from "./pages/PackDetail";
import { ReviewQueue } from "./pages/Review";
import { Upload } from "./pages/Upload";

// Polling pauses while the browser tab is hidden; refetching on focus catches up on return.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 2_000 } },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "upload", element: <Upload /> },
      { path: "batches", element: <Batches /> },
      { path: "batches/:batchId", element: <Batches /> },
      { path: "review", element: <ReviewQueue /> },
      { path: "review/:packId", element: <PackDetailPage /> },
      { path: "export", element: <ExportPage /> },
      { path: "monitoring", element: <Monitoring /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

function ThemedToaster() {
  const scheme = useScheme();
  return <Toaster theme={scheme} richColors closeButton position="top-right" toastOptions={{ style: { borderRadius: 16 } }} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <ThemedToaster />
    </QueryClientProvider>
  </StrictMode>,
);
