import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { makeClaim, makeDecision, mockApi } from "../tests/fixtures";
import { Payment } from "./Payment";

const pending = () =>
  makeClaim({ status: "waiting_for_sign_off", decision: makeDecision() });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("requires a handler and records sign-off before payment", async () => {
  const api = mockApi();
  const refresh = vi.fn();
  render(<Payment claim={pending()} refresh={refresh} />);
  expect(
    screen
      .getByRole("button", { name: "Authorize and pay" })
      .hasAttribute("disabled"),
  ).toBe(true);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Authorize and pay" }));
  expect(await screen.findByText(/Payment recorded/)).toBeDefined();
  const writes = api.fetcher.mock.calls.filter(
    ([, init]) => init?.method === "POST",
  );
  expect(writes.map(([path]) => path)).toEqual([
    "/api/claims/CLM-1001/sign-off",
    "/api/claims/CLM-1001/pay",
  ]);
  expect(writes[1][1]?.body).toBe(JSON.stringify({ amount: "1250.00" }));
  expect(refresh).toHaveBeenCalledOnce();
});

it("retries a failed payment without repeating sign-off", async () => {
  const api = mockApi();
  api.failures.set("POST /api/claims/CLM-1001/pay", {
    status: 503,
    body: { detail: "Payment unavailable" },
  });
  render(<Payment claim={pending()} refresh={vi.fn()} />);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Authorize and pay" }));
  expect(await screen.findByRole("alert")).toBeDefined();
  expect(screen.getByText("Payment ready")).toBeDefined();
  api.failures.clear();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText(/Payment recorded/)).toBeDefined();
  expect(
    api.fetcher.mock.calls.filter(([path]) => path.endsWith("/sign-off")),
  ).toHaveLength(1);
});

it("shows a failed sign-off and allows retry", async () => {
  const api = mockApi();
  api.failures.set("POST /api/claims/CLM-1001/sign-off", {
    status: 409,
    body: { detail: "Sign-off unavailable" },
  });
  render(<Payment claim={pending()} refresh={vi.fn()} />);
  await screen.findByRole("option", { name: "Dana Whitfield" });
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "HND-01" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Authorize and pay" }));
  expect(await screen.findByText("Sign-off unavailable")).toBeDefined();
  expect(
    api.fetcher.mock.calls.filter(([path]) => path.endsWith("/pay")),
  ).toHaveLength(0);
  api.failures.clear();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText(/Payment recorded/)).toBeDefined();
});

it("retries handler loading and skips sign-off for an already authorized decision", async () => {
  const api = mockApi();
  api.failures.set("/api/handlers", { status: 503, body: {} });
  const view = render(<Payment claim={pending()} refresh={vi.fn()} />);
  expect(await screen.findByText("Request failed (503).")).toBeDefined();
  api.failures.clear();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(
    await screen.findByRole("option", { name: "Dana Whitfield" }),
  ).toBeDefined();
  view.rerender(
    <Payment
      claim={makeClaim({
        status: "waiting_for_sign_off",
        decision: makeDecision({ handler_id: "HND-01" }),
      })}
      refresh={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Record payment" }));
  await waitFor(() => {
    expect(screen.getByText(/Payment recorded/)).toBeDefined();
  });
  expect(
    api.fetcher.mock.calls.filter(([path]) => path.endsWith("/sign-off")),
  ).toHaveLength(0);
});
