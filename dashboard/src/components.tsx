import { label, money } from "./format";
import { statuses, type Json, type RecordData, type Status } from "./types";

export function Badge({ status }: Readonly<{ status: Status }>) {
  return (
    <span className={`badge ${status}`}>
      <span aria-hidden="true" className="dot" />
      {statuses[status]}
    </span>
  );
}

export function ErrorNotice({
  message,
  retry,
}: Readonly<{
  message: string;
  retry: () => void;
}>) {
  return (
    <div className="error" role="alert">
      <p>{message}</p>
      <button onClick={retry}>Try again</button>
    </div>
  );
}

function DataValue({ value }: Readonly<{ value: Json }>) {
  if (value === null) return <span>None</span>;
  if (Array.isArray(value))
    return value.length ? (
      <ul className="records">
        {value.map((item) => (
          <li key={JSON.stringify(item)}>
            <DataValue value={item} />
          </li>
        ))}
      </ul>
    ) : (
      <span>None</span>
    );
  if (typeof value === "object") return <Facts data={value} />;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  return <span>{String(value)}</span>;
}

export function Facts({ data }: Readonly<{ data: RecordData }>) {
  return (
    <dl className="facts">
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <dt>{label(key)}</dt>
          <dd>
            {/(?:^amount|_amount$|_cost$|_max$|_limit$|^deductible$)/.test(
              key,
            ) &&
            (typeof value === "number" || typeof value === "string") ? (
              money(value)
            ) : (
              <DataValue value={value} />
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}
