let idSeed = 0;

export function nextId(prefix = "id") {
  idSeed += 1;
  return `${prefix}-${idSeed}`;
}

export function resetIdSeed() {
  idSeed = 0;
}

export function nextRequestId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return nextId("req");
}
