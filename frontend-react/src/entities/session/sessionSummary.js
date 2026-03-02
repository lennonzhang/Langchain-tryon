export function buildSessionTitle(input) {
  const cleaned = String(input || "")
    .replace(/[#>*`_\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (!cleaned) {
    return "New Chat";
  }

  if (cleaned.length <= 30) {
    return cleaned;
  }

  return `${cleaned.slice(0, 30)}...`;
}

export function buildMessagePreview(input) {
  const cleaned = String(input || "").replace(/\s+/g, " ").trim();
  if (!cleaned) {
    return "";
  }
  return cleaned.length > 80 ? `${cleaned.slice(0, 80)}...` : cleaned;
}
