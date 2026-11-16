import type { AgentEvent, Demonstration, Health, ModelInfo, Observation, Plan, Session, Skill, TeachAnalysis } from './types';

const DEFAULT_ORIGIN = 'http://127.0.0.1:8765';

/** The credential lives only in React memory, never localStorage or the URL. */
export class PikoClient {
  constructor(private readonly token: string, private readonly origin = DEFAULT_ORIGIN) {}

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 100_000);
    try {
      const response = await fetch(`${this.origin}${path}`, {
        ...options,
        signal: controller.signal,
        headers: {
          'Authorization': `Bearer ${this.token}`,
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        },
        cache: 'no-store',
      });
      if (!response.ok) {
        let detail = `HTTP ${response.status}`;
        try {
          const data: unknown = await response.json();
          if (typeof data === 'object' && data !== null && 'detail' in data) {
            const message = (data as { detail: unknown }).detail;
            detail = typeof message === 'string' ? message : JSON.stringify(message);
          }
        } catch { /* retain HTTP error when the body is not JSON */ }
        throw new Error(detail);
      }
      return response.json() as Promise<T>;
    } catch (error) {
      if (error instanceof TypeError) throw new Error(`Cannot reach the Piko backend at ${this.origin}.`);
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  health() { return this.request<Health>('/health'); }
  models() { return this.request<{ installed: ModelInfo[]; reasoning: string | null; vision: string | null }>('/models'); }
  selectModels(reasoning_model: string, vision_model: string | null) {
    return this.request<{ reasoning: string; vision: string | null }>('/models/selection', {
      method: 'POST', body: JSON.stringify({ reasoning_model, vision_model }),
    });
  }
  sessions() { return this.request<Session[]>('/sessions'); }
  session(id: string) { return this.request<Session>(`/sessions/${encodeURIComponent(id)}`); }
  events(id: string) { return this.request<AgentEvent[]>(`/sessions/${encodeURIComponent(id)}/events`); }
  skills() { return this.request<Skill[]>('/skills'); }
  reviewSkill(slug: string, parameters: Record<string, string> = {}) {
    return this.request<Session>(`/skills/${encodeURIComponent(slug)}/review`, {
      method: 'POST', body: JSON.stringify({ authorize_foreground_app: true, parameters }),
    });
  }
  async exportSkill(slug: string): Promise<Blob> {
    const response = await fetch(`${this.origin}/skills/${encodeURIComponent(slug)}/export`, {
      headers: { Authorization: `Bearer ${this.token}` },
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`Skill export failed: HTTP ${response.status}`);
    return response.blob();
  }
  importSkill(archive_base64: string) {
    return this.request<{ name: string; status: string }>(`/skills/import`, {
      method: 'POST', body: JSON.stringify({ archive_base64 }),
    });
  }
  skillRevisions(slug: string) {
    return this.request<{ revisions: number[] }>(`/skills/${encodeURIComponent(slug)}/revisions`);
  }
  rollbackSkill(slug: string, revision: number) {
    return this.request(`/skills/${encodeURIComponent(slug)}/rollback/${revision}`, {
      method: 'POST',
    });
  }
  skillHistory(slug: string) {
    return this.request<Array<{ session_id: string; completed: boolean; timestamp: string }>>(
      `/skills/${encodeURIComponent(slug)}/history`);
  }
  windows(executable: string) {
    return this.request<Array<{ window_handle: number; title: string; executable: string; process_id: number }>>(
      `/windows?executable=${encodeURIComponent(executable)}`);
  }
  createSession(objective: string, executable: string, targetWindowHandle?: number) {
    return this.request<Session>('/sessions', {
      method: 'POST', body: JSON.stringify({
        objective, executable, target_window_handle: targetWindowHandle ?? null,
        allow_activate: targetWindowHandle !== undefined,
      }),
    });
  }
  grant(executable: string, profile: 'observe' | 'limited', session_id?: string) {
    return this.request('/permissions', { method: 'POST', body: JSON.stringify({ executable, profile, session_id }) });
  }
  revoke(executable: string) { return this.request(`/permissions/${encodeURIComponent(executable)}`, { method: 'DELETE' }); }
  plan(id: string) { return this.request<Session>(`/sessions/${id}/plan`, { method: 'POST' }); }
  execute(id: string) { return this.request(`/sessions/${id}/execute`, { method: 'POST' }); }
  pause(id: string) { return this.request(`/sessions/${id}/pause`, { method: 'POST' }); }
  resume(id: string) { return this.request(`/sessions/${id}/resume`, { method: 'POST' }); }
  stop(id: string) { return this.request(`/sessions/${id}/stop`, { method: 'POST' }); }
  emergencyStop() { return this.request('/emergency-stop', { method: 'POST' }); }
  observe(id: string) { return this.request<Observation>(`/sessions/${encodeURIComponent(id)}/observation`); }
  teachStatus() { return this.request<{ recording: boolean; id: string | null }>('/teach/status'); }
  startTeach(executable: string, seconds: number) {
    return this.request<{ id: string; recording: boolean }>(`/teach/start?seconds=${seconds}`, {
      method: 'POST', body: JSON.stringify({ executable, profile: 'observe', session_id: 'teach' }),
    });
  }
  latestTeach() { return this.request<Demonstration>('/teach/latest'); }
  analyzeTeach(id: string) {
    return this.request<TeachAnalysis>(`/teach/${encodeURIComponent(id)}/analysis`);
  }
  saveTeachDraft(id: string, slug: string, description: string,
                 plan: Plan, confirmedUserCorrections: boolean) {
    return this.request(`/teach/${encodeURIComponent(id)}/draft`, {
      method: 'POST',
      body: JSON.stringify({
        slug, description, plan, confirmed_user_corrections: confirmedUserCorrections,
      }),
    });
  }
  stopTeach() { return this.request<Demonstration>('/teach/stop', { method: 'POST' }); }
  deleteTeach(id: string) { return this.request(`/teach/${encodeURIComponent(id)}`, { method: 'DELETE' }); }
  saveSkill(id: string, slug: string, description: string) {
    return this.request(`/sessions/${encodeURIComponent(id)}/save-skill`, {
      method: 'POST', body: JSON.stringify({ slug, description }),
    });
  }
}
