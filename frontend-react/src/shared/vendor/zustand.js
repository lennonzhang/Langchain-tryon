import { useRef, useSyncExternalStore } from "react";

function shallowEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  const keysA = Object.keys(a);
  if (keysA.length !== Object.keys(b).length) return false;
  for (const key of keysA) {
    if (!Object.is(a[key], b[key])) return false;
  }
  return true;
}

export function useShallow(selector) {
  const prevRef = useRef(undefined);
  return (state) => {
    const next = selector(state);
    if (shallowEqual(prevRef.current, next)) return prevRef.current;
    prevRef.current = next;
    return next;
  };
}

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
