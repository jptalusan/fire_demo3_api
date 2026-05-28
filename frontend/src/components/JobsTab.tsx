import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { RefreshCw, ChevronDown, ChevronRight, Clock, ListOrdered, Loader2, Eye } from 'lucide-react';
import { useJobs } from '../context/JobsContext';
import { Job, JobProgress } from '../services/jobs';

const STATUS_COLOR: Record<string, string> = {
  pending: 'bg-amber-100 text-amber-800',
  running: 'bg-blue-100 text-blue-800',
  done: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

function fmtTime(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  return d.toLocaleString();
}

function fmtDuration(s: number | null): string {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s % 60)}s`;
}

function ResultSummary({ job }: { job: Job }) {
  if (job.status === 'failed') {
    return <div className="text-sm text-red-600 whitespace-pre-wrap">{job.error || 'Job failed'}</div>;
  }
  if (!job.result) return <div className="text-sm text-muted-foreground">No result yet.</div>;

  const r = job.result;
  // run-comparison shape
  if (r.comparison) {
    const a = r.baseline || {};
    const b = r.newConfig || {};
    const m = r.comparison.overall_metrics || {};
    return (
      <div className="text-sm space-y-2">
        <div className="font-medium">Comparison · {r.comparison?.summary?.overall_assessment ?? '—'}</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-1">Metric</th><th>Baseline</th><th>New</th><th>Δ</th>
            </tr>
          </thead>
          <tbody>
            <tr><td>Avg response (s)</td><td>{a.average_response_time?.toFixed?.(1) ?? '—'}</td><td>{b.average_response_time?.toFixed?.(1) ?? '—'}</td><td>{m.average_response_time?.difference?.toFixed?.(2) ?? '—'}</td></tr>
            <tr><td>Coverage (%)</td><td>{a.coverage_percent?.toFixed?.(1) ?? '—'}</td><td>{b.coverage_percent?.toFixed?.(1) ?? '—'}</td><td>{m.coverage_percent?.difference?.toFixed?.(2) ?? '—'}</td></tr>
            <tr><td>P90 (s)</td><td>{a.P90_continuous?.toFixed?.(1) ?? '—'}</td><td>{b.P90_continuous?.toFixed?.(1) ?? '—'}</td><td>{m.p90_response_time?.difference?.toFixed?.(2) ?? '—'}</td></tr>
          </tbody>
        </table>
      </div>
    );
  }
  // run-simulation shape
  return (
    <div className="text-sm grid grid-cols-2 gap-x-4 gap-y-1">
      <span className="text-muted-foreground">Total incidents</span><span>{r.total_incidents ?? '—'}</span>
      <span className="text-muted-foreground">Avg response (s)</span><span>{r.average_response_time?.toFixed?.(1) ?? '—'}</span>
      <span className="text-muted-foreground">Coverage (%)</span><span>{r.coverage_percent?.toFixed?.(1) ?? '—'}</span>
      <span className="text-muted-foreground">P90 (s)</span><span>{r.P90_continuous?.toFixed?.(1) ?? '—'}</span>
    </div>
  );
}

function fmtConfig(job: Job): string {
  // Surface the key settings/changes that produced this run.
  const p = job.kind === 'run-comparison' ? (job.payload?.newConfig ?? {}) : (job.payload ?? {});
  const parts: string[] = [];
  if (p.incident_type) parts.push(p.incident_type);
  if (p.dispatch_policy) parts.push(p.dispatch_policy);
  if (p.models?.incident) parts.push(p.models.incident.replace('_incidents', ''));
  const dr = p.date_range || {};
  if (dr.start_date && dr.end_date) parts.push(`${dr.start_date.slice(0, 10)} → ${dr.end_date.slice(0, 10)}`);
  if (Array.isArray(p.stations) && p.stations.length) parts.push(`${p.stations.length} custom stations`);
  return parts.join(' · ') || '—';
}

function ConfigSummary({ job }: { job: Job }) {
  // For comparisons the changes live in newConfig; baseline is default stations.
  const cfg = job.kind === 'run-comparison' ? (job.payload?.newConfig ?? {}) : (job.payload ?? {});
  const m = cfg.models ?? {};
  const dr = cfg.date_range ?? {};
  const stations: any[] = Array.isArray(cfg.stations) ? cfg.stations : [];

  const apparatusLine = (s: any) =>
    (s.apparatus ?? []).map((a: any) => `${a.type}×${a.count}`).join(', ') || 'none';

  return (
    <div className="text-xs space-y-3 mt-3 border-t pt-3">
      <div className="font-medium text-sm">Configuration{job.kind === 'run-comparison' ? ' (new vs. default baseline)' : ''}</div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        <span className="text-muted-foreground">Incident model</span><span>{m.incident ?? '—'}</span>
        <span className="text-muted-foreground">Incident type</span><span>{cfg.incident_type ?? '—'}</span>
        <span className="text-muted-foreground">Dispatch policy</span><span>{cfg.dispatch_policy ?? m.dispatch ?? '—'}</span>
        <span className="text-muted-foreground">Travel-time model</span><span>{m.travelTime ?? '—'}</span>
        <span className="text-muted-foreground">Service-time model</span><span>{m.serviceTime ?? '—'}</span>
        <span className="text-muted-foreground">Station data</span><span>{cfg.station_data ?? '—'}</span>
        <span className="text-muted-foreground">Date range</span>
        <span>{dr.start_date ? `${String(dr.start_date).slice(0, 10)} → ${String(dr.end_date).slice(0, 10)}` : '—'}</span>
        <span className="text-muted-foreground">EMS</span><span>{cfg.disable_ems ? 'disabled' : 'enabled'}</span>
      </div>

      {stations.length > 0 && (
        <details>
          <summary className="cursor-pointer text-muted-foreground">
            {stations.length} custom stations (locations + apparatus)
          </summary>
          <div className="mt-2 max-h-48 overflow-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-muted-foreground">
                  <th className="py-1 pr-2">Station</th><th className="pr-2">lat, lon</th><th>Apparatus</th>
                </tr>
              </thead>
              <tbody>
                {stations.map((s: any, i: number) => (
                  <tr key={s.id ?? i} className="border-t border-gray-100">
                    <td className="py-1 pr-2">{s.name ?? s.id}</td>
                    <td className="pr-2 font-mono">{Number(s.lat).toFixed(5)}, {Number(s.lon).toFixed(5)}</td>
                    <td>{apparatusLine(s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function JobRow({ job, onLoadJob, progress }: { job: Job; onLoadJob?: (job: Job) => void; progress?: JobProgress }) {
  const [open, setOpen] = useState(false);
  const terminal = job.status === 'done' || job.status === 'failed';
  const showBar = job.status === 'running' && progress && progress.total > 0;
  return (
    <div className="border rounded-lg p-3">
      <div className="flex items-center justify-between gap-2">
        <button className="flex items-center gap-2 text-left flex-1 min-w-0" onClick={() => setOpen((o) => !o)}>
          {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          <span className="font-mono text-xs text-muted-foreground">#{job.id}</span>
          <span className="text-sm font-medium">{job.kind}</span>
          <Badge className={STATUS_COLOR[job.status]}>
            {(job.status === 'running' || job.status === 'pending') && <Loader2 className="h-3 w-3 mr-1 animate-spin" />}
            {job.status}
            {job.status === 'pending' && job.queue_position != null ? ` · #${job.queue_position} in queue` : ''}
          </Badge>
        </button>
        <div className="flex items-center gap-3 text-xs text-muted-foreground shrink-0">
          {terminal && <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{fmtDuration(job.duration_seconds)}</span>}
          <span>{fmtTime(job.created_at)}</span>
          {job.status === 'done' && onLoadJob && (
            <Button variant="default" size="sm" className="gap-1 h-7" onClick={() => onLoadJob(job)}>
              <Eye className="h-3 w-3" /> View
            </Button>
          )}
        </div>
      </div>
      {/* Always show the settings line so users can scan past runs. */}
      <div className="mt-1 pl-6 text-xs text-muted-foreground truncate">{fmtConfig(job)}</div>

      {/* Live incident progress while running. */}
      {showBar && (
        <div className="mt-2 pl-6">
          <div className="flex justify-between text-xs text-muted-foreground mb-1">
            <span>Incidents processed</span>
            <span className="font-mono">
              {progress!.processed.toLocaleString()} / {progress!.total.toLocaleString()} ({progress!.percent}%)
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-gray-200 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-[width] duration-500"
              style={{ width: `${progress!.percent}%` }}
            />
          </div>
        </div>
      )}
      {open && (
        <div className="mt-3 pl-6">
          <ResultSummary job={job} />
          <ConfigSummary job={job} />
        </div>
      )}
    </div>
  );
}

export function JobsTab({ onLoadJob }: { onLoadJob?: (job: Job) => void }) {
  const { jobs, queue, loading, refresh, progress } = useJobs();

  return (
    <div className="space-y-4 p-1">
      {/* Queue summary */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <ListOrdered className="h-4 w-4" /> Queue
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {queue ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div><div className="text-2xl font-semibold">{queue.running_total}</div><div className="text-xs text-muted-foreground">running (everyone)</div></div>
              <div><div className="text-2xl font-semibold">{queue.pending_total}</div><div className="text-xs text-muted-foreground">pending (everyone)</div></div>
              <div><div className="text-2xl font-semibold">{queue.your_pending + queue.your_running}</div><div className="text-xs text-muted-foreground">your active jobs</div></div>
              <div><div className="text-2xl font-semibold">{queue.your_next_position ?? '—'}</div><div className="text-xs text-muted-foreground">your queue position</div></div>
            </div>
          ) : (
            <div className="text-muted-foreground">Loading…</div>
          )}
        </CardContent>
      </Card>

      {/* Job history */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Your jobs ({jobs.length})</h3>
        <Button variant="outline" size="sm" onClick={() => refresh()} className="gap-1">
          <RefreshCw className="h-3 w-3" /> Refresh
        </Button>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="text-sm text-muted-foreground">Loading jobs…</div>
      ) : jobs.length === 0 ? (
        <div className="text-sm text-muted-foreground">No jobs yet. Run a simulation to see it here.</div>
      ) : (
        <div className="space-y-2">
          {jobs.map((j) => <JobRow key={j.id} job={j} onLoadJob={onLoadJob} progress={progress[j.id]} />)}
        </div>
      )}
    </div>
  );
}
