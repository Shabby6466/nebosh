import { useCallback, useEffect, useState } from "react";
import type { Candidate } from "./api";

const STORAGE_KEY = "nebosh_proctoring_candidate";

export interface StoredCandidate {
  id: string;
  full_name: string;
  email: string;
  kyc_status: Candidate["kyc_status"];
}

function read(): StoredCandidate | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredCandidate) : null;
  } catch {
    return null;
  }
}

function write(candidate: StoredCandidate | null) {
  try {
    if (candidate) localStorage.setItem(STORAGE_KEY, JSON.stringify(candidate));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable (private mode, quota) — degrade to in-memory only for this tab
  }
}

/** Persists the active candidate across reloads so a lost URL param doesn't strand them mid-flow. */
export function useCandidateSession() {
  const [candidate, setCandidateState] = useState<StoredCandidate | null>(() => read());

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setCandidateState(read());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setCandidate = useCallback((c: StoredCandidate | null) => {
    write(c);
    setCandidateState(c);
  }, []);

  const clearCandidate = useCallback(() => setCandidate(null), [setCandidate]);

  return { candidate, setCandidate, clearCandidate };
}
