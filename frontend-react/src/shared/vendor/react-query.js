import { createContext, createElement, useContext, useEffect, useMemo, useRef, useState } from "react";

function toKeyString(queryKey) {
  return JSON.stringify(queryKey || []);
}

function isPrefixKey(target, prefix) {
  const targetArr = Array.isArray(target) ? target : [];
  const prefixArr = Array.isArray(prefix) ? prefix : [];
  if (prefixArr.length > targetArr.length) return false;
  for (let i = 0; i < prefixArr.length; i += 1) {
    if (targetArr[i] !== prefixArr[i]) return false;
  }
  return true;
}

export class QueryClient {
  constructor() {
    this.cache = new Map();
    this.staleKeys = new Set();
    this.listeners = new Set();
  }

  setQueryData(queryKey, data) {
    this.cache.set(toKeyString(queryKey), data);
    this.staleKeys.delete(toKeyString(queryKey));
    this.emit();
  }

  getQueryData(queryKey) {
    return this.cache.get(toKeyString(queryKey));
  }

  invalidateQueries({ queryKey }) {
    for (const key of this.cache.keys()) {
      const parsed = JSON.parse(key);
      if (!queryKey || isPrefixKey(parsed, queryKey)) {
        this.staleKeys.add(key);
      }
    }
    this.emit();
    return Promise.resolve();
  }

  removeQueries({ queryKey }) {
    const target = toKeyString(queryKey);
    this.cache.delete(target);
    this.staleKeys.delete(target);
    this.emit();
  }

  isStale(queryKey) {
    return this.staleKeys.has(toKeyString(queryKey));
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }
}

const QueryClientContext = createContext(null);

export function QueryClientProvider({ client, children }) {
  return createElement(QueryClientContext.Provider, { value: client }, children);
}

export function useQueryClient() {
  const client = useContext(QueryClientContext);
  if (!client) {
    throw new Error("QueryClientProvider is missing");
  }
  return client;
}

export function useQuery({ queryKey, queryFn, enabled = true }) {
  const client = useQueryClient();
  const keyString = useMemo(() => toKeyString(queryKey), [queryKey]);
  const queryFnRef = useRef(queryFn);
  queryFnRef.current = queryFn;
  const queryKeyRef = useRef(queryKey);
  queryKeyRef.current = queryKey;
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState(() => {
    const cached = client.getQueryData(queryKeyRef.current);
    return {
      data: cached,
      isLoading: enabled && cached === undefined,
      error: null,
    };
  });

  useEffect(() => {
    const unsub = client.subscribe(() => {
      const cached = client.getQueryData(queryKeyRef.current);
      setRevision((value) => value + 1);
      setState((prev) => ({ ...prev, data: cached }));
    });
    return unsub;
  }, [client, keyString]);

  useEffect(() => {
    let cancelled = false;
    if (!enabled) {
      return () => {
        cancelled = true;
      };
    }

    const cached = client.getQueryData(queryKeyRef.current);
    if (cached !== undefined && !client.isStale(queryKeyRef.current)) {
      setState((prev) => ({ ...prev, data: cached, isLoading: false }));
      return () => {
        cancelled = true;
      };
    }

    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    Promise.resolve(queryFnRef.current())
      .then((data) => {
        if (cancelled) return;
        client.setQueryData(queryKeyRef.current, data);
        setState({ data, isLoading: false, error: null });
      })
      .catch((error) => {
        if (cancelled) return;
        setState({ data: undefined, isLoading: false, error });
      });

    return () => {
      cancelled = true;
    };
  }, [client, enabled, keyString, revision]);

  return state;
}

export function useMutation({ mutationFn, onSuccess }) {
  const [isPending, setPending] = useState(false);

  async function mutateAsync(variables) {
    setPending(true);
    try {
      const result = await mutationFn(variables);
      await onSuccess?.(result, variables);
      return result;
    } finally {
      setPending(false);
    }
  }

  return {
    mutateAsync,
    isPending,
  };
}
