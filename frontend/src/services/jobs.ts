// Async job-queue client. Simulations run through /api/jobs and a worker process;
// the UI submits a job then polls until it reaches a terminal status.
import { apiJson } from './api';

export type JobKind = 'run-simulation' | 'run-comparison';
export type JobStatus = 'pending' | 'running' | 'done' | 'failed';

export interface Job {
  id: number;
  user_id: number | null;
  kind: JobKind;
  status: JobStatus;
  payload: any;
  result: any | null;
  error: string | null;
  attempts: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  queue_position: number | null;
}

export interface QueueStatus {
  pending_total: number;
  running_total: number;
  your_pending: number;
  your_running: number;
  your_next_position: number | null;
}

export async function getQueueStatus(): Promise<QueueStatus> {
  return apiJson<QueueStatus>('/api/jobs/queue/status');
}

export interface JobProgress {
  job_id: number;
  status: JobStatus;
  processed: number;
  total: number;
  percent: number;
  legs: Record<string, { processed: number; total: number }>;
}

export async function getJobProgress(id: number): Promise<JobProgress> {
  return apiJson<JobProgress>(`/api/jobs/${id}/progress`);
}

export async function submitJob(kind: JobKind, payload: any, priority = 0): Promise<Job> {
  return apiJson<Job>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify({ kind, payload, priority }),
  });
}

export async function getJob(id: number): Promise<Job> {
  return apiJson<Job>(`/api/jobs/${id}`);
}

export async function listJobs(): Promise<Job[]> {
  return apiJson<Job[]>('/api/jobs');
}

export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onTick?: (job: Job) => void;
  onProgress?: (p: JobProgress) => void;
}

// Submit a job and resolve with its result once status is 'done'.
// Rejects on 'failed' or timeout.
export async function runJob(
  kind: JobKind,
  payload: any,
  opts: PollOptions = {},
): Promise<any> {
  const { intervalMs = 3000, timeoutMs = 30 * 60 * 1000, onTick, onProgress } = opts;
  const submitted = await submitJob(kind, payload);
  const deadline = Date.now() + timeoutMs;

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await getJob(submitted.id);
    onTick?.(job);
    if (onProgress && (job.status === 'running' || job.status === 'pending')) {
      try {
        onProgress(await getJobProgress(submitted.id));
      } catch {
        /* progress is best-effort */
      }
    }
    if (job.status === 'done') return job.result;
    if (job.status === 'failed') {
      throw new Error(job.error || 'Simulation job failed');
    }
    if (Date.now() > deadline) {
      throw new Error(`Job ${submitted.id} timed out after ${timeoutMs}ms (status=${job.status})`);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
