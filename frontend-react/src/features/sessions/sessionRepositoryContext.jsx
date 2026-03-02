import { createContext, useContext } from "react";
import { MemorySessionRepository } from "../../entities/session/memorySessionRepository";

const defaultRepository = new MemorySessionRepository();

const SessionRepositoryContext = createContext(defaultRepository);

export function SessionRepositoryProvider({ repository = defaultRepository, children }) {
  return <SessionRepositoryContext.Provider value={repository}>{children}</SessionRepositoryContext.Provider>;
}

export function useSessionRepository() {
  return useContext(SessionRepositoryContext);
}
