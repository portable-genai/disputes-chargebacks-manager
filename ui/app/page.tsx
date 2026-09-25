"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this dispute is not queued for review.",
  off: "Review routing is off in this deployment; this dispute is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// A fictional card-scheme dispute the local profile answers: reason code 10.4 filed nine days after
// the transaction, inside its 120-day window. It is edited as JSON because the API takes it nested,
// and the tenant is never part of it: the server takes that from the verified principal.
const DEFAULT_DISPUTE = {
  id: "DSP-DEMO-1001",
  track: "card_scheme",
  reason_code: "10.4",
  amount_minor: 42000,
  currency: "SGD",
  transaction_date: "2025-05-01",
  intake_date: "2025-05-10",
  product: "credit_card",
  market: "SG",
  channel: "app",
  customer_ref: "CUST-DEMO-1",
  merchant_ref: "MERCH-DEMO-9",
  narrative: "Cardholder reports a charge they did not make at an online shop (fictional)",
};

// What the console can do with the one dispute, each a route the service serves.
const ACTIONS = [
  { id: "open", label: "Open the dispute (eligibility, lifecycle state, deadlines)" },
  { id: "abuse", label: "Score refund abuse" },
  { id: "representment", label: "Draft a representment pack" },
  { id: "regulator", label: "Draft a regulator response" },
];

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [action, setAction] = useState(ACTIONS[0].id);
  const [disputeText, setDisputeText] = useState(JSON.stringify(DEFAULT_DISPUTE, null, 2));
  const [asOf, setAsOf] = useState("2025-05-12");
  const [result, setResult] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  // One plain call per action, so each request shape can be read off the source and held against
  // the API. Only opening takes an as-of date; the other three take the dispute alone.
  function send(dispute: unknown): Promise<Response> {
    const headers = { "Content-Type": "application/json", "X-Dev-Persona": persona };
    if (action === "abuse") {
      return fetch(API + "/v1/disputes/abuse", {
        method: "POST",
        headers,
        body: JSON.stringify({ dispute }),
      });
    }
    if (action === "representment") {
      return fetch(API + "/v1/disputes/representment", {
        method: "POST",
        headers,
        body: JSON.stringify({ dispute }),
      });
    }
    if (action === "regulator") {
      return fetch(API + "/v1/disputes/regulator", {
        method: "POST",
        headers,
        body: JSON.stringify({ dispute }),
      });
    }
    return fetch(API + "/v1/disputes/open", {
      method: "POST",
      headers,
      body: JSON.stringify({ dispute, as_of: asOf }),
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    let dispute: unknown;
    try {
      dispute = JSON.parse(disputeText);
    } catch (error) {
      setFailed(true);
      setResult("The dispute is not valid JSON: " + String(error));
      return;
    }
    setBusy(true);
    setFailed(false);
    try {
      const response = await send(dispute);
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Open a dispute. The decision is deterministic, cited, and routed to a human reviewer when it escalates."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The dispute</legend>
          <label>
            Action
            <select value={action} onChange={(event) => setAction(event.target.value)}>
              {ACTIONS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Dispute (JSON; the tenant comes from your persona, not from this field)
            <textarea
              rows={16}
              value={disputeText}
              onChange={(event) => setDisputeText(event.target.value)}
            />
          </label>
          {action === "open" ? (
            <label>
              Assess as of
              <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
            </label>
          ) : null}
          <button type="submit" disabled={busy}>
            {busy ? "Working" : "Run on this dispute"}
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
