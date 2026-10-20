import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';

import 'scanner.dart';

class Extension extends FletExtension {
  @override
  Widget? createWidget(Key? key, Control control) {
    switch (control.type) {
      case "S8Scanner":
        return S8ScannerControl(key: key, control: control);
      default:
        return null;
    }
  }
}
