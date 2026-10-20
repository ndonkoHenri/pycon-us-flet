// S8 throwaway extension (docs/spikes/08-scanner.md): a camera preview that
// reports barcodes, over mobile_scanner 7.4.2. Written from the package's
// pub.dev API and flet-camera only (D-99). Imports widgets.dart, never
// material.dart: the error and placeholder builders below replace
// mobile_scanner's defaults, which use Colors and Icons (the gate, gaps doc §3).
import 'dart:async';

import 'package:flet/flet.dart';
import 'package:flutter/widgets.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

class S8ScannerControl extends StatefulWidget {
  final Control control;

  const S8ScannerControl({super.key, required this.control});

  @override
  State<S8ScannerControl> createState() => _S8ScannerControlState();
}

class _S8ScannerControlState extends State<S8ScannerControl>
    with WidgetsBindingObserver {
  late final MobileScannerController _controller;
  late bool _paused;
  late bool _torch;
  final Stopwatch _clock = Stopwatch()..start();
  String? _lastError;

  @override
  void initState() {
    super.initState();
    _paused = widget.control.getBool("paused", false)!;
    _torch = widget.control.getBool("torch", false)!;
    final formats = (widget.control.get<List>("formats") ?? ["qrCode"])
        .map((f) => parseEnum(BarcodeFormat.values, f as String,
            BarcodeFormat.qrCode)!)
        .toList();
    // The widget starts the camera after it attaches when autoStart is true.
    // A controller passed in gets no lifecycle handling from the widget,
    // so this state observes the app lifecycle itself (below).
    _controller = MobileScannerController(
      autoStart: !_paused,
      formats: formats,
      torchEnabled: _torch,
    );
    _controller.addListener(_onState);
    WidgetsBinding.instance.addObserver(this);
    widget.control.addInvokeMethodListener(_invokeMethod);
    _log("init paused=$_paused torch=$_torch formats=$formats");
  }

  void _log(String message) {
    debugPrint("S8 dart t=${_clock.elapsedMilliseconds} $message");
  }

  void _onState() {
    final value = _controller.value;
    final error = value.error;
    final code = error?.errorCode.name;
    if (code != _lastError) {
      _lastError = code;
      if (error != null) {
        _log("error $code");
        widget.control.triggerEvent("error", {
          "code": code,
          "message": error.errorDetails?.message ?? error.errorCode.message,
        });
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // The widget's own handling (useAppLifecycleState) applies only to the
    // controller it creates. Stop on inactive (releases the camera, as the
    // widget does) and start again on resume, unless paused.
    _log("lifecycle ${state.name}");
    switch (state) {
      case AppLifecycleState.inactive:
        unawaited(_controller.stop());
      case AppLifecycleState.resumed:
        if (!_paused && _controller.value.hasCameraPermission) {
          unawaited(_controller.start());
        }
      default:
        break;
    }
  }

  @override
  void didUpdateWidget(covariant S8ScannerControl oldWidget) {
    super.didUpdateWidget(oldWidget);
    final paused = widget.control.getBool("paused", false)!;
    if (paused != _paused) {
      _paused = paused;
      _log("paused=$paused");
      unawaited(paused ? _controller.stop() : _controller.start());
    }
    final torch = widget.control.getBool("torch", false)!;
    if (torch != _torch) {
      _torch = torch;
      final state = _controller.value.torchState;
      _log("torch=$torch state=${state.name}");
      if ((state == TorchState.on) != torch &&
          state != TorchState.unavailable) {
        unawaited(_controller.toggleTorch());
      }
    }
  }

  void _onDetect(BarcodeCapture capture) {
    for (final barcode in capture.barcodes) {
      _log("detect ${barcode.format.name}");
      widget.control.triggerEvent("detect", {
        "raw_value": barcode.rawValue,
        "format": barcode.format.name,
      });
    }
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "analyze_image":
        final capture = await _controller.analyzeImage(args["path"]);
        return capture?.barcodes.map((b) => b.rawValue).toList() ?? [];
      default:
        throw Exception("Unknown S8Scanner method: $name");
    }
  }

  @override
  void dispose() {
    _log("dispose");
    widget.control.removeInvokeMethodListener(_invokeMethod);
    WidgetsBinding.instance.removeObserver(this);
    _controller.removeListener(_onState);
    unawaited(_controller.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Placeholder and error draw a plain box: the app shows the message from
    // on_error with its own Material controls, so nothing here needs Material.
    // SizedBox.expand: a ColoredBox with no child is as small as its
    // constraints allow, which in a Column is zero wide (the first build).
    const blank = SizedBox.expand(child: ColoredBox(color: Color(0xFF000000)));
    return LayoutControl(
      control: widget.control,
      child: MobileScanner(
        controller: _controller,
        onDetect: _onDetect,
        placeholderBuilder: (context) => blank,
        errorBuilder: (context, error) => blank,
      ),
    );
  }
}
