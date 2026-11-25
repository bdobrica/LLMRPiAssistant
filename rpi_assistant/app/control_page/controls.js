// Shared by each page. Compare current inputs with the last loaded or saved values.
const el = id => document.getElementById(id);
const form = document.querySelector('form');
function formValues() {
  return JSON.stringify(Array.from(form.querySelectorAll('input,select'),
    field => field.type === 'checkbox' ? field.checked : field.value));
}
let savedValues = formValues();
const markSaved = () => { savedValues = formValues(); };
const hasEdits = () => savedValues !== formValues();
window.addEventListener('beforeunload', event => {
  if (hasEdits()) {
    event.preventDefault();
    event.returnValue = '';
  }
});

async function request(path, options) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(path.startsWith('/admin/') ? 60000 : 7000)});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Control unavailable');
  return data;
}
function initPage(render, unavailable) {
  let revision = 0;
  async function refresh() {
    const started = revision;
    try {
      const state = await request('/status');
      if (started === revision) {
        render(state);
        el('network').textContent = state.error || '';
      }
    } catch {
      if (started === revision) {
        el('network').textContent = 'Device unavailable. Reconnect to its Wi-Fi.';
        if (unavailable) unavailable();
      }
    }
    setTimeout(refresh, 2500);
  }
  refresh();
  return async (action, value, fallback = 'Done.') => {
    try {
      const admin = action.startsWith('settings_') || action === 'privacy_delete';
      const data = await request(admin ? '/admin/change' : '/control', {
        method: 'POST',
        headers: {'Content-Type':'application/json', 'X-Assistant-Control':'1'},
        body: JSON.stringify({action, value})
      });
      revision++;
      render(data);
      el('network').textContent = data.error || '';
      el('message').textContent = data.message || fallback;
      return data;
    } catch (error) {
      el('message').textContent = error.message;
      return null;
    }
  };
}
