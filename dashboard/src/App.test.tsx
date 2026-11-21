import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { activity, makeClaim, makeDecision, mockApi } from "../tests/fixtures";
import { App } from "./App";
import type { Status } from "./types";

const queueButton = () => screen.getByRole("button", { name: /CLM-1001/ });

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("shows the queue, every status and full claim context", async () => {
  const states: Status[] = [
    "waiting",
    "in_progress",
    "waiting_for_sign_off",
    "decided",
  ];
  mockApi(
    states.map((status, index) =>
      makeClaim({ claim_id: `CLM-${String(1001 + index)}`, status }),
    ),
  );
  render(<App />);
  expect(screen.getByText("Loading claims…")).toBeDefined();
  expect(await screen.findByRole("button", { name: /CLM-1001/ })).toBeDefined();
  expect(
    await screen.findByText(
      "Our flight was delayed overnight because of a crew problem.",
    ),
  ).toBeDefined();
  expect(screen.getAllByText("$1,250.00").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByText("Carrier report", { selector: "summary" }));
  expect(screen.getByText("Departure was delayed eight hours.")).toBeDefined();
  fireEvent.click(await screen.findByText("Customer and claim history"));
  expect(screen.getByText("alex@example.test")).toBeDefined();
  expect(screen.getByText("$35.50")).toBeDefined();
  fireEvent.click(screen.getByText("Policy and travelers"));
  expect(screen.getByText("Yes")).toBeDefined();
  fireEvent.click(screen.getByText("Plan limits and add-ons"));
  expect(screen.getByText("$1,500.00")).toBeDefined();
  expect(screen.getAllByText("None").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: /CLM-1002/ }));
  expect(
    await screen.findByText("CLM-1002", { selector: ".eyebrow" }),
  ).toBeDefined();
});

it("shows read-only instructions and returns to the queue", async () => {
  mockApi();
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Agent instructions" }));
  expect(screen.getByText("Loading instructions…")).toBeDefined();
  expect(
    await screen.findByText("Read the wording. Explain your decision."),
  ).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Claims" }));
  expect(await screen.findByRole("button", { name: /CLM-1001/ })).toBeDefined();
});

it("shows an empty queue", async () => {
  mockApi([]);
  render(<App />);
  expect(
    await screen.findByText("There are no claims in the queue."),
  ).toBeDefined();
});

it("shows a network failure and retries", async () => {
  const api = mockApi();
  api.fetcher.mockRejectedValueOnce(new Error("Network unavailable"));
  render(<App />);
  expect(await screen.findByRole("alert")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("button", { name: /CLM-1001/ })).toBeDefined();
});

it("refreshes the queue and events and stops polling on navigation", async () => {
  vi.useFakeTimers();
  const api = mockApi();
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(queueButton()).toBeDefined();
  api.routes.set("/api/claims/CLM-1001/events", [
    ...activity,
    {
      id: 2,
      type: "tool_call",
      content: "Reading policy wording",
      created_at: "2026-06-20T10:01:00Z",
    },
  ]);
  api.routes.set("/api/claims", [makeClaim({ status: "in_progress" })]);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(screen.getByText("Reading policy wording")).toBeDefined();
  expect(within(queueButton()).getByText("In progress")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Agent instructions" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  api.fetcher.mockClear();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(6000);
  });
  expect(api.fetcher).not.toHaveBeenCalled();
});

it.each(["decline", "refer"] as const)(
  "shows a %s decision without a payment action",
  async (outcome) => {
    mockApi([
      makeClaim({
        status: "decided",
        decision: makeDecision({ outcome, amount: "0.00" }),
        documents: [],
      }),
    ]);
    render(<App />);
    expect(await screen.findByText("Agent decision")).toBeDefined();
    expect(screen.getByText("No documents provided.")).toBeDefined();
    expect(
      screen.queryByRole("button", { name: "Authorize and pay" }),
    ).toBeNull();
    expect(screen.getByText("3. Trip Delay")).toBeDefined();
  },
);

it("shows completed payments and sign-off details", async () => {
  mockApi([
    makeClaim({
      status: "decided",
      decision: makeDecision({
        paid_amount: "1250.00",
        paid_at: "2026-06-20T10:00:00Z",
        handler_id: "HND-01",
        signed_at: "2026-06-20T09:59:00Z",
      }),
    }),
  ]);
  render(<App />);
  expect(await screen.findByText(/Payment recorded/)).toBeDefined();
  expect(screen.getByText(/Authorized by HND-01/)).toBeDefined();
});

it("shows claim, context, activity and instructions errors", async () => {
  const api = mockApi();
  for (const path of [
    "/api/claims/CLM-1001",
    "/api/claims/CLM-1001/context",
    "/api/claims/CLM-1001/events",
    "/api/agent/instructions",
  ]) {
    api.failures.set(path, {
      status: 503,
      body: { detail: `Unavailable: ${path}` },
    });
  }
  render(<App />);
  expect(
    await screen.findByText("Unavailable: /api/claims/CLM-1001"),
  ).toBeDefined();
  api.failures.delete("/api/claims/CLM-1001");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(
    await screen.findByText("Unavailable: /api/claims/CLM-1001/events"),
  ).toBeDefined();
  expect(
    await screen.findByText("Unavailable: /api/claims/CLM-1001/context"),
  ).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Agent instructions" }));
  expect(
    await screen.findByText("Unavailable: /api/agent/instructions"),
  ).toBeDefined();
});

it("shows no activity before the agent starts", async () => {
  const api = mockApi();
  api.routes.set("/api/claims/CLM-1001/events", []);
  render(<App />);
  expect(
    await screen.findByText("The agent has not started this claim."),
  ).toBeDefined();
});

it("keeps payment pending until the API confirms it", async () => {
  const api = mockApi([
    makeClaim({ status: "waiting_for_sign_off", decision: makeDecision() }),
  ]);
  const original = api.fetcher.getMockImplementation();
  let finish: ((value: Response) => void) | undefined;
  api.fetcher.mockImplementation((path, init) =>
    path.endsWith("/pay")
      ? new Promise<Response>((resolve) => {
          finish = resolve;
        })
      : (original?.(path, init) ??
        Promise.reject(new Error("No mock response"))),
  );
  render(<App />);
  const select = await screen.findByRole("combobox");
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(select, { target: { value: "HND-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Authorize and pay" }));
  await waitFor(() => {
    expect(finish).toBeDefined();
  });
  expect(
    screen
      .getByRole("button", { name: "Recording payment…" })
      .hasAttribute("disabled"),
  ).toBe(true);
  expect(screen.queryByText(/Payment recorded/)).toBeNull();
  act(() => {
    finish?.(new Response("{}"));
  });
  expect(await screen.findByText(/Payment recorded/)).toBeDefined();
});
