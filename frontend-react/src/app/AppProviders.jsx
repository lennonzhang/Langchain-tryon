import { useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionRepositoryProvider } from "../features/sessions/sessionRepositoryContext";
import { MemorySessionRepository } from "../entities/session/memorySessionRepository";

export function AppProviders({ repository, children }) {
  const sessionRepository = useMemo(() => repository || new MemorySessionRepository(), [repository]);
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            refetchOnWindowFocus: false,
          },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <SessionRepositoryProvider repository={sessionRepository}>{children}</SessionRepositoryProvider>
    </QueryClientProvider>
  );
}
