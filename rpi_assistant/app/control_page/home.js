let muted = false;
let resetPending = false;
const command = initPage(s => {
  if (resetPending && !s.reset_pending) el('message').textContent = 'New conversation ready.';
  resetPending = s.reset_pending;
  muted = s.muted;
  el('mute').disabled = false;
  el('mute').textContent = muted ? 'Unmute microphone' : 'Mute microphone';
  el('capture').textContent = muted ? 'Microphone closed · steady red' : s.capture_active ? 'Microphone capture active' : 'Capture unavailable · mute not confirmed';
  el('status').textContent = s.state === 'CAPTURE_ERROR' ? 'Microphone control needs attention' : s.reset_pending ? 'New conversation pending' : s.state === 'ALERT' ? 'Alert ringing · amber' : s.audio_check?.active ? 'Local audio check active' : s.busy ? 'Finishing request…' : s.state === 'FOLLOW_UP' ? 'Ready for a follow-up · green' : muted ? 'Muted' : s.capture_active ? 'Ready for wake word' : 'Microphone unavailable';
  el('volume').textContent = s.volume === null ? 'Unavailable' : s.volume + '%';
  el('connection').textContent = s.online === true ? 'Internet reachable' : s.online === false ? 'Internet unavailable · local controls still work' : 'Internet status unknown';
}, () => {
  el('status').textContent = 'Device status unknown';
  el('capture').textContent = 'Capture status unknown';
  el('connection').textContent = '';
  el('mute').disabled = true;
});
el('stop').onclick = () => command('stop', null, 'Stopped. Already dispatched actions may still finish.');
el('mute').onclick = () => command('mute', !muted, 'Microphone setting updated.');
el('new').onclick = async () => {
  const result = await command('new_conversation');
  if (result) el('message').textContent = result.reset_pending ? 'Waiting for the pending request to finish.' : 'New conversation ready.';
};
el('down').onclick = () => command('volume_down');
el('up').onclick = () => command('volume_up');
form.onsubmit = async event => {
  event.preventDefault();
  const level = el('level').value;
  if (level && await command('volume', Number(level)) && el('level').value === level) markSaved();
};
