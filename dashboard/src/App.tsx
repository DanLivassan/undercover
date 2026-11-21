import { useState } from "react";
import { useResource } from "./api";
import { ClaimDetail } from "./ClaimDetail";
import { Badge, ErrorNotice } from "./components";
import { money } from "./format";
import { statuses, type Claim, type Status } from "./types";
import "./style.css";

function Instructions() {
  const resource = useResource<{ text: string }>(
    "/api/agent/instructions",
    null,
    false,
  );
  return (
    <section className="panel instructions">
      <span className="eyebrow">UnderCover Agent</span>
      <h1>Agent instructions</h1>
      <p className="muted">The instructions used for each review. Read only.</p>
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      {!resource.data && !resource.error && (
        <p role="status">Loading instructions…</p>
      )}
      {resource.data && <pre>{resource.data.text}</pre>}
    </section>
  );
}

function ClaimsDesk() {
  const resource = useResource<Claim[]>("/api/claims", null);
  const [selected, setSelected] = useState("");
  const claims = resource.data;
  const selectedId = selected || claims?.[0]?.claim_id;
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Claims operations</span>
          <h1>Every journey deserves a fair decision.</h1>
          <p>Your claims queue, with the context to move it forward.</p>
        </div>
        <span className="pilot-label">Pilot workspace</span>
      </div>
      <div className="stats" aria-label="Queue overview">
        {(Object.entries(statuses) as [Status, string][]).map(
          ([status, title]) => (
            <div className={`stat ${status}`} key={status}>
              <span>{title}</span>
              <strong>
                {claims
                  ? claims.filter((claim) => claim.status === status).length
                  : "—"}
              </strong>
            </div>
          ),
        )}
      </div>
      {resource.error && (
        <ErrorNotice message={resource.error} retry={resource.reload} />
      )}
      {!claims && !resource.error && <p role="status">Loading claims…</p>}
      {claims?.length === 0 && (
        <section className="panel">
          <h2>You’re all caught up.</h2>
          <p>There are no claims in the queue.</p>
        </section>
      )}
      {claims && claims.length > 0 && (
        <div className="workspace">
          <section className="panel queue">
            <div className="section-heading">
              <h2>Claims queue</h2>
              <span className="count">{claims.length}</span>
            </div>
            <p className="muted queue-note">In queue order · amounts in USD</p>
            <ul>
              {claims.map((claim) => (
                <li key={claim.claim_id}>
                  <button
                    className="claim-row"
                    aria-pressed={selectedId === claim.claim_id}
                    onClick={() => {
                      setSelected(claim.claim_id);
                    }}
                  >
                    <span className="row-top">
                      <span className="mono">{claim.claim_id}</span>
                      <strong>{money(claim.amount_claimed)}</strong>
                    </span>
                    <span className="customer">{claim.customer_name}</span>
                    <span className="summary">{claim.summary}</span>
                    <Badge status={claim.status} />
                  </button>
                </li>
              ))}
            </ul>
          </section>
          {selectedId && (
            <ClaimDetail
              key={selectedId}
              claimId={selectedId}
              refreshQueue={resource.reload}
            />
          )}
        </div>
      )}
    </>
  );
}

export function App() {
  const [page, setPage] = useState("claims");
  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <header>
        <div className="brand">
          <span className="brand-icon" aria-hidden="true">
            u
          </span>
          <span>
            UnderCover<small>Travel insurance</small>
          </span>
        </div>
        <nav aria-label="Main navigation">
          <button
            aria-current={page === "claims" ? "page" : undefined}
            onClick={() => {
              setPage("claims");
            }}
          >
            Claims
          </button>
          <button
            aria-current={page === "instructions" ? "page" : undefined}
            onClick={() => {
              setPage("instructions");
            }}
          >
            Agent instructions
          </button>
        </nav>
        <span className="header-note">
          <span className="dot" /> Claims desk
        </span>
      </header>
      <main id="content">
        {page === "claims" ? <ClaimsDesk /> : <Instructions />}
      </main>
      <footer>
        <span>UnderCover Travel Insurance</span>
        <span>Pilot · All payments are simulated</span>
      </footer>
    </>
  );
}
