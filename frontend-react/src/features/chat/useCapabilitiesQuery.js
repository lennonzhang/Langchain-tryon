import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchCapabilities } from "../../shared/api/chatApiClient";
import { FALLBACK_CAPABILITIES } from "../../utils/models";

function normalizeModelChoice(caps) {
  const models = Array.isArray(caps?.models) ? caps.models : [];
  const modelIds = models.map((m) => m.id).filter(Boolean);
  const fallbackId = modelIds[0] || FALLBACK_CAPABILITIES.default;
  if (typeof caps?.default === "string" && modelIds.includes(caps.default)) {
    return caps.default;
  }
  return fallbackId;
}

function isModelAvailable(caps, modelId) {
  const models = Array.isArray(caps?.models) ? caps.models : [];
  return models.some((m) => m?.id === modelId);
}

export function useCapabilitiesQuery() {
  const hasUserSelectedModel = useRef(false);
  const [model, setModelState] = useState(FALLBACK_CAPABILITIES.default);

  const capabilitiesQuery = useQuery({
    queryKey: ["capabilities"],
    queryFn: fetchCapabilities,
    retry: 0,
  });

  const caps = capabilitiesQuery.data || FALLBACK_CAPABILITIES;

  const stableModel = useMemo(() => {
    if (!hasUserSelectedModel.current) {
      return normalizeModelChoice(caps);
    }
    if (isModelAvailable(caps, model)) {
      return model;
    }
    return normalizeModelChoice(caps);
  }, [caps, model]);

  useEffect(() => {
    if (stableModel !== model) {
      setModelState(stableModel);
    }
  }, [model, stableModel]);

  const models = caps.models.map((m) => m.id);
  const currentModelCaps = caps.models.find((m) => m.id === stableModel)?.capabilities ?? {};

  const setModel = useCallback((nextModel) => {
    hasUserSelectedModel.current = true;
    setModelState(nextModel);
  }, []);

  return {
    model: stableModel,
    models,
    setModel,
    supportsThinking: Boolean(currentModelCaps.thinking),
    supportsMedia: Boolean(currentModelCaps.media),
  };
}
