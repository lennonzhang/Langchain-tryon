let prismPromise = null;

export function ensurePrismLoaded() {
  if (typeof window !== "undefined" && window.Prism) {
    return Promise.resolve();
  }

  if (!prismPromise) {
    prismPromise = import("./prism-setup")
      .then((mod) => {
        if (typeof window !== "undefined" && !window.Prism && mod?.default) {
          window.Prism = mod.default;
        }
      })
      .catch((error) => {
        prismPromise = null;
        throw error;
      });
  }

  return prismPromise;
}
