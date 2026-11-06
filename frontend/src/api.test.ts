import { afterEach, expect, test, vi } from "vitest";
import { approveRun, createDraft, getConversation, listRuns, rejectRun } from "./api";
import { ApiError } from "./types";

function respond(status: number, body: unknown): void {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(text, { status })));
}

function lastCall(): { url: string; init: RequestInit } {
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  return { url: String(url), init: init ?? {} };
}

afterEach(() => vi.unstubAllGlobals());

test("GET returns the parsed JSON", async () => {
  respond(200, { conversation: { id: "conv_priya" } });
  const detail = await getConversation("conv_priya");
  expect(detail.conversation.id).toBe("conv_priya");
  expect(lastCall().url).toBe("/api/conversations/conv_priya");
  expect(lastCall().init.method).toBe("GET");
});

test("createDraft POSTs instructions as JSON, and an empty body without them", async () => {
  respond(201, { id: "r1" });
  await createDraft("conv_priya", "Keep it short");
  expect(lastCall().init.body).toBe(JSON.stringify({ instructions: "Keep it short" }));
  expect(lastCall().url).toBe("/api/conversations/conv_priya/drafts");

  respond(201, { id: "r2" });
  await createDraft("conv_priya");
  expect(lastCall().init.body).toBe("{}");
});

test("approve sends edited_text only when given; reject sends the reason", async () => {
  respond(200, { id: "r1" });
  await approveRun("r1", "My text");
  expect(lastCall().init.body).toBe(JSON.stringify({ edited_text: "My text" }));

  respond(200, { id: "r1" });
  await approveRun("r1");
  expect(lastCall().init.body).toBe("{}");

  respond(200, { id: "r1" });
  await rejectRun("r1", "too formal");
  expect(lastCall().url).toBe("/api/runs/r1/reject");
  expect(lastCall().init.body).toBe(JSON.stringify({ reason: "too formal" }));
});

test("listRuns adds the conversation filter, URL-encoded", async () => {
  respond(200, []);
  await listRuns("conv a&b");
  expect(lastCall().url).toBe("/api/runs?conversation_id=conv%20a%26b");
});

test("an error envelope becomes an ApiError with code, message and status", async () => {
  respond(409, { error: { code: "invalid_transition", message: "Cannot move a run" } });
  const error = await approveRun("r1").catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({
    code: "invalid_transition",
    message: "Cannot move a run",
    status: 409,
  });
});

test("a non-JSON error response still becomes an ApiError", async () => {
  respond(502, "<html>Bad gateway</html>");
  await expect(listRuns()).rejects.toMatchObject({ code: "http_error", status: 502 });
});

test("an unreachable server becomes a network_error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  await expect(listRuns()).rejects.toMatchObject({ code: "network_error", status: 0 });
});
