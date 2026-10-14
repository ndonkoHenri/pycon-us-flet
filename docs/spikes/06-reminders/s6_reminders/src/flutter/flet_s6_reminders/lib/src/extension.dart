import 'package:flet/flet.dart';

import 'reminders.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "S6Reminders":
        return S6RemindersService(control: control);
      default:
        return null;
    }
  }
}
