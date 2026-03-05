import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useState } from "react";

function QueryProbe() {
  const [keySuffix, setKeySuffix] = useState("a");
  const query = useQuery({
    queryKey: ["session", keySuffix],
    queryFn: async () => `session-${keySuffix}`,
    enabled: false,
  });

  return (
    <div>
      <div data-testid="query-data">{query.data === undefined ? "undefined" : String(query.data)}</div>
      <div data-testid="query-loading">{String(query.isLoading)}</div>
      <button type="button" onClick={() => setKeySuffix("b")}>
        Switch key
      </button>
    </div>
  );
}

describe("react-query lite behavior", () => {
  it("resets local state on queryKey change when query is disabled", async () => {
    const client = new QueryClient();
    client.setQueryData(["session", "a"], "session-a");

    render(
      <QueryClientProvider client={client}>
        <QueryProbe />
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("query-data")).toHaveTextContent("session-a");
    expect(screen.getByTestId("query-loading")).toHaveTextContent("false");

    await userEvent.click(screen.getByRole("button", { name: "Switch key" }));

    expect(screen.getByTestId("query-data")).toHaveTextContent("undefined");
    expect(screen.getByTestId("query-loading")).toHaveTextContent("false");
  });
});
