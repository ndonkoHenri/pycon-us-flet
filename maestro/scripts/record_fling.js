// Record one trial of maestro/regression/fling_after_sheet.yaml and print it.
//
// Reads, from `output`:
// - startSlot: the slot at the top before the trials (the now slot), and trialStart,
//   the slot at the top as this trial began;
// - restRow, restSlot: where "Show N sessions" leaves the list with no fling;
// - controlSlot: where the same fling took the list from there, with no sheet before it;
// - topRow, topSlot: what top_slot.yaml read once the trial's fling had ended.
// A trial is:
// - "moved": the list ended in the control's slot, as a full fling does;
// - "short": it ended elsewhere, on another row than the rest's (cut short);
// - "none": the rest's row is on top, so the list did not scroll at all;
// - "invalid": the trial began elsewhere (the fake clock moved the now slot) or no row
//   could be read, so it says nothing.
// Adds it to output.counts and output.summary; the flow fails at the end unless every
// trial was "moved".

var trial = (output.trial || 0) + 1;
output.trial = trial;

var kind;
if (output.trialStart !== output.startSlot || !output.topSlot) {
  kind = "invalid";
} else if (output.topSlot === output.controlSlot) {
  kind = "moved";
} else if (output.topRow === output.restRow) {
  kind = "none";
} else {
  kind = "short";
}

var counts = output.counts || { moved: 0, short: 0, none: 0, invalid: 0 };
counts[kind] += 1;
output.counts = counts;
output.lost = counts.short + counts.none + counts.invalid;
output.summary =
  counts.moved + " moved, " + counts.short + " short, " + counts.none + " none, " +
  counts.invalid + " invalid, of " + trial;

console.log(
  "fling " + trial + ": " + kind +
  " (began at " + output.trialStart + ", top after the fling " + (output.topSlot || "-") +
  "; the control went to " + output.controlSlot + ")"
);
