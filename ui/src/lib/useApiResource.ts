import React from 'react';

export type ApiResourceState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
};

export function useApiResource<T>(loader: () => Promise<T>, deps: React.DependencyList): ApiResourceState<T> {
  const [data, setData] = React.useState<T | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void loader()
      .then((d) => {
        if (cancelled) return;
        setData(d);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  // Load on mount and whenever dependencies change.
  React.useEffect(() => {
    const cleanup = load();
    return cleanup;
  }, [load]);

  return {
    data,
    loading,
    error,
    reload: load,
  };
}
