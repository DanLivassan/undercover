import { vi } from "vitest";
import type { Activity, Claim, Context, Decision } from "../src/types";

export function makeDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    outcome: "approve",
    amount: "1250.00",
    calculation: "$1,500 less $250 reimbursement = $1,250.",
    explanation:
      "The delay is covered by the policy. The documented expenses are eligible.",
    policy_section: "3. Trip Delay",
    handler_id: null,
    signed_at: null,
    paid_amount: null,
    paid_at: null,
    ...overrides,
  };
}

export function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    claim_id: "CLM-1001",
    customer_id: "CUS-1",
    customer_name: "Alex Morgan",
    policy_id: "POL-1",
    claim_type: "trip_delay",
    summary: "Overnight flight delay",
    story: "Our flight was delayed overnight because of a crew problem.",
    submitted_on: "2026-06-20",
    incident_date: "2026-06-18",
    incident_location: "Rome, Italy",
    amount_claimed: "1250.00",
    status: "waiting",
    decision: null,
    items: [
      {
        description: "Airport hotel",
        category: "accommodation",
        amount: "1250.00",
      },
    ],
    documents: [
      {
        name: "Carrier report",
        type: "carrier_report",
        content: "Departure was delayed eight hours.",
      },
    ],
    ...overrides,
  };
}

export const context: Context = {
  customer: {
    name: "Alex Morgan",
    email: "alex@example.test",
    address: { city: "Boston" },
    previous_claims: [{ claim_id: "CLM-OLD", amount_paid: "35.50" }],
  },
  policy: {
    policy_id: "POL-1",
    plan: "premium",
    travelers: ["Alex Morgan"],
    active: true,
    note: null,
  },
  plan: { name: "Premium", trip_delay_max: "1500.00", deductible: "50.00" },
  add_ons: [],
  deductible_applies_to: ["baggage", "emergency_medical"],
};
export const activity: Activity[] = [
  {
    id: 1,
    type: "started",
    content: "Agent started reviewing the claim.",
    created_at: "2026-06-20T10:00:00Z",
  },
];

export function mockApi(claims: Claim[] = [makeClaim()]) {
  const failures = new Map<string, { status: number; body: unknown }>();
  const routes = new Map<string, unknown>([
    ["/api/claims", claims],
    [
      "/api/agent/instructions",
      { text: "Read the wording. Explain your decision." },
    ],
    [
      "/api/handlers",
      [
        {
          handler_id: "HND-01",
          name: "Dana Whitfield",
          can_approve_over_limit: true,
        },
      ],
    ],
  ]);
  for (const claim of claims) {
    routes.set(`/api/claims/${claim.claim_id}`, claim);
    routes.set(`/api/claims/${claim.claim_id}/context`, context);
    routes.set(`/api/claims/${claim.claim_id}/events`, activity);
  }
  const fetcher = vi.fn((path: string, init?: RequestInit) => {
    const key = init?.method === "POST" ? `POST ${path}` : path;
    const failure = failures.get(key);
    if (failure)
      return Promise.resolve(
        new Response(JSON.stringify(failure.body), { status: failure.status }),
      );
    if (init?.method === "POST") return Promise.resolve(new Response("{}"));
    return Promise.resolve(new Response(JSON.stringify(routes.get(path))));
  });
  vi.stubGlobal("fetch", fetcher);
  return { fetcher, failures, routes };
}
