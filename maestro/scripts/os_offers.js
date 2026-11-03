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
};
console.log("os offers: " + JSON.stringify(output.os));
