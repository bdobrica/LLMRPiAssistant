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
  el('status').textContent = s.state === 'CAPTURE_ERROR' ? 'Microphone control needs attention' : s.reset_pending ? 'New conversation pending · previous request finishing' : s.busy ? 'Finishing request…' : s.state === 'FOLLOW_UP' ? 'Ready for a follow-up · green' : muted ? 'Muted' : s.capture_active ? 'Ready for wake word' : 'Microphone unavailable';
  el('volume').textContent = s.volume === null ? 'Unavailable' : s.volume + '%';
  if(s.error) el('message').textContent = s.error;
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
  try { const data = await request('/control', {method:'POST',headers:{'Content-Type':'application/json','X-Assistant-Control':'1'},body:JSON.stringify({action,value})}); show(data); el('message').textContent = data.message || (action === 'new_conversation' ? (data.reset_pending ? 'Will start fresh when the pending request finishes.' : 'New conversation ready.') : action === 'stop' ? 'Stopped. Already dispatched actions may still finish.' : 'Microphone setting updated.'); }
  catch(e) { el('message').textContent = e.message; await refresh(); }
}
el('stop').onclick = () => command('stop');
el('mute').onclick = () => command('mute', !muted);
el('down').onclick = () => command('volume_down');
el('up').onclick = () => command('volume_up');
el('set').onclick = () => {const v=Number(el('level').value); if(Number.isInteger(v)&&v>=0&&v<=100) command('volume',v); else el('message').textContent='Enter a whole number from 0 to 100.';};
el('new').onclick = () => command('new_conversation');
async function poll() { await refresh(); setTimeout(poll, 2500); }
poll();
