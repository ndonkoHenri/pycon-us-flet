// The F8 wrapper owns this loopback control port; Maestro runs this on the laptop.
var response = http.post(CONTROL_URL + '/' + ACTION, {body: ''});
if (!response.ok) {
  throw new Error('F8 listener action failed: ' + ACTION + ': ' + response.status);
}
