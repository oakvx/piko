export type AgentState = 'idle' | 'observing' | 'analyzing' | 'planning' | 'executing' | 'verifying' | 'paused' | 'waiting_for_user' | 'completed' | 'failed' | 'cancelled';
export type Lens = 'work' | 'teach' | 'skills' | 'coach' | 'system';
export type Access = 'observe' | 'limited' | 'full';

export interface Expectation {
  automation_id: string;
  property: 'exists' | 'text_equals' | 'text_contains' | 'enabled';
  value: string | boolean | null;
}
export interface Action {
  kind: 'ui.click' | 'ui.set_text' | 'keyboard.hotkey' | 'wait.condition';
  automation_id: string | null;
  text: string | null;
  keys: string[];
  timeout_seconds: number;
  expected: Expectation;
}
export interface Plan {
  objective: string;
  explanation: string;
  actions: Action[];
}
export interface Session {
  id: string;
  objective: string;
  state: AgentState;
  app_executable: string;
  created_at: string;
  updated_at: string;
  plan: Plan | null;
  next_action: number;
  error: string | null;
}
export interface AgentEvent {
  type: string;
  timestamp: string;
  payload: Record<string, string | boolean | number | null>;
}
export interface Health {
  status: string;
  mode: string;
  platform: string;
  active_session_count: number;
}
export interface ModelInfo {
  name: string;
  size?: number;
  details?: { parameter_size?: string; quantization_level?: string };
}
export interface Skill {
  name: string;
  description: string;
  version: string;
  status: string;
  executable: string;
  actions: number;
  parameters?: string[];
}
export interface Observation {
  timestamp: string;
  window_title: string;
  process_id: number;
  executable: string;
  window_handle?: number | null;
  elements: { automation_id: string; name: string; control_type: string; bounds: [number, number, number, number] | null }[];
  capture_bounds: [number, number, number, number] | null;
  image_base64: string;
}
export interface Demonstration {
  id: string;
  frames: number;
  recording: boolean;
  limitations: string[];
  stopped_reason?: string | null;
}

export interface TeachAnalysis {
  id: string;
  frames: number;
  input_events: number;
  status: 'needs_review';
  steps: Array<{
    kind: 'ui.click';
    automation_id: string | null;
    confidence: 'tentative' | 'unresolved';
    requires_expected_outcome: boolean;
  }>;
  observed_targets: Array<{ automation_id: string; control_type: string }>;
  uncertainties: string[];
}
