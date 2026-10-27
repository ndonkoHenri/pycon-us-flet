// Read the sponsor's name from Now's spotlight card, for maestro/journeys/spotlight_back.yaml.
//
// Reads `maestro.copiedText`, the card's one node: "Thanks to NVIDIA, a Visionary
// sponsor" (core.sponsors.thanks()). Keeps, in `output`:
// - spotlightName: the name as a regular expression that matches it whole (Maestro's
//   `text:` is one), its special characters escaped: "Anaconda, Inc" stays as it is;
//   empty when the card says something else.

function spotlightName(text) {
  var match = /^Thanks to (.+), an? .+ sponsor$/.exec(String(text || "").trim());
  if (!match) {
    return "";
  }
  return match[1].replace(/[.*+?^$()|[\]{}\\]/g, "\\$&");
}

output.spotlightName = spotlightName(maestro.copiedText);
console.log("spotlight: " + maestro.copiedText);
