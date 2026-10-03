import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router-dom";

import { AuthProvider } from "@/components/common/AuthProvider";
import { TooltipProvider } from "@/components/ui/tooltip";

export function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
}

/** Renders `ui` at `route` inside the real providers (auth reads /auth/me from MSW). */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", path = "*", extraRoutes = [] }: { route?: string; path?: string; extraRoutes?: RouteObject[] } = {},
): RenderResult & { client: QueryClient } {
  const client = testQueryClient();
  const router = createMemoryRouter([{ path, element: ui }, ...extraRoutes], { initialEntries: [route] });
  const result = render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return { ...result, client };
}
