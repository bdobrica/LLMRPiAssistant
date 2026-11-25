let muted = false;
let resetPending = false;
const slider = el('level');
const speaker = el('speaker-mute');
let actual = null;
let writing = false;
let editing = false;
let debounce;

function showVolume() {
  slider.disabled = actual === null || writing;
  speaker.disabled = slider.disabled || editing;
  speaker.textContent = actual === 0 ? 'Unmute speaker' : 'Mute speaker';
  if (!editing) {
    if (actual !== null) slider.value = actual;
    el('volume').textContent = actual === null ? 'Unavailable' : actual + '%';
    markSaved();
  }
}
const command = initPage(s => {
  if (resetPending && !s.reset_pending) el('message').textContent = 'New conversation ready.';
  resetPending = s.reset_pending;
  muted = s.muted;
  el('mute').disabled = false;
  el('mute').textContent = muted ? 'Unmute microphone' : 'Mute microphone';
  el('capture').textContent = muted ? 'Microphone closed · steady red' : s.capture_active ? 'Microphone capture active' : 'Capture unavailable · mute not confirmed';
  el('status').textContent = s.state === 'CAPTURE_ERROR' ? 'Microphone control needs attention' : s.reset_pending ? 'New conversation pending' : s.state === 'ALERT' ? 'Alert ringing · amber' : s.audio_check?.active ? 'Local audio check active' : s.busy ? 'Finishing request…' : s.state === 'FOLLOW_UP' ? 'Ready for a follow-up · green' : muted ? 'Muted' : s.capture_active ? 'Ready for wake word' : 'Microphone unavailable';
  actual = s.volume;
  showVolume();
  el('connection').textContent = s.online === true ? 'Internet reachable' : s.online === false ? 'Internet unavailable · local controls still work' : 'Internet status unknown';
}, () => {
  el('status').textContent = 'Device status unknown';
  el('capture').textContent = 'Capture status unknown';
  el('connection').textContent = '';
  el('mute').disabled = true;
  actual = null;
  editing = false;
  clearTimeout(debounce);
  showVolume();
});
el('stop').onclick = () => command('stop', null, 'Stopped. Already dispatched actions may still finish.');
el('mute').onclick = () => command('mute', !muted, 'Microphone setting updated.');
el('new').onclick = async () => {
  if (!window.confirm('Clear the current conversation and start a new one?')) return;
  const result = await command('new_conversation');
  if (result) el('message').textContent = result.reset_pending ? 'Waiting for the pending request to finish.' : 'New conversation ready.';
};
async function writeVolume(action, value) {
  if (writing || actual === null) return;
  writing = true;
  editing = false;
  showVolume();
  try {
    if (!await command(action, value)) actual = null;
  } finally {
    writing = false;
    showVolume();
  }
}
form.onsubmit = event => event.preventDefault();
slider.oninput = () => {
  clearTimeout(debounce);
  editing = true;
  speaker.disabled = true;
  el('volume').textContent = slider.value + '%';
};
slider.onchange = () => {
  clearTimeout(debounce);
  debounce = setTimeout(() => writeVolume('volume', Number(slider.value)), 180);
};
slider.onpointerup = () => { if (editing) slider.onchange(); };
slider.onpointercancel = () => { editing = false; showVolume(); };
speaker.onclick = () => writeVolume('speaker_mute', actual !== 0);
