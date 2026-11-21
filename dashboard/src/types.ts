export type Money = string | number;
export type Status =
  "waiting" | "in_progress" | "waiting_for_sign_off" | "decided";
export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export type RecordData = Record<string, Json>;
export interface Decision {
  outcome: "approve" | "decline" | "refer";
  amount: string;
  calculation: string;
  explanation: string;
  policy_section: string;
  handler_id: string | null;
  signed_at: string | null;
  paid_amount: string | null;
  paid_at: string | null;
}
export interface Claim {
  claim_id: string;
  customer_id: string;
  customer_name?: string;
  policy_id: string;
  claim_type: string;
  summary: string;
  story: string;
  submitted_on: string;
  incident_date: string;
  incident_location: string;
  amount_claimed: Money;
  status: Status;
  decision: Decision | null;
  items: { description: string; category: string; amount: Money }[];
  documents: { name: string; type: string; content: string }[];
}
export interface Context {
  customer: RecordData;
  policy: RecordData;
  plan: RecordData;
  add_ons: RecordData[];
  deductible_applies_to: string[];
}
export interface Activity {
  id: number;
  type: string;
  content: string;
  created_at: string;
}
export interface Handler {
  handler_id: string;
  name: string;
  can_approve_over_limit: boolean;
}
export const statuses: Record<Status, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_sign_off: "Waiting for sign-off",
  decided: "Decided",
};
