import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

afterEach(() => vi.unstubAllGlobals());

test("lists conversations from the API and prompts for a selection", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            id: "conv_priya",
            candidate_name: "Priya Sharma",
            job_title: "Senior Backend Engineer",
            last_message_preview: "Thanks!",
            latest_run_status: "approved",
          },
        ]),
        { status: 200 },
      ),
    ),
  );
  render(<App />);

  expect(screen.getByRole("heading", { name: /candidate messaging assistant/i })).toBeInTheDocument();
  expect(await screen.findByText("Priya Sharma")).toBeInTheDocument();
  expect(screen.getByTestId("status-badge")).toHaveTextContent("approved");
  expect(screen.getByText("Select a conversation.")).toBeInTheDocument();
});

test("a failing list request shows an alert", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server");
});
