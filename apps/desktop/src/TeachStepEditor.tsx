import { useMemo } from 'react';
import type { Action, Plan, TeachAnalysis } from './types';

type Target = TeachAnalysis['observed_targets'][number];

function parsePlan(text: string): Plan | null {
  try {
    const value: unknown = JSON.parse(text);
    if (!value || typeof value !== 'object' || !('actions' in value) ||
        !Array.isArray(value.actions)) return null;
    return value as Plan;
  } catch {
    return null;
  }
}

export default function TeachStepEditor({
  value, onChange, targets,
}: {
  value: string;
  onChange: (value: string) => void;
  targets: Target[];
}) {
  const plan = useMemo(() => parsePlan(value), [value]);
  const edit = (change: (next: Plan) => void) => {
    if (!plan) return;
    const next = JSON.parse(JSON.stringify(plan)) as Plan;
    change(next);
    onChange(JSON.stringify(next, null, 2));
  };
  const first = (type: string) => targets.find(item => item.control_type === type)?.automation_id;
  const addStep = (kind: Action['kind']) => {
    if (!plan || plan.actions.length >= 12) return;
    const target = kind === 'ui.set_text' ? first('Edit') : first('Button');
    const status = first('Text') ?? first('Static') ?? target;
    const text = kind === 'ui.set_text' ? '{{value}}' : null;
    edit(next => next.actions.push({
      kind,
      automation_id: target ?? '',
      text,
      keys: [],
      timeout_seconds: 5,
      expected: {
        automation_id: kind === 'ui.set_text' ? (target ?? '') : (status ?? ''),
        property: 'text_equals',
        value: text ?? 'REPLACE_WITH_OBSERVED_OUTCOME',
      },
    }));
  };

  if (!plan) {
    return <p className="operation-note operation-note--error">Invalid procedure JSON. Restore a valid plan in Advanced JSON to use the guided editor.</p>;
  }
  return (
    <div className="teach-review-editor" aria-label="Guided Teach correction">
      <datalist id="teach-reviewed-uia-targets">
        {targets.map(target => <option key={target.automation_id} value={target.automation_id} label={target.control_type} />)}
      </datalist>
      <label htmlFor="teach-reviewed-objective">What should this Skill achieve?</label>
      <input id="teach-reviewed-objective" maxLength={500} value={plan.objective}
        onChange={event => edit(next => { next.objective = event.target.value; })} required />
      <label htmlFor="teach-reviewed-explanation">Explain what you demonstrated</label>
      <textarea id="teach-reviewed-explanation" rows={2} maxLength={2000} value={plan.explanation}
        onChange={event => edit(next => { next.explanation = event.target.value; })} required />
      <p className="operation-note">Only UIA selectors actually seen during your authorized recording are accepted. No password characters were recorded. You must supply expected outcomes yourself.</p>
      {plan.actions.map((step, index) => {
        const parameter = step.text?.match(/^\{\{([a-z][a-z0-9_]{0,31})\}\}$/)?.[1] ?? '';
        return <fieldset className="teach-step-editor" key={index}>
          <legend>Step {index + 1}</legend>
          <label htmlFor={`teach-kind-${index}`}>Action</label>
          <select id={`teach-kind-${index}`} value={step.kind}
            onChange={event => {
              const kind = event.target.value as Action['kind'];
              edit(next => {
                next.actions[index].kind = kind;
                next.actions[index].text = kind === 'ui.set_text' ? '{{value}}' : null;
                next.actions[index].keys = [];
                next.actions[index].expected.value = kind === 'ui.set_text' ? '{{value}}' : 'REPLACE_WITH_OBSERVED_OUTCOME';
              });
            }}>
            <option value="ui.click">Select UI control</option>
            <option value="ui.set_text">Enter reviewed text</option>
          </select>
          <label htmlFor={`teach-target-${index}`}>UI Automation target (observed)</label>
          <input id={`teach-target-${index}`} list="teach-reviewed-uia-targets" value={step.automation_id ?? ''}
            onChange={event => edit(next => {
              const current = next.actions[index];
              if (current.expected.automation_id === current.automation_id) {
                current.expected.automation_id = event.target.value;
              }
              current.automation_id = event.target.value;
            })} required />
          {step.kind === 'ui.set_text' && <>
            <label htmlFor={`teach-parameter-${index}`}>Reusable parameter name (letters, numbers, underscore)</label>
            <input id={`teach-parameter-${index}`} value={parameter}
              placeholder="person" pattern="[a-z][a-z0-9_]{0,31}" maxLength={32}
              onChange={event => {
                const name = event.target.value;
                if (name && !/^[a-z][a-z0-9_]{0,31}$/.test(name)) return;
                edit(next => {
                  const action = next.actions[index];
                  const previous = action.text;
                  action.text = name ? `{{${name}}}` : '';
                  if (action.expected.value === previous) {
                    action.expected.value = action.text;
                  }
                });
              }} />
            <label htmlFor={`teach-text-${index}`}>Text or a literal {'{{parameter}}'} placeholder</label>
            <input id={`teach-text-${index}`} value={step.text ?? ''} autoComplete="off" maxLength={2000}
              onChange={event => edit(next => { next.actions[index].text = event.target.value; })} required />
          </>}
          <label htmlFor={`teach-verify-target-${index}`}>Independent expected outcome selector</label>
          <input id={`teach-verify-target-${index}`} list="teach-reviewed-uia-targets"
            value={step.expected.automation_id}
            onChange={event => edit(next => { next.actions[index].expected.automation_id = event.target.value; })} required />
          <label htmlFor={`teach-verify-property-${index}`}>Expected observable property</label>
          <select id={`teach-verify-property-${index}`} value={step.expected.property}
            onChange={event => edit(next => {
              const expected = next.actions[index].expected;
              expected.property = event.target.value as typeof expected.property;
              expected.value = expected.property === 'exists' ? null :
                expected.property === 'enabled' ? true : 'REPLACE_WITH_OBSERVED_OUTCOME';
            })}>
            <option value="text_equals">Exact text</option>
            <option value="text_contains">Text contains</option>
            <option value="enabled">Enabled state</option>
            <option value="exists">Exists (not sufficient as a final outcome)</option>
          </select>
          {step.expected.property === 'enabled' ?
            <select aria-label={`Expected enabled state for step ${index + 1}`}
              value={String(step.expected.value)}
              onChange={event => edit(next => {
                next.actions[index].expected.value = event.target.value === 'true';
              })}>
              <option value="true">Enabled</option><option value="false">Disabled</option>
            </select> :
            step.expected.property !== 'exists' &&
            <label htmlFor={`teach-outcome-${index}`}>Expected result, optionally with {'{{parameter}}'}</label>}
          {step.expected.property !== 'enabled' && step.expected.property !== 'exists' &&
            <input id={`teach-outcome-${index}`} maxLength={2000}
              value={typeof step.expected.value === 'string' ? step.expected.value : ''}
              onChange={event => edit(next => { next.actions[index].expected.value = event.target.value; })} required />}
          <button type="button" className="system-secondary" onClick={() => edit(next => { next.actions.splice(index, 1); })}>Remove step</button>
        </fieldset>;
      })}
      <div className="execution-controls">
        <button type="button" className="system-secondary" disabled={plan.actions.length >= 12}
          onClick={() => addStep('ui.click')}>Add selection</button>
        <button type="button" className="system-secondary" disabled={plan.actions.length >= 12}
          onClick={() => addStep('ui.set_text')}>Add parameterized text entry</button>
      </div>
    </div>
  );
}
