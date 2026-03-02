import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSessionRepository } from "./sessionRepositoryContext";
import { NEW_SESSION_KEY } from "../../shared/store/chatUiStore";

export const SESSION_LIST_QUERY_KEY = ["sessions"];
export const sessionDetailQueryKey = (sessionId) => ["session", sessionId];

export function useSessionListQuery() {
  const repository = useSessionRepository();
  return useQuery({
    queryKey: SESSION_LIST_QUERY_KEY,
    queryFn: () => repository.listSessions(),
  });
}

export function useSessionDetailQuery(sessionId) {
  const repository = useSessionRepository();
  return useQuery({
    queryKey: sessionDetailQueryKey(sessionId),
    queryFn: () => repository.getSession(sessionId),
    enabled: Boolean(sessionId) && sessionId !== NEW_SESSION_KEY,
  });
}

export function useCreateSessionMutation() {
  const repository = useSessionRepository();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (initial) => repository.createSession(initial),
    onSuccess: async (session) => {
      queryClient.setQueryData(sessionDetailQueryKey(session.id), session);
      await queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    },
  });
}

export function useDeleteSessionMutation() {
  const repository = useSessionRepository();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (sessionId) => repository.deleteSession(sessionId),
    onSuccess: async (_unused, sessionId) => {
      queryClient.removeQueries({ queryKey: sessionDetailQueryKey(sessionId) });
      await queryClient.invalidateQueries({ queryKey: SESSION_LIST_QUERY_KEY });
    },
  });
}
