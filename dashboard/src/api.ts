import { useEffect, useState } from "react";

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const body: unknown = await response.json();
    const detail =
      body && typeof body === "object" && "detail" in body ? body.detail : null;
    throw new Error(
      typeof detail === "string"
        ? detail
        : `Request failed (${String(response.status)}).`,
    );
  }
  return response.json() as Promise<T>;
}

export function post<T>(
  path: string,
  body: Record<string, string>,
): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function useResource<T>(
  path: string,
  initialData: T | null,
  poll = true,
): {
  data: T | null;
  error: string;
  reload: () => void;
} {
  const [snapshot, setSnapshot] = useState<{
    path: string;
    data: T | null;
    error: string;
  }>({ path: "", data: initialData, error: "" });
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const data = await request<T>(path, { signal: controller.signal });
        if (!controller.signal.aborted) setSnapshot({ path, data, error: "" });
      } catch (error) {
        if (!controller.signal.aborted)
          setSnapshot((previous) => ({
            path,
            data: previous.path === path ? previous.data : null,
            error:
              error instanceof Error
                ? error.message
                : "Could not load this information.",
          }));
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = poll
      ? setInterval(() => {
          void load();
        }, 2000)
      : undefined;
    return () => {
      controller.abort();
      clearInterval(timer);
    };
  }, [path, poll, version]);
  const current = snapshot.path === path;
  return {
    data: current ? snapshot.data : null,
    error: current ? snapshot.error : "",
    reload: () => {
      setVersion((previous) => previous + 1);
    },
  };
}
