// Record one trial of maestro/regression/fling_after_sheet.yaml and print it.
//
// Reads what top_slot.yaml left in `output` after the fling (topRow, topSlot), and
// where "Show N sessions" leaves the list with no fling (restRow, restSlot), read once
// before the trials. A trial is:
// - "moved": the list left the slot it rested in, as a full fling does;
// - "short": it stayed in that slot, on another row (the fling was cut short);
// - "none": the same row is at the top, so the list did not scroll at all.
// Adds it to output.counts and output.summary; the flow fails at the end when a trial
// was not "moved".

var trial = (output.trial || 0) + 1;
output.trial = trial;

var kind;
if (output.topSlot !== output.restSlot) {
  kind = "moved";
} else if (output.topRow === output.restRow) {
  kind = "none";
} else {
  kind = "short";
}

var counts = output.counts || { moved: 0, short: 0, none: 0 };
counts[kind] += 1;
output.counts = counts;
output.lost = counts.short + counts.none;
output.summary =
  counts.moved + " moved, " + counts.short + " short, " + counts.none + " none, of " + trial;

console.log(
  "fling " + trial + ": " + kind +
  " (rested at " + output.restSlot + ", top after the fling " + (output.topSlot || "-") + ")"
);
