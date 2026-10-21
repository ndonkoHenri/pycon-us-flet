package io.github.ndonkohenri.a11ytree;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;

/**
 * Dumps the active window's accessibility tree as XML, with what {@code uiautomator dump} leaves out (#257).
 *
 * <p>{@code uiautomator dump} has no heading attribute, so this walks the window through {@link UiAutomation} and
 * writes {@code uiautomator dump}'s attributes plus {@code heading} ({@link AccessibilityNodeInfo#isHeading()}, what
 * TalkBack's Headings navigation moves by), {@code accessibility-focused}, {@code state-description} and
 * {@code hint}. {@code FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES} keeps TalkBack on while it runs.
 *
 * <p>Run by {@code tools/a11y_tree.py}: {@code am instrument -w -r io.github.ndonkohenri.a11ytree/.A11yTree}. The XML
 * is one line, in the result bundle's {@code xml} key; a failure is in its {@code error} key.
 */
public final class A11yTree extends Instrumentation {
    /** How long to wait for a window whose tree has more than its root, in milliseconds. */
    private static final long WAIT_MS = 10_000;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        try {
            result.putString("xml", dump());
            finish(Activity.RESULT_OK, result);
        } catch (Exception e) {
            result.putString("error", e.toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private String dump() throws Exception {
        UiAutomation automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        AccessibilityServiceInfo info = automation.getServiceInfo();
        // Without these, resource-id is empty and nodes that are not "important" are skipped.
        info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
        automation.setServiceInfo(info);
        // Flutter builds its semantics tree only once a service connects (F72), so the first look may find only
        // the FlutterView: wait until the root has children.
        long deadline = SystemClock.uptimeMillis() + WAIT_MS;
        while (true) {
            try {
                automation.waitForIdle(300, 2_000);
            } catch (java.util.concurrent.TimeoutException ignored) {
                // A screen that keeps animating is never idle; dump it anyway.
            }
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            if (root != null && (deepChildCount(root) > 1 || SystemClock.uptimeMillis() > deadline)) {
                StringBuilder xml = new StringBuilder("<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">");
                write(xml, root, 0);
                return xml.append("</hierarchy>").toString();
            }
            if (SystemClock.uptimeMillis() > deadline) {
                throw new IllegalStateException("no active window");
            }
            SystemClock.sleep(250);
        }
    }

    private static int deepChildCount(AccessibilityNodeInfo node) {
        int count = 0;
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                count += 1 + deepChildCount(child);
            }
        }
        return count;
    }

    private static void write(StringBuilder xml, AccessibilityNodeInfo node, int index) {
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        xml.append("<node");
        attr(xml, "index", String.valueOf(index));
        attr(xml, "text", node.getText());
        attr(xml, "resource-id", node.getViewIdResourceName());
        attr(xml, "class", node.getClassName());
        attr(xml, "package", node.getPackageName());
        attr(xml, "content-desc", node.getContentDescription());
        attr(xml, "state-description", node.getStateDescription());
        attr(xml, "hint", node.getHintText());
        attr(xml, "heading", node.isHeading());
        attr(xml, "checkable", node.isCheckable());
        attr(xml, "checked", node.isChecked());
        attr(xml, "clickable", node.isClickable());
        attr(xml, "enabled", node.isEnabled());
        attr(xml, "focusable", node.isFocusable());
        attr(xml, "focused", node.isFocused());
        attr(xml, "accessibility-focused", node.isAccessibilityFocused());
        attr(xml, "scrollable", node.isScrollable());
        attr(xml, "long-clickable", node.isLongClickable());
        attr(xml, "selected", node.isSelected());
        attr(xml, "visible-to-user", node.isVisibleToUser());
        attr(xml, "bounds", "[" + bounds.left + "," + bounds.top + "][" + bounds.right + "," + bounds.bottom + "]");
        xml.append(">");
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                write(xml, child, i);
            }
        }
        xml.append("</node>");
    }

    private static void attr(StringBuilder xml, String name, boolean value) {
        attr(xml, name, String.valueOf(value));
    }

    private static void attr(StringBuilder xml, String name, CharSequence value) {
        xml.append(' ').append(name).append("=\"");
        String text = value == null ? "" : value.toString();
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '&': xml.append("&amp;"); break;
                case '<': xml.append("&lt;"); break;
                case '>': xml.append("&gt;"); break;
                case '"': xml.append("&quot;"); break;
                default:
                    // A label's newline is escaped to keep the XML on one line, as am prints the result bundle
                    // line by line; other control characters are not allowed in XML 1.0 at all.
                    if (c == '\n' || c == '\r' || c == '\t') {
                        xml.append("&#").append((int) c).append(';');
                    } else if (c >= 0x20) {
                        xml.append(c);
                    }
            }
        }
        xml.append('"');
    }
}
