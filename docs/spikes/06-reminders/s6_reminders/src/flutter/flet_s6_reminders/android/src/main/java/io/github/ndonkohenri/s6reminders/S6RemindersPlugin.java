package io.github.ndonkohenri.s6reminders;

import androidx.annotation.NonNull;

import io.flutter.embedding.engine.plugins.FlutterPlugin;

/**
 * A no-op plugin class. Flutter builds a plugin's android/ folder only when the
 * pubspec names a pluginClass, and S6 needs the module for its manifest alone.
 */
public class S6RemindersPlugin implements FlutterPlugin {
    @Override
    public void onAttachedToEngine(@NonNull FlutterPluginBinding binding) {}

    @Override
    public void onDetachedFromEngine(@NonNull FlutterPluginBinding binding) {}
}
