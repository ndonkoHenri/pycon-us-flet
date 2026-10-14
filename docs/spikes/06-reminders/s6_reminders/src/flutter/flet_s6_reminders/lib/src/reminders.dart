// S6: the E3 API of docs/flet-gaps-and-extensions.md §4.1 over
// flutter_local_notifications 22.3.1, small enough to read in one go.
import 'package:flet/flet.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/timezone.dart' as tz;

class S6RemindersService extends FletService {
  S6RemindersService({required super.control});

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static const AndroidNotificationDetails _android = AndroidNotificationDetails(
    'reminders',
    'Reminders',
    channelDescription: 'Reminders before saved sessions',
    importance: Importance.high,
    priority: Priority.high,
  );

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }

  AndroidFlutterLocalNotificationsPlugin? get _androidPlugin =>
      _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();

  IOSFlutterLocalNotificationsPlugin? get _iosPlugin =>
      _plugin.resolvePlatformSpecificImplementation<
          IOSFlutterLocalNotificationsPlugin>();

  void _onResponse(NotificationResponse response) {
    debugPrint("S6Reminders tap id=${response.id} payload=${response.payload}");
    control.triggerEvent(
        "tap", {"id": response.id, "payload": response.payload});
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "initialize":
        // No permission prompt here: the app asks in context (D-61).
        await _plugin.initialize(
          settings: const InitializationSettings(
            // A monochrome drawable from this extension's Android module:
            // the launcher icon would show as a plain disc in the status bar.
            android: AndroidInitializationSettings('ic_stat_s6'),
            iOS: DarwinInitializationSettings(
              requestAlertPermission: false,
              requestBadgePermission: false,
              requestSoundPermission: false,
            ),
          ),
          onDidReceiveNotificationResponse: _onResponse,
        );
        final details = await _plugin.getNotificationAppLaunchDetails();
        final response = details?.notificationResponse;
        return {
          "launched_by_tap": details?.didNotificationLaunchApp ?? false,
          "id": response?.id,
          "payload": response?.payload,
        };
      case "request_permission":
        if (defaultTargetPlatform == TargetPlatform.android) {
          return await _androidPlugin?.requestNotificationsPermission();
        }
        return await _iosPlugin?.requestPermissions(
            alert: true, badge: true, sound: true);
      case "permission_status":
        if (defaultTargetPlatform == TargetPlatform.android) {
          return {
            "enabled": await _androidPlugin?.areNotificationsEnabled(),
            "exact": await _androidPlugin?.canScheduleExactNotifications(),
          };
        }
        final options = await _iosPlugin?.checkPermissions();
        return {"enabled": options?.isEnabled, "exact": null};
      case "request_exact":
        return await _androidPlugin?.requestExactAlarmsPermission();
      case "zoned_schedule":
        // One instant, in UTC: no time-zone database and no device zone
        // lookup (gaps doc §4.1, "Time").
        final at = tz.TZDateTime.from(DateTime.parse(args["at"]), tz.UTC);
        try {
          await _plugin.zonedSchedule(
            id: args["id"],
            title: args["title"],
            body: args["body"],
            scheduledDate: at,
            notificationDetails: const NotificationDetails(
              android: _android,
              iOS: DarwinNotificationDetails(),
            ),
            androidScheduleMode: args["exact"] == true
                ? AndroidScheduleMode.exactAllowWhileIdle
                : AndroidScheduleMode.inexactAllowWhileIdle,
            payload: args["payload"],
          );
          return {"ok": true, "code": null};
        } on PlatformException catch (e) {
          return {"ok": false, "code": e.code};
        }
      case "get_pending":
        final pending = await _plugin.pendingNotificationRequests();
        return pending
            .map((p) => {
                  "id": p.id,
                  "title": p.title,
                  "body": p.body,
                  "payload": p.payload,
                })
            .toList();
      case "cancel_all":
        await _plugin.cancelAll();
        return null;
      default:
        throw Exception("Unknown S6Reminders method: $name");
    }
  }
}
