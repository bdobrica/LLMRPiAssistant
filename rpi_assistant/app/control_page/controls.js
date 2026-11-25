const el = id => document.getElementById(id);
let muted = false;
let resetPending = false;
function show(s) {
  if (resetPending && !s.reset_pending) el('message').textContent = 'New conversation ready.';
  resetPending = s.reset_pending;
  muted = s.muted;
  el('mute').disabled = false;
  el('mute').textContent = muted ? 'Unmute microphone' : 'Mute microphone';
  el('capture').textContent = muted ? 'Microphone closed · steady red' : s.capture_active ? 'Microphone capture active' : 'Capture unavailable · mute not confirmed';
  el('status').textContent = s.state === 'CAPTURE_ERROR' ? 'Microphone control needs attention' : s.reset_pending ? 'New conversation pending · previous request finishing' : s.state === 'ALERT' ? 'Timer ringing · amber' : s.busy ? 'Finishing request…' : s.state === 'FOLLOW_UP' ? 'Ready for a follow-up · green' : muted ? 'Muted' : s.capture_active ? 'Ready for wake word' : 'Microphone unavailable';
  el('volume').textContent = s.volume === null ? 'Unavailable' : s.volume + '%';
  if(s.error) el('message').textContent = s.error;
  el('household-error').textContent = s.household_error || '';
  el('reminder-zone').textContent = s.timezone ? 'Timezone: ' + s.timezone : 'Reminder timezone unavailable';
  el('shopping').replaceChildren();
  for (const item of s.shopping || []) {
    const row=document.createElement('li'), text=document.createElement('span'), remove=document.createElement('button');
    text.textContent=item.item; remove.textContent='Remove'; remove.onclick=()=>command('shopping_remove',item.id);
    row.append(text,remove); el('shopping').append(row);
  }
  el('reminders').replaceChildren();
  for (const reminder of s.reminders || []) {
    const row=document.createElement('li'), text=document.createElement('span'), remove=document.createElement('button');
    text.textContent=reminder.label + ' · ' + reminder.due_local.replace('T',' ') + ' · ' + reminder.state;
    remove.textContent=reminder.state==='missed'?'Dismiss':'Cancel'; remove.onclick=()=>command('reminder_cancel',reminder.id);
    row.append(text,remove); el('reminders').append(row);
  }
  el('timer-error').textContent = s.timer_error || '';
  el('timers').replaceChildren();
  for (const t of s.timers || []) {
    const row = document.createElement('li');
    const text = document.createElement('span');
    const seconds = t.remaining_seconds;
    text.textContent = t.label + ' · ' + (t.state === 'pending' ? Math.floor(seconds/60) + 'm ' + seconds%60 + 's remaining' : t.state);
    const cancel = document.createElement('button');
    cancel.textContent = t.state === 'missed' ? 'Dismiss' : 'Cancel';
    cancel.onclick = () => command('timer_cancel', t.id);
    row.append(text, cancel); el('timers').append(row);
  }
}
async function request(path, options) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(7000)});
  const data = await response.json();
  if(!response.ok) throw Error(data.error || 'Control unavailable');
  return data;
}
async function refresh() {
  try { show(await request('/status')); }
  catch(e) { el('status').textContent = 'Device unavailable · reconnect to its Wi-Fi'; el('capture').textContent = 'Capture status unknown'; el('mute').disabled = true; }
}
async function command(action, value) {
  try { const data = await request('/control', {method:'POST',headers:{'Content-Type':'application/json','X-Assistant-Control':'1'},body:JSON.stringify({action,value})}); show(data); el('message').textContent = data.message || (action === 'new_conversation' ? (data.reset_pending ? 'Will start fresh when the pending request finishes.' : 'New conversation ready.') : action === 'timer_cancel' ? 'Timer cancelled.' : action === 'stop' ? 'Stopped. Already dispatched actions may still finish.' : 'Microphone setting updated.'); }
  catch(e) { el('message').textContent = e.message; await refresh(); }
}
el('stop').onclick = () => command('stop');
el('mute').onclick = () => command('mute', !muted);
el('down').onclick = () => command('volume_down');
el('up').onclick = () => command('volume_up');
el('set').onclick = () => {const v=Number(el('level').value); if(Number.isInteger(v)&&v>=0&&v<=100) command('volume',v); else el('message').textContent='Enter a whole number from 0 to 100.';};
el('shopping-add').onclick = async () => {
  const item=el('shopping-item').value.trim();
  if(!item) {el('household-error').textContent='Enter an item first.'; return;}
  el('shopping-add').disabled=true;
  try {await command('shopping_add', item);} finally {el('shopping-add').disabled=false;}
};
el('reminder-add').onclick = async () => {
  const text=el('reminder-text').value.trim(), local_time=el('reminder-time').value;
  if(!text || !local_time) {el('household-error').textContent='Enter reminder text and an exact local date/time.'; return;}
  el('reminder-add').disabled=true;
  try {await command('reminder_create', {text,local_time,occurrence:el('reminder-occurrence').value});}
  finally {el('reminder-add').disabled=false;}
};
el('timer-add').onclick = async () => {
  const minutes=Number(el('timer-minutes').value), seconds=Number(el('timer-seconds').value);
  if(!Number.isInteger(minutes)||!Number.isInteger(seconds)||minutes<0||seconds<0||seconds>59||minutes*60+seconds<1||minutes*60+seconds>604800) {
    el('timer-error').textContent='Choose a duration from one second to seven days.'; return;
  }
  el('timer-add').disabled = true;
  try { await command('timer_create', {seconds:minutes*60+seconds,label:el('timer-name').value}); }
  finally { el('timer-add').disabled = false; }
};
el('new').onclick = () => command('new_conversation');
async function poll() { await refresh(); setTimeout(poll, 2500); }
poll();
