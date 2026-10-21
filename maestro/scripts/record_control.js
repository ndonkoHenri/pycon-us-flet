// Record one control fling of maestro/regression/fling_after_sheet.yaml and print it.
//
// A control is the trials' fling with no sheet just before it: from the rest (where
// "Show N sessions" leaves the list), a while after the sheet has gone. The flow runs it
// three times, from the same rest each time.
//
// Reads, from `output`:
// - restRow: the top row at the rest, read before this control's fling;
// - topRows: the first four rows on screen once the fling had ended
//   (subflows/top_rows.yaml), in order, topRows[0] being the top row.
// Keeps, in `output`:
// - controls: every control so far, as {rest, top, rows};
// - controlsOk: every control started from the first control's rest and left it, and
//   any two are near (scripts/record_fling.js): one's top row is among the other's
//   rows, so they ended no more than three rows apart. The flow fails before the trials
//   otherwise: the controls then measure nothing a trial can be held to.

function near(a, b) {
  return a.length > 0 && b.length > 0 && (b.indexOf(a[0]) !== -1 || a.indexOf(b[0]) !== -1);
}

function recordControl(o) {
  var rows = (o.topRows || []).filter(function (row) {
    return !!row;
  });
  var control = { rest: o.restRow, top: rows.length ? rows[0] : "", rows: rows };
  var controls = (o.controls || []).concat([control]);
  var ok = true;
  for (var i = 0; i < controls.length; i++) {
    var c = controls[i];
    if (!c.top || c.rest !== controls[0].rest || c.rows.indexOf(c.rest) !== -1) {
      ok = false;
    }
    for (var k = 0; k < i; k++) {
      if (!near(c.rows, controls[k].rows)) {
        ok = false;
      }
    }
  }
  return { controls: controls, controlsOk: ok, control: control };
}

var recorded = recordControl(output);
output.controls = recorded.controls;
output.controlsOk = recorded.controlsOk;

console.log(
  "control " + recorded.controls.length + ": from \"" + recorded.control.rest +
  "\" to \"" + (recorded.control.top || "-") + "\"" +
  (recorded.controlsOk ? "" : " (the controls disagree, or one did not move)")
);
