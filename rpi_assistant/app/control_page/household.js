const task = form.id.split('-')[0];
function describe(item) {
  if (task === 'shopping') return item.item;
  if (task === 'reminders') return item.label + ' · ' + item.due_local.replace('T', ' ') + ' · ' + item.state;
  const sec = item.remaining_seconds;
  return item.label + ' · ' + (item.state === 'pending' ? Math.floor(sec / 60) + 'm ' + sec % 60 + 's remaining' : item.state);
}
const rows = new Map();
const command = initPage(s => {
  const error = task === 'timers' ? s.timer_error : s.household_error;
  el(task === 'timers' ? 'timer-error' : 'household-error').textContent = error || '';
  if (task === 'reminders') el('reminder-zone').textContent = 'Timezone: ' + (s.timezone || 'unavailable');
  const ids = new Set();
  for (const item of s[task] || []) {
    ids.add(item.id);
    let row = rows.get(item.id);
    if (!row) {
      row = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.onclick = () => command({timers:'timer_cancel', reminders:'reminder_cancel', shopping:'shopping_remove'}[task], item.id, 'Timer cancelled.');
      row.append(document.createElement('span'), button);
      rows.set(item.id, row);
      el(task).append(row);
    }
    row.firstChild.textContent = describe(item);
    const label = task === 'shopping' ? 'Remove' : item.state === 'missed' ? 'Dismiss' : 'Cancel';
    row.lastChild.textContent = label;
    row.lastChild.setAttribute('aria-label', label + ' ' + (item.label || item.item));
  }
  for (const [id, row] of rows) {
    if (!ids.has(id)) { row.remove(); rows.delete(id); }
  }
});
form.onsubmit = async event => {
  event.preventDefault();
  let action, value;
  if (task === 'shopping') {
    action = 'shopping_add';
    value = el('shopping-item').value.trim();
  } else if (task === 'reminders') {
    action = 'reminder_create';
    value = {text: el('reminder-text').value.trim(), local_time: el('reminder-time').value, occurrence: el('reminder-occurrence').value};
  } else {
    action = 'timer_create';
    const seconds = Number(el('timer-minutes').value) * 60 + Number(el('timer-seconds').value);
    if (seconds < 1 || seconds > 604800) {
      el('message').textContent = 'Choose a duration from one second to seven days.';
      return;
    }
    value = {seconds, label: el('timer-name').value};
  }
  const fields = form.querySelector('fieldset');
  fields.disabled = true;
  try {
    if (await command(action, value)) {
      form.reset();
      markSaved();
    }
  } finally { fields.disabled = false; }
};
