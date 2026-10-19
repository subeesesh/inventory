import { useCallback, useEffect, useRef, useState } from 'react';
import api from './api';

/**
 * Load a GET endpoint: { data, error, loading, reload }.
 * Pass null as the path to skip loading (e.g. when the role cannot see it).
 */
export function useApi(path, { initial = null } = {}) {
  const [data, setData] = useState(initial);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(path));
  const latest = useRef(0);

  const reload = useCallback(async () => {
    if (!path) { setLoading(false); return; }
    const call = ++latest.current;
    setLoading(true);
    try {
      const d = await api.get(path);
      if (call === latest.current) { setData(d); setError(null); }
    } catch (e) {
      if (call === latest.current) setError(e.message);
    } finally {
      if (call === latest.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => { reload(); }, [reload]);

  return { data, error, loading, reload, setData };
}
