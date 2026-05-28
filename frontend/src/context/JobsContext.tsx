import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Job, JobProgress, QueueStatus, getJobProgress, getQueueStatus, listJobs } from '../services/jobs';

interface JobsContextValue {
  jobs: Job[];
  queue: QueueStatus | null;
  loading: boolean;
  refresh: () => Promise<void>;
  // True while any of this user's jobs are pending/running.
  hasActive: boolean;
  // Live incident progress per job id (only populated for running/pending jobs).
  progress: Record<number, JobProgress>;
}

const JobsContext = createContext<JobsContextValue | null>(null);

const IDLE_POLL_MS = 15000; // background refresh
const ACTIVE_POLL_MS = 3000; // while a job is in flight

export function JobsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [progress, setProgress] = useState<Record<number, JobProgress>>({});
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasActive = jobs.some((j) => j.status === 'pending' || j.status === 'running');

  const refresh = useCallback(async () => {
    try {
      const [j, q] = await Promise.all([listJobs(), getQueueStatus()]);
      setJobs(j);
      setQueue(q);

      // Fetch live progress for in-flight jobs (best-effort, parallel).
      const active = j.filter((job) => job.status === 'running' || job.status === 'pending');
      if (active.length) {
        const entries = await Promise.all(
          active.map(async (job) => {
            try {
              return [job.id, await getJobProgress(job.id)] as const;
            } catch {
              return null;
            }
          }),
        );
        setProgress(Object.fromEntries(entries.filter(Boolean) as [number, JobProgress][]));
      } else {
        setProgress({});
      }
    } catch {
      // 401 is handled globally by the api layer; ignore here.
    } finally {
      setLoading(false);
    }
  }, []);

  // Self-scheduling poll: faster cadence when something is active. This is what
  // makes a page refresh mid-job seamless — on mount we fetch the user's jobs
  // from the DB and pick up any still running.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      await refresh();
      if (cancelled) return;
      const active = (await listJobsSafe()).some(
        (j) => j.status === 'pending' || j.status === 'running',
      );
      timer.current = setTimeout(tick, active ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    };
    tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <JobsContext.Provider value={{ jobs, queue, loading, refresh, hasActive, progress }}>
      {children}
    </JobsContext.Provider>
  );
}

// Helper that never throws, used inside the poll loop.
async function listJobsSafe(): Promise<Job[]> {
  try {
    return await listJobs();
  } catch {
    return [];
  }
}

export function useJobs(): JobsContextValue {
  const ctx = useContext(JobsContext);
  if (!ctx) throw new Error('useJobs must be used within JobsProvider');
  return ctx;
}
