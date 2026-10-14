import Flutter
import UIKit
import UserNotifications

/// Makes the app delegate the notification center's delegate.
///
/// Flet's AppDelegate never sets it, and flutter_local_notifications does not
/// either, so iOS never tells the plugin about a tap. FlutterAppDelegate
/// forwards the center's callbacks to every plugin registered as an
/// application delegate, which flutter_local_notifications is.
public class S6RemindersPlugin: NSObject, FlutterPlugin {
  public static func register(with registrar: FlutterPluginRegistrar) {
    if let delegate = UIApplication.shared.delegate as? UNUserNotificationCenterDelegate {
      UNUserNotificationCenter.current().delegate = delegate
      NSLog("S6Reminders: notification center delegate set")
    }
  }
}
