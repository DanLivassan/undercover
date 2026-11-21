import { useState } from "react";
import { post, useResource } from "./api";
import { ErrorNotice } from "./components";
import { money } from "./format";
import type { Claim, Decision, Handler } from "./types";

type Props = Readonly<{ claim: Claim; refresh: () => void }>;

function Recorded({ amount }: Readonly<{ amount: string }>) {
  return (
    <p className="paid" role="status">
      Payment recorded · {money(amount)}
      <span>Simulated payment</span>
    </p>
  );
}

function HandlerSelect({
  value,
  busy,
  change,
}: Readonly<{
  value: string;
  busy: boolean;
  change: (value: string) => void;
}>) {
  const handlers = useResource<Handler[]>("/api/handlers", null, false);
  return (
    <>
      <label>
        Handler
        <select
          value={value}
          onChange={(event) => {
            change(event.target.value);
          }}
          disabled={busy}
        >
          <option value="">Select a handler</option>
          {handlers.data
            ?.filter((person) => person.can_approve_over_limit)
            .map((person) => (
              <option key={person.handler_id} value={person.handler_id}>
                {person.name}
              </option>
            ))}
        </select>
      </label>
      {handlers.error && (
        <ErrorNotice message={handlers.error} retry={handlers.reload} />
      )}
    </>
  );
}

function PaymentForm({
  claim,
  decision,
  refresh,
}: Props & Readonly<{ decision: Decision }>) {
  const [handler, setHandler] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [paid, setPaid] = useState(false);
  const needsSignOff =
    claim.status === "waiting_for_sign_off" &&
    !decision.handler_id &&
    !authorized;
  async function pay() {
    setBusy(true);
    setError("");
    try {
      if (needsSignOff) {
        await post<Claim>(`/api/claims/${claim.claim_id}/sign-off`, {
          handler_id: handler,
        });
        setAuthorized(true);
      }
      await post<Claim>(`/api/claims/${claim.claim_id}/pay`, {
        amount: decision.amount,
      });
      setPaid(true);
      refresh();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Payment could not be recorded.",
      );
    } finally {
      setBusy(false);
    }
  }
  if (paid) return <Recorded amount={decision.amount} />;
  const action = needsSignOff ? "Authorize and pay" : "Record payment";
  return (
    <div className="payment">
      <h3>{needsSignOff ? "Handler sign-off required" : "Payment ready"}</h3>
      <p>
        {needsSignOff
          ? "Payouts over $1,000 need a handler’s authorization."
          : "The approved amount is ready for a simulated payment."}
      </p>
      <p className="payout">{money(decision.amount)}</p>
      {needsSignOff && (
        <HandlerSelect value={handler} busy={busy} change={setHandler} />
      )}
      <button
        className="primary"
        disabled={busy || (needsSignOff && !handler)}
        onClick={() => {
          void pay();
        }}
      >
        {busy ? "Recording payment…" : action}
      </button>
      {error && (
        <ErrorNotice
          message={error}
          retry={() => {
            void pay();
          }}
        />
      )}
      <small>No real money is transferred.</small>
    </div>
  );
}

export function Payment({ claim, refresh }: Props) {
  if (claim.decision?.outcome !== "approve") return null;
  if (claim.decision.paid_at)
    return <Recorded amount={claim.decision.amount} />;
  return (
    <PaymentForm claim={claim} decision={claim.decision} refresh={refresh} />
  );
}
