// Ask the feed-pair server (tools/feed_pair.py) which side of its pair to serve.
//
// Runs on the laptop, as Maestro does, so it reaches the server at the laptop's own
// loopback whatever the device reaches it at.
// env:
// - CONTROL_URL: the server, as the laptop reaches it (http://127.0.0.1:<port>);
// - SIDE: "reset" serves the old feed, "swap" the new one.
// Keeps, in `output`: side, the side the server says it now serves ("old" or "new").

var response = http.post(CONTROL_URL + "/" + SIDE, { body: "" });
if (!response.ok) {
  throw new Error(
    "The feed-pair server at " + CONTROL_URL + " answered " + response.status +
      " to " + SIDE + ": is uv run python -m tools.feed_pair running?"
  );
}
output.side = response.body;
