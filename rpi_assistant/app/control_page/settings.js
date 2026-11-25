const privacy = Boolean(el('privacy-delete'));
let lastSettings;
let loadedRevision;
const keys = ['openai', 'weather', 'ipgeolocation'];
function loadSettings(s) {
  if (privacy) {
    el('conversation-logging').checked = s.conversation_logging;
  } else {
    el('follow-up').value = s.follow_up_seconds;
    el('timezone').value = s.reminder_timezone;
    el('weather-city').value = s.weather_city;
    for (const key of keys) el(key + '-key').value = '';
    el('clear-weather-key').checked = el('clear-ipgeolocation-key').checked = false;
  }
  loadedRevision = s.revision;
  markSaved();
}
const command = initPage(s => {
  if (!s.settings) return;
  lastSettings = s.settings;
  if (loadedRevision === undefined) form.querySelector('fieldset').disabled = false;
  if (loadedRevision !== lastSettings.revision && !hasEdits()) loadSettings(lastSettings);
  el('settings-save').disabled = !lastSettings.revision;
  el('settings-undo').disabled = !lastSettings.can_undo;
  el('settings-message').textContent = lastSettings.error ||
    (loadedRevision !== lastSettings.revision ? 'Settings changed elsewhere. Reload to use the latest values.' : '');
  if (privacy) {
    if (s.privacy) el('privacy-status').textContent = (s.privacy.conversation_logging ? 'Conversation logging enabled. ' : 'Conversation logging off. ') +
      s.privacy.retention_days + '-day retention, ' + (s.privacy.max_bytes / 1048576).toFixed(2) + ' MiB file cap. ' + (s.privacy.error || '');
  } else {
    for (const key of keys) el(key + '-key-state').textContent = lastSettings.keys_configured[key + '_key'] ? 'Key configured (hidden)' : 'No key configured';
    el('weather-location').textContent = lastSettings.weather_location ? 'Last resolved city: ' + lastSettings.weather_location : 'City will be resolved on the next weather request.';
    if (s.audio_check) {
      el('audio-check').textContent = s.audio_check.message;
      el('check-stop').disabled = !s.audio_check.active;
      el('check-speaker').disabled = s.audio_check.active || s.busy || s.state === 'ALERT';
      el('check-microphone').disabled = el('check-speaker').disabled || !s.capture_active || s.muted;
    }
  }
});
function discardEdits() {
  return !hasEdits() || window.confirm('Discard your unsaved changes?');
}
el('settings-reload').onclick = () => {
  if (lastSettings && discardEdits()) loadSettings(lastSettings);
};
async function save(undo) {
  if (!lastSettings || (undo && !discardEdits())) return;
  const value = {revision: loadedRevision};
  if (!undo && privacy) value.conversation_logging = el('conversation-logging').checked;
  if (!undo && !privacy) {
    value.follow_up_seconds = Number(el('follow-up').value);
    value.reminder_timezone = el('timezone').value.trim();
    value.weather_city = el('weather-city').value.trim();
    for (const key of keys) value[key + '_key'] = el(key + '-key').value.trim();
    value.clear_weather_key = el('clear-weather-key').checked;
    value.clear_ipgeolocation_key = el('clear-ipgeolocation-key').checked;
  }
  const fields = form.querySelector('fieldset');
  fields.disabled = true;
  try {
    const data = await command(undo ? 'settings_undo' : 'settings_apply', value);
    if (data) loadSettings(data.settings);
  } finally { fields.disabled = false; }
}
form.onsubmit = event => { event.preventDefault(); save(false); };
el('settings-undo').onclick = () => save(true);
if (privacy) {
  el('privacy-delete').onclick = async () => {
    if (!window.confirm("Delete conversation memory and this installation's logs/audio? Saved household data and settings stay.")) return;
    el('privacy-delete').disabled = true;
    try { await command('privacy_delete', {confirm:true}); }
    finally { el('privacy-delete').disabled = false; }
  };
} else {
  el('check-speaker').onclick = () => command('audio_check', 'speaker');
  el('check-microphone').onclick = () => command('audio_check', 'microphone');
  el('check-stop').onclick = () => command('stop', null, 'Audio check stopped.');
}
