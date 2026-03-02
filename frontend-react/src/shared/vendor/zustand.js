import { useSyncExternalStore } from "react";

export function create(createState) {
  let state;
  const listeners = new Set();

  const setState = (partial) => {
    const nextState = typeof partial === "function" ? partial(state) : partial;
    state = { ...state, ...nextState };
    for (const listener of listeners) {
      listener();
    }
  };

  const getState = () => state;

  const api = {
    setState,
    getState,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };

  state = createState(setState, getState, api);

  function useStore(selector = (snapshot) => snapshot) {
    return useSyncExternalStore(api.subscribe, () => selector(api.getState()));
  }

  useStore.getState = api.getState;
  useStore.setState = api.setState;
  useStore.subscribe = api.subscribe;

  return useStore;
}
