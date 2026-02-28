import { useCallback, useEffect, useRef, useState } from "react";
import { FALLBACK_CAPABILITIES } from "../utils/models";

export function useCapabilities() {
  const [capabilities, setCapabilities] = useState(null);
  const [model, setModelState] = useState(FALLBACK_CAPABILITIES.default);
  const hasUserSelectedModel = useRef(false);

  useEffect(() => {
    let cancelled = false;

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

    fetch("/api/capabilities")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("fetch failed"))))
      .then((data) => {
        if (cancelled) return;
        setCapabilities(data);
        setModelState((currentModel) => {
          if (!hasUserSelectedModel.current) {
            return normalizeModelChoice(data);
          }
          if (isModelAvailable(data, currentModel)) {
            return currentModel;
          }
          return normalizeModelChoice(data);
        });
      })
      .catch(() => {
        if (cancelled) return;
        setCapabilities(FALLBACK_CAPABILITIES);
        setModelState((currentModel) => {
          if (!hasUserSelectedModel.current) {
            return normalizeModelChoice(FALLBACK_CAPABILITIES);
          }
          if (isModelAvailable(FALLBACK_CAPABILITIES, currentModel)) {
            return currentModel;
          }
          return normalizeModelChoice(FALLBACK_CAPABILITIES);
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const caps = capabilities || FALLBACK_CAPABILITIES;
  const models = caps.models.map((m) => m.id);
  const currentModelCaps = caps.models.find((m) => m.id === model)?.capabilities ?? {};
  const supportsThinking = Boolean(currentModelCaps.thinking);
  const supportsMedia = Boolean(currentModelCaps.media);

  const setModel = useCallback((nextModel) => {
    hasUserSelectedModel.current = true;
    setModelState(nextModel);
  }, []);

  return { models, model, setModel, supportsThinking, supportsMedia };
}
