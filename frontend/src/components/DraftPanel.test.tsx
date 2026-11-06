import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { makeRun, makeStep } from "../testData";
import type { AgentRun } from "../types";
import { DraftPanel } from "./DraftPanel";

function mockFetch(...responses: Array<{ status: number; body: unknown }>): void {
  const fn = vi.fn();
  for (const r of responses) {
    fn.mockResolvedValueOnce(new Response(JSON.stringify(r.body), { status: r.status }));
  }
  vi.stubGlobal("fetch", fn);
}

afterEach(() => vi.unstubAllGlobals());

test("awaiting_approval run shows the editable draft, the actions and the trace", () => {
  vi.stubGlobal("fetch", vi.fn());
  render(<DraftPanel run={makeRun()} onChange={() => {}} />);

  expect(screen.getByTestId("run-status")).toHaveTextContent("awaiting approval");
  expect(screen.getByRole("textbox", { name: /draft/i })).toHaveValue(
    "Hi Priya, your interview is on 2026-11-12.",
  );
  expect(screen.getByTestId("approve-button")).toBeEnabled();
  expect(screen.getByRole("button", { name: "Reject" })).toBeEnabled();
  expect(screen.getAllByTestId("trace-step")).toHaveLength(3);
  expect(screen.queryByTestId("degraded-banner")).not.toBeInTheDocument();
});

test("a run with error steps shows the warning banner and marks the error steps", () => {
  const run = makeRun({
    steps: [
      makeStep({ type: "error", error: "tool_unavailable: down, retrying" }),
      makeStep({ index: 1, type: "error", error: "tool_unavailable: down" }),
    ],
  });
  render(<DraftPanel run={run} onChange={() => {}} />);

  expect(screen.getByTestId("degraded-banner")).toHaveTextContent(
    "Some data was unavailable; the draft avoids relying on it.",
  );
  const steps = screen.getAllByTestId("trace-step");
  expect(steps).toHaveLength(2);
  expect(steps[0]).toHaveClass("step-error");
});

test("a failed run shows the error and no approve button or banner", () => {
  const run = makeRun({
    status: "failed",
    draft_text: null,
    error: "draft contains a placeholder",
    steps: [makeStep({ type: "error", error: "guardrail_violation: placeholder" })],
  });
  render(<DraftPanel run={run} onChange={() => {}} />);

  expect(screen.getByRole("alert")).toHaveTextContent("draft contains a placeholder");
  expect(screen.queryByTestId("approve-button")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  expect(screen.queryByTestId("degraded-banner")).not.toBeInTheDocument();
});

test("rejecting with a too-short reason does not call the API", () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<DraftPanel run={makeRun()} onChange={() => {}} />);

  fireEvent.change(screen.getByLabelText(/rejection reason/i), { target: { value: " ab " } });
  fireEvent.click(screen.getByRole("button", { name: "Reject" }));

  expect(screen.getByRole("alert")).toHaveTextContent("at least 3 characters");
  expect(fetchMock).not.toHaveBeenCalled();
});

test("approving unchanged text sends no edit; edited text is sent", async () => {
  const approved: AgentRun = makeRun({ status: "approved", final_text: "x" });
  mockFetch({ status: 200, body: approved }, { status: 200, body: approved });
  const onChange = vi.fn();
  render(<DraftPanel run={makeRun()} onChange={onChange} />);

  fireEvent.click(screen.getByTestId("approve-button"));
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
  expect(vi.mocked(fetch).mock.calls[0][1]?.body).toBe("{}");

  fireEvent.change(screen.getByRole("textbox", { name: /draft/i }), {
    target: { value: "  My own words " },
  });
  fireEvent.click(screen.getByTestId("approve-button"));
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(2));
  expect(vi.mocked(fetch).mock.calls[1][1]?.body).toBe(JSON.stringify({ edited_text: "My own words" }));
});

test("a 409 shows the API message and refreshes the run", async () => {
  const rejectedElsewhere = makeRun({ status: "rejected", rejection_reason: "too long" });
  mockFetch(
    { status: 409, body: { error: { code: "invalid_transition", message: "Cannot move a run" } } },
    { status: 200, body: rejectedElsewhere },
  );
  const onChange = vi.fn();
  render(<DraftPanel run={makeRun()} onChange={onChange} />);

  fireEvent.click(screen.getByTestId("approve-button"));

  expect(await screen.findByRole("alert")).toHaveTextContent("Cannot move a run");
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(rejectedElsewhere));
  expect(vi.mocked(fetch).mock.calls[1][0]).toBe("/api/runs/run1");
});

test("approved and rejected runs show their outcome", () => {
  const { rerender } = render(
    <DraftPanel run={makeRun({ status: "approved", final_text: "Final words" })} onChange={() => {}} />,
  );
  expect(screen.getByText("Approved - ready to send")).toBeInTheDocument();
  expect(screen.getByText("Final words")).toBeInTheDocument();
  expect(screen.queryByTestId("approve-button")).not.toBeInTheDocument();

  rerender(
    <DraftPanel run={makeRun({ status: "rejected", rejection_reason: "too formal" })} onChange={() => {}} />,
  );
  expect(screen.getByText(/too formal/)).toBeInTheDocument();
});
