const task = form.id.split('-')[0];
function describe(item, zone) {
  if (task === 'shopping') return item.item;
  if (task === 'reminders') {
    const due = new Date(item.due_local).toLocaleString(undefined, {
      timeZone: zone, year: 'numeric', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit', second: '2-digit', timeZoneName: 'short'
    });
    return item.label + ' · ' + due + ' · ' + item.state;
  }
  const sec = item.remaining_seconds;
  return item.label + ' · ' + (item.state === 'pending' ? Math.floor(sec / 60) + 'm ' + sec % 60 + 's remaining' : item.state);
}
const rows = new Map();
const command = initPage(s => {
  const error = task === 'timers' ? s.timer_error : s.household_error;
  el(task === 'timers' ? 'timer-error' : 'household-error').textContent = error || '';
  if (task === 'reminders') el('reminder-zone').textContent = 'Assistant timezone: ' + (s.timezone || 'unavailable');
  el('empty').hidden = Boolean(error || s[task]?.length || !Array.isArray(s[task]));
  const ids = new Set();
  for (const item of s[task] || []) {
    ids.add(item.id);
    let row = rows.get(item.id);
    if (!row) {
      row = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.onclick = async () => {
        const label = button.textContent;
        if (label === 'Cancel' && !window.confirm('Cancel “' + item.label + '”?')) return;
        button.disabled = true;
        try {
          await command({timers:'timer_cancel', reminders:'reminder_cancel', shopping:'shopping_remove'}[task], item.id,
                        label === 'Dismiss' ? 'Dismissed.' : 'Cancelled.');
        } finally { button.disabled = false; }
      };
      row.append(document.createElement('span'), button);
      rows.set(item.id, row);
      el(task).append(row);
    }
    row.firstChild.textContent = describe(item, s.timezone);
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
