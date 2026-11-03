// What the device's OS offers, for the flows whose steps depend on the Android API level
// (#953). Keeps, in `output.os`:
// - notificationPrompt: the OS asks the user before an app may notify. iOS always; Android
//   from API 33 (Android 13), which added the POST_NOTIFICATIONS runtime permission. Below
//   it the OS allows notifications, so the reminders primer has nothing to ask (D-395).
// - exactAlarmCard: a fresh install has exact alarms off, so Settings shows the Alarms &
//   reminders card. Android from API 34 (Android 14, which denies SCHEDULE_EXACT_ALARM
//   to new installs by default); iOS has no such card. Below 31 nothing needs a grant
//   (`exact_allowed()` is true). API 31 to 33 grant it by default; those images were not
//   run (docs/development.md, "The OS floors").
// - fieldHint: a text field's label and helper line reach the accessibility tree, so the
//   flow can read them. iOS always; Android from API 28, where Flutter's bridge sets the
//   node's hint text. Below it the field is an unnamed edit box (#952, #968).
// - confirmsCopy: the OS shows its own "copied" confirmation, so the app's SnackBar is
//   not on screen to check (D-263). Android from API 33 (Android 13, which added the
//   clipboard preview). iOS and Android below 13 show nothing, so the app's SnackBar is
//   the user's only confirmation and the flow asserts it (#972).
//
// The API level is `ANDROID_API`, which the runner passes with `-e ANDROID_API=<level>`
// (maestro/README.md, "Android API levels"): a flow cannot run `adb`. It defaults to 36,
// the newest, so a run on an older image that forgot it fails at the step the image
// lacks, as it did before, and never skips a check.

var android = maestro.platform == "android";
var api = Number(typeof ANDROID_API === "undefined" || !ANDROID_API ? 36 : ANDROID_API);

output.os = {
  api: api,
  notificationPrompt: !android || api >= 33,
  exactAlarmCard: android && api >= 34,
  fieldHint: !android || api >= 28,
  confirmsCopy: android && api >= 33,
};
console.log("os offers: " + JSON.stringify(output.os));
