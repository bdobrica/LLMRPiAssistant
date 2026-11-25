let catalog;
let inputs = [];
const make = (tag, text) => Object.assign(document.createElement(tag), {textContent: text});
function edits() {
  const changes = Object.create(null);
  for (const {section, key, mode, input} of inputs) {
    if (mode.value === 'keep') continue;
    (changes[section] ||= Object.create(null))[key] = mode.value === 'inherit' ? null : input.value;
  }
  return changes;
}
function needsRestart(changes) {
  return Object.entries(changes).some(([section, values]) => Object.keys(values).some(
    key => !catalog.live.some(([s, k]) => s === section && k === key)));
}
function impact() {
  const changes = edits();
  el('impact').textContent = needsRestart(changes)
    ? 'Applying these edits restarts voice and phone controls. Startup failure restores your previous settings.'
    : 'These settings can apply while the assistant is idle.';
}
function group(section, title, options) {
  const details = make('details', '');
  details.append(make('summary', title));
  for (const [key, field] of Object.entries(options)) {
    const label = key.replaceAll('_', ' ');
    const block = make('fieldset', '');
    block.append(make('legend', label));
    const hint = [field.help, 'Source: ' + field.source + '.'];
    if ('default' in field) hint.push('Built-in: ' + (field.default || 'empty') + '.');
    if (field.environment) hint.push('Environment: ' + field.environment + '.');
    if (field.private) hint.push(field.configured ? 'Configured (hidden).' : 'Empty.');
    block.append(make('p', hint.join(' ')));
    const mode = make('select', '');
    mode.setAttribute('aria-label', 'Action for ' + section + ' ' + label);
    for (const [name, text] of [['keep','Keep'],['set','Set file value'],['inherit','Remove file override']]) {
      mode.add(new Option(text, name));
    }
    const input = make(field.type === 'bool' || field.choices ? 'select' : 'input', '');
    if (field.choices) {
      for (const choice of field.choices) input.add(new Option(choice, choice));
      input.value = field.value;
    } else if (field.type === 'bool') {
      input.add(new Option('Enabled','true'));
      input.add(new Option('Disabled','false'));
      input.value = ['true','1','yes','on'].includes(String(field.value).toLowerCase()) ? 'true' : 'false';
    } else {
      input.type = field.private ? 'password' : ['float','int'].includes(field.type) ? 'number' : 'text';
      if (input.type === 'number') input.step = field.type === 'int' ? '1' : 'any';
      input.value = field.value || '';
      input.autocomplete = field.private ? 'new-password' : 'off';
      input.maxLength = 4096;
    }
    input.setAttribute('aria-label', section + ' ' + label);
    input.disabled = true;
    mode.onchange = () => { input.disabled = mode.value !== 'set'; impact(); };
    block.append(mode, input);
    details.append(block);
    inputs.push({section, key, mode, input});
  }
  el('groups').append(details);
  return details;
}
async function load() {
  try {
    catalog = await request('/admin/options');
    inputs = [];
    el('groups').replaceChildren();
    for (const [section, options] of Object.entries(catalog.options))
      group(section, catalog.groups[section] || section, options);
    el('undo').disabled = !catalog.can_undo;
    form.querySelector('fieldset').disabled = false;
    impact();
    markSaved();
  } catch (error) { el('message').textContent = error.message; }
}
el('add-server').onclick = () => {
  const name = el('server-name').value.trim();
  const section = 'mcp.server.' + name;
  if (!/^[A-Za-z0-9_-]{1,24}$/.test(name) || inputs.some(x => x.section === section)) {
    el('message').textContent = 'Choose a new name with 1–24 letters, digits, underscores or hyphens.';
    return;
  }
  const options = {...catalog.server, name: {...catalog.server.name, value:name}};
  group(section, section, options).open = true;
  el('server-name').value = '';
};
const command = initPage(s => {
  if (!catalog || !s.settings) return;
  el('restart').textContent = s.settings.revision !== catalog.revision
    ? 'Settings changed. Reload this page before editing again.' : s.settings.restart_status || '';
});
async function save(undo) {
  const changes = edits();
  const restart = undo ? catalog.undo_restart : needsRestart(changes);
  if (!undo && !Object.keys(changes).length) return;
  if (undo && !window.confirm('Undo the last saved change and discard any unsaved edits?')) return;
  if (restart && !window.confirm('Restart the assistant? Changing the address or port moves this page. Disabling access or selecting loopback requires local terminal access to turn it back on.')) return;
  const groups = undo ? catalog.undo_groups : Object.keys(changes);
  const trust = groups.includes('app_store');
  if (trust && !window.confirm('Change trusted app sources or signing policy? Only continue if you trust the selected source and key.')) return;
  if (groups.some(s => s.startsWith('mcp')) && !window.confirm('Apply these MCP tool settings? Enabled servers can run programs as the assistant user or receive data over the network.')) return;
  form.querySelector('fieldset').disabled = true;
  try {
    const data = await command(undo ? 'settings_undo' : 'settings_advanced', {
      revision:catalog.revision, edits:changes, confirm_restart:!!restart, confirm_trust:trust
    });
    if (data && !restart) await load();
    if (data && restart) {
      markSaved();
      el('message').textContent = data.message + ' Refresh after the device returns.';
    }
  } finally { form.querySelector('fieldset').disabled = false; }
}
form.onsubmit = e => { e.preventDefault(); save(false); };
el('undo').onclick = () => save(true);
load();
