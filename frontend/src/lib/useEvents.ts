import * as React from "react";

/** SSE-Abo mit automatischem Reconnect. Ein Stream fuer die ganze App. */
export function useEventStream(
  handlers: Record<string, (data: unknown) => void>,
  enabled = true,
) {
  const [connected, setConnected] = React.useState(false);
  // In einer Ref halten, damit ein Handler-Wechsel den Stream nicht neu aufbaut.
  // Die Zuweisung gehoert in einen Layout-Effekt, nicht in den Render-Durchlauf:
  // waehrend des Renderns etwas zu veraendern ist mit nebenlaeufigem Rendern
  // nicht vertraeglich. Layout-Effekte laufen vor allen passiven Effekten -
  // der Stream unten sieht also nie eine veraltete Ref.
  const handlersRef = React.useRef(handlers);
  React.useLayoutEffect(() => {
    handlersRef.current = handlers;
  });

  React.useEffect(() => {
    if (!enabled) return;

    let source: EventSource | null = null;
    let retryTimer: number | undefined;
    let retryDelay = 1000;
    let closed = false;

    const connect = () => {
      if (closed) return;
      source = new EventSource("/api/events", { withCredentials: true });

      source.onopen = () => {
        setConnected(true);
        retryDelay = 1000;
      };

      source.onerror = () => {
        setConnected(false);
        source?.close();
        if (closed) return;
        // Exponentieller Backoff bis 30s, damit ein down-Backend nicht
        // den Browser mit Reconnects flutet.
        retryTimer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
      };

      for (const name of Object.keys(handlersRef.current)) {
        source.addEventListener(name, (event) => {
          try {
            handlersRef.current[name]?.(JSON.parse((event as MessageEvent).data));
          } catch {
            /* kaputtes Event ignorieren, Stream weiterlaufen lassen */
          }
        });
      }
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(retryTimer);
      source?.close();
      setConnected(false);
    };
  }, [enabled]);

  return connected;
}

/** Kleiner Helfer fuer Laden/Fehler/Daten, damit die Seiten schlank bleiben. */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: React.DependencyList = [],
): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [tick, setTick] = React.useState(0);
  const loaderRef = React.useRef(loader);
  React.useLayoutEffect(() => {
    loaderRef.current = loader;
  });

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loaderRef.current()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}
