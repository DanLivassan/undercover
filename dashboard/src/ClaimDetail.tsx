import { useResource } from "./api";
import { Badge, ErrorNotice, Facts } from "./components";
import { label, money } from "./format";
import { Payment } from "./Payment";
import type { Activity, Claim, Context } from "./types";

function ActivityFeed({ claimId }: Readonly<{ claimId: string }>) {
  const activity = useResource<Activity[]>(
    `/api/claims/${claimId}/events`,
    null,
  );
  return (
    <section className="panel">
      <div className="section-heading">
        <h2>Agent activity</h2>
        <span className="live">Updates every 2 seconds</span>
      </div>
      {activity.error && (
        <ErrorNotice message={activity.error} retry={activity.reload} />
      )}
      {!activity.data && !activity.error && (
        <p role="status">Loading activity…</p>
      )}
      {activity.data?.length === 0 && (
        <p className="muted">The agent has not started this claim.</p>
      )}
      <ol className="timeline">
        {activity.data?.map((event) => (
          <li key={event.id}>
            <div>
              <strong>{label(event.type)}</strong>
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleTimeString("en-US")}
              </time>
            </div>
            <p>{event.content}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ClaimContext({ claimId }: Readonly<{ claimId: string }>) {
  const context = useResource<Context>(
    `/api/claims/${claimId}/context`,
    null,
    false,
  );
  return (
    <section className="panel">
      <h2>Customer and cover</h2>
      {context.error && (
        <ErrorNotice message={context.error} retry={context.reload} />
      )}
      {!context.data && !context.error && <p role="status">Loading cover…</p>}
      {context.data && (
        <>
          <details>
            <summary>Customer and claim history</summary>
            <Facts data={context.data.customer} />
          </details>
          <details>
            <summary>Policy and travelers</summary>
            <Facts data={context.data.policy} />
          </details>
          <details>
            <summary>Plan limits and add-ons</summary>
            <Facts data={context.data.plan} />
            <Facts
              data={{
                add_ons: context.data.add_ons,
                deductible_applies_to: context.data.deductible_applies_to,
              }}
            />
          </details>
        </>
      )}
    </section>
  );
}

export function ClaimDetail({
  claimId,
  refreshQueue,
}: Readonly<{
  claimId: string;
  refreshQueue: () => void;
}>) {
  const resource = useResource<Claim>(`/api/claims/${claimId}`, null);
  const claim = resource.data;
  return (
    <article className="claim-detail" aria-label="Claim details">
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      {!claim && !resource.error && <p role="status">Loading claim…</p>}
      {claim && (
        <>
          <section className="panel claim-heading">
            <div className="section-heading">
              <span className="eyebrow">{claim.claim_id}</span>
              <Badge status={claim.status} />
            </div>
            <h2>{claim.summary}</h2>
            <div className="claim-meta">
              <span>{label(claim.claim_type)}</span>
              <span>{claim.incident_location}</span>
              <span>Incident {claim.incident_date}</span>
            </div>
            <div className="amount">
              <span>Amount claimed</span>
              <strong>{money(claim.amount_claimed)}</strong>
            </div>
            <Facts
              data={{
                submitted_on: claim.submitted_on,
                policy_id: claim.policy_id,
                customer_id: claim.customer_id,
              }}
            />
          </section>
          {claim.decision && (
            <section className="panel decision">
              <div className="section-heading">
                <h2>Agent decision</h2>
                <span className="outcome">{label(claim.decision.outcome)}</span>
              </div>
              <p>{claim.decision.explanation}</p>
              <h3>Calculation</h3>
              <p className="preserve">{claim.decision.calculation}</p>
              <p>
                <strong>Policy reference:</strong>{" "}
                {claim.decision.policy_section}
              </p>
              {claim.decision.signed_at && (
                <p>
                  Authorized by {claim.decision.handler_id} at{" "}
                  {new Date(claim.decision.signed_at).toLocaleString("en-US")}
                </p>
              )}
              <Payment
                key={claim.claim_id}
                claim={claim}
                refresh={() => {
                  resource.reload();
                  refreshQueue();
                }}
              />
            </section>
          )}
          <ActivityFeed claimId={claimId} />
          <section className="panel">
            <h2>What happened</h2>
            <p className="preserve">{claim.story}</p>
            <h3>Items claimed</h3>
            <ul className="items">
              {claim.items.map((item) => (
                <li key={`${item.description}-${item.category}`}>
                  <span>
                    {item.description}
                    <small>{label(item.category)}</small>
                  </span>
                  <strong>{money(item.amount)}</strong>
                </li>
              ))}
            </ul>
          </section>
          <section className="panel">
            <h2>
              Supporting documents{" "}
              <span className="muted">({claim.documents.length})</span>
            </h2>
            {claim.documents.length ? (
              claim.documents.map((document) => (
                <details key={document.name}>
                  <summary>{document.name}</summary>
                  <p className="eyebrow">{label(document.type)}</p>
                  <p className="preserve">{document.content}</p>
                </details>
              ))
            ) : (
              <p className="muted">No documents provided.</p>
            )}
          </section>
          <ClaimContext claimId={claimId} />
        </>
      )}
    </article>
  );
}
