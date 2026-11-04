// Record one trial of maestro/regression/fling_after_sheet.yaml and print it.
//
// Reads, from `output`:
// - startSlot: the slot at the top before the trials (the now slot), and trialStart,
//   the slot at the top as this trial began;
// - restRow: where "Show N sessions" leaves the list with no fling;
// - controls: the control flings (scripts/record_control.js), each with the first four
//   rows where it stopped;
// - dragRows: the rows a slow swipe, with no velocity, ends on;
// - topRows: the first four rows once the trial's fling had ended
//   (subflows/top_rows.yaml), topRows[0] being the top row.
// A trial is:
// - "invalid": the trial began elsewhere (the fake clock moved the now slot) or no row
//   could be read, so it says nothing;
// - "moved": it is near a control: its top row is among the control's rows, or the
//   control's top row among its own, so it ended no more than three rows from where a
//   full fling ends, before or past it. The rows, not their slot: 3:00 PM, where a full
//   fling ends, is about 20 rows deep with Open space shown, so a fling cut short by many
//   rows can still end in it;
// - "none": the rest's row is on top, so the list did not scroll at all;
// - "dragged": it is near where the slow swipe ended: it lost its velocity, which the
//   Android emulator's flings also do with no sheet before them (#1012);
// - "short": it ended anywhere else, further from the controls (short of them, or
//   rarely past them).
// A row is its phrase (D-190), which holds its time and room, so two rows never share one.
// Adds it to output.counts and output.summary; the flow fails at the end on any "short",
// "none" or "invalid", or when more than half were "dragged".

function near(a, b) {
  return a.length > 0 && b.length > 0 && (b.indexOf(a[0]) !== -1 || a.indexOf(b[0]) !== -1);
}

function classify(o) {
  var rows = (o.topRows || []).filter(function (row) {
    return !!row;
  });
  if (o.trialStart !== o.startSlot || rows.length === 0) {
    return "invalid";
  }
  var controls = o.controls || [];
  for (var i = 0; i < controls.length; i++) {
    if (near(rows, controls[i].rows)) {
      return "moved";
    }
  }
  if (rows[0] === o.restRow) {
    return "none";
  }
  if (near(rows, o.dragRows || [])) {
    return "dragged";
  }
  return "short";
}

var trial = (output.trial || 0) + 1;
output.trial = trial;

var kind = classify(output);
var counts = output.counts || { moved: 0, dragged: 0, short: 0, none: 0, invalid: 0 };
counts[kind] += 1;
output.counts = counts;
output.lost = counts.short + counts.none + counts.invalid;
output.dragged = counts.dragged;
output.summary =
  counts.moved + " moved, " + counts.dragged + " dragged, " + counts.short + " short, " +
  counts.none + " none, " +
  counts.invalid + " invalid, of " + trial;

console.log(
  "fling " + trial + ": " + kind +
  " (began at " + output.trialStart + "; top row after the fling \"" +
  ((output.topRows || [])[0] || "-") + "\"; the first control ended on \"" +
  (((output.controls || [])[0] || {}).top || "-") + "\")"
);
