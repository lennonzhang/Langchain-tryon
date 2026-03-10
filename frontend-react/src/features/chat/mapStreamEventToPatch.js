function formatUsageLine(usage) {
  const phase = usage.phase || "unknown";
  const used = Number(usage.used_estimated_tokens || 0);
  const total = Number(usage.window_total_tokens || 0);
  const ratio = Number(usage.usage_ratio || 0);
  const pct = (ratio * 100).toFixed(2);
  const model = usage.model ? ` - ${usage.model}` : "";
  return `[${phase}] ${used}/${total} tokens (${pct}%)${model}`;
}

const MARKDOWN_BLOCK_START_RE = /^(?:\*{4,}|#{1,6}\s|[-+*]\s|\d+\.\s|>\s|```)/;
const LEADING_PUNCT_RE = /^[,.;:!?)}\]]/;
const LETTER_OR_NUMBER_RE = /[\p{L}\p{N}]/u;
const CJK_CHAR_RE = /[\u3400-\u9FFF]/;
const REASONING_STEP_KEYWORDS = [
  "Planning",
  "Assessing",
  "Reporting",
  "Summarizing",
  "Confirming",
  "Verifying",
  "Evaluating",
  "Checking",
  "Reviewing",
];
const STEP_KEYWORD_STICKY_PATTERN = new RegExp(`(\\S)(${REASONING_STEP_KEYWORDS.join("|")})\\b`, "g");

function looksLikeNewReasoningStep(text) {
  const normalized = String(text || "").trim();
  if (!normalized) return false;
  if (!/^[A-Z]/.test(normalized)) return false;
  // Usually step-like chunks contain multiple words (e.g. "Planning ...").
  return /\S+\s+\S+/.test(normalized);
}

function normalizeReasoningChunkForDisplay(nextChunkRaw) {
  const nextChunk = String(nextChunkRaw || "");
  if (!nextChunk) return "";

  // Split sticky markdown block starts inside a single chunk:
  // "...limitations****Confirming..." -> "...limitations\n\n****Confirming..."
  let normalized = nextChunk.replace(/(\S)(\*{4,}(?=[A-Za-z#\-\d>`]))/g, "$1\n\n$2");

  // Split sticky step keywords inside one chunk:
  // "...stepsPlanning..." -> "...steps\n\nPlanning..."
  normalized = normalized.replace(STEP_KEYWORD_STICKY_PATTERN, (match, lead, keyword) => {
    if (lead === "*") return match;
    if (/[([{<"'`]/.test(lead)) return match;
    return `${lead}\n\n${keyword}`;
  });

  return normalized;
}

function withStepBreak(reasoningText) {
  if (!reasoningText) return reasoningText;
  if (/\n\s*\n\s*$/.test(reasoningText)) return reasoningText;
  return `${reasoningText.trimEnd()}\n\n`;
}

export function mergeReasoningChunk(prevRaw, nextRaw) {
  const prev = prevRaw || "";
  const next = nextRaw || "";

  if (!prev) return next;
  if (!next) return prev;

  if (/^\s/.test(next)) {
    return prev + next;
  }

  if (MARKDOWN_BLOCK_START_RE.test(next) && !/\n\s*$/.test(prev)) {
    return `${prev}\n\n${next}`;
  }

  const prevTrimmed = prev.trimEnd();
  if (
    looksLikeNewReasoningStep(next) &&
    /\S+\s+\S+/.test(prevTrimmed) &&
    !/[.!?;:]\s*$/.test(prevTrimmed) &&
    !/\n\s*$/.test(prevTrimmed)
  ) {
    return `${prevTrimmed}\n\n${next}`;
  }

  if (LEADING_PUNCT_RE.test(next)) {
    return prev + next;
  }

  const prevChar = prev.at(-1) || "";
  const nextChar = next[0] || "";
  if (CJK_CHAR_RE.test(prevChar) && CJK_CHAR_RE.test(nextChar)) {
    return prev + next;
  }
  if (LETTER_OR_NUMBER_RE.test(prevChar) && LETTER_OR_NUMBER_RE.test(nextChar)) {
    return `${prev} ${next}`;
  }

  return prev + next;
}

export function mapStreamEventToPatch(message, event) {
  if (!message || message.role !== "assistant_stream") {
    return message;
  }

  if (event.type === "search_start") {
    return {
      ...message,
      search: { state: "loading", query: event.query || "", results: [], error: "" },
    };
  }

  if (event.type === "search_done") {
    return {
      ...message,
      search: {
        state: "done",
        query: message.search.query,
        results: Array.isArray(event.results) ? event.results : [],
        error: "",
      },
    };
  }

  if (event.type === "search_error") {
    return {
      ...message,
      search: {
        state: "error",
        query: message.search.query,
        results: [],
        error: event.error || "",
      },
    };
  }

  if (event.type === "context_usage") {
    const usage = event.usage || {};
    const line = formatUsageLine(usage);
    if (usage.phase === "final") {
      return {
        ...message,
        usageLines: [line],
      };
    }
    return {
      ...message,
      usageLines: [...message.usageLines, line],
    };
  }

  if (event.type === "agent_step_start") {
    const nextStep = Number(event.step || 0);
    const prevStep = Number(message.reasoningStepCursor || 0);
    const hasReasoning = Boolean((message.reasoning || "").trim());
    const isForwardStep = Number.isFinite(nextStep) && nextStep > prevStep;
    const shouldBreak = hasReasoning && isForwardStep;

    return {
      ...message,
      reasoningStepCursor: isForwardStep ? nextStep : prevStep,
      reasoningNeedsStepBreak: Boolean(message.reasoningNeedsStepBreak || shouldBreak),
    };
  }

  if (event.type === "reasoning") {
    const normalizedChunk = normalizeReasoningChunkForDisplay(event.content);
    const baseReasoning = message.reasoningNeedsStepBreak
      ? withStepBreak(message.reasoning)
      : message.reasoning;

    return {
      ...message,
      reasoning: mergeReasoningChunk(baseReasoning, normalizedChunk),
      reasoningNeedsStepBreak: false,
    };
  }

  if (event.type === "token") {
    const answer = `${message.answer === "Thinking..." ? "" : message.answer}${event.content || ""}`;
    return {
      ...message,
      answer: answer || "Thinking...",
    };
  }

  if (event.type === "user_input_required") {
    const question = String(event.question || "").trim() || "Please provide the missing information.";
    const rawOptions = Array.isArray(event.options) ? event.options : [];
    const options = rawOptions
      .filter((option) => option && typeof option === "object" && String(option.label || "").trim())
      .slice(0, 3)
      .map((option, index) => ({
        id: String(option.id || `option-${index + 1}`),
        label: String(option.label || "").trim(),
        description: String(option.description || "").trim(),
      }));

    return {
      ...message,
      clarification: {
        question,
        options,
        allowFreeText: event.allow_free_text !== false,
        answered: false,
      },
      answer: question,
    };
  }

  if (event.type === "error") {
    return {
      ...message,
      status: "failed",
      answer: `Error: ${event.error || "Streaming request failed"}`,
    };
  }

  if (event.type === "done") {
    if (message.status === "failed") {
      return {
        ...message,
        status: "failed",
        finishReason: event.finish_reason || message.finishReason || "error",
      };
    }

    const normalizedAnswer = !message.answer || message.answer === "Thinking..." ? "(empty response)" : message.answer;

    return {
      ...message,
      status: "done",
      finishReason: event.finish_reason || message.finishReason || null,
      answer: normalizedAnswer,
    };
  }

  return message;
}
