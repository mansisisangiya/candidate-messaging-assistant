import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { makeRun } from "../testData";
import type { ConversationDetail } from "../types";
import { ConversationView } from "./ConversationView";

const detail: ConversationDetail = {
  conversation: {
    id: "conv_priya",
    candidate_id: "cand_priya",
    messages: [{ sender: "candidate", text: "When is my interview?", sent_at: "2026-11-05T08:15:00Z" }],
  },
  candidate: { id: "cand_priya", name: "Priya Sharma", email: "p@example.com", job_id: "j", stage: "interview" },
  job: { id: "j", title: "Senior Backend Engineer", team: "Platform", location: "Remote" },
  latest_run: null,
};

afterEach(() => vi.unstubAllGlobals());

test("shows the transcript and candidate info", () => {
  render(<ConversationView detail={detail} onDrafted={() => {}} />);
  expect(screen.getByText("Priya Sharma")).toBeInTheDocument();
  expect(screen.getByText(/When is my interview\?/)).toBeInTheDocument();
  expect(screen.getByText(/Senior Backend Engineer/)).toBeInTheDocument();
});

test("the draft button is disabled while the request is pending", async () => {
  let finish: (r: Response) => void = () => {};
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((resolve) => (finish = resolve))));
  const onDrafted = vi.fn();
  render(<ConversationView detail={detail} onDrafted={onDrafted} />);

  fireEvent.click(screen.getByTestId("draft-button"));
  expect(await screen.findByRole("button", { name: "Drafting…" })).toBeDisabled();

  finish(new Response(JSON.stringify(makeRun()), { status: 201 }));
  await waitFor(() => expect(onDrafted).toHaveBeenCalled());
  expect(screen.getByTestId("draft-button")).toBeEnabled();
});

test("an API error is shown in an alert", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "validation_error", message: "too long" } }), { status: 422 }),
    ),
  );
  render(<ConversationView detail={detail} onDrafted={() => {}} />);
  fireEvent.click(screen.getByTestId("draft-button"));
  expect(await screen.findByRole("alert")).toHaveTextContent("too long");
});

test("instructions are limited to 500 characters", () => {
  render(<ConversationView detail={detail} onDrafted={() => {}} />);
  expect(screen.getByLabelText(/instructions/i)).toHaveAttribute("maxlength", "500");
});
