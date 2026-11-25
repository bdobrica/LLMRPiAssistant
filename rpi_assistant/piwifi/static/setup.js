'use strict';
const networks = document.getElementById('network');
const manualName = document.getElementById('ssid');
function chooseNetwork() {
  const manual = networks.selectedOptions[0]?.dataset.manual === 'true';
  document.getElementById('manual-network').hidden = !manual;
  manualName.disabled = !manual || networks.disabled;
  manualName.required = manual;
  networks.required = !manual;
  if (manual) networks.removeAttribute('name');
  else networks.name = 'ssid';
}
networks.addEventListener('change', chooseNetwork);
chooseNetwork();
document.getElementById('show-password').addEventListener('change', (event) => {
  document.getElementById('password').type = event.target.checked ? 'text' : 'password';
});
