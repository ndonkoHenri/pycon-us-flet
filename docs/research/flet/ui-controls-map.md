# PyCon US mobile (Ionic 8 / Angular 17 / Capacitor 7) -> Flet 1.1.0-dev: UI control map

Source of truth for Flet: local monorepo `<flet checkout>`
(HEAD `7688de3`, "1.1.0" section at top of `CHANGELOG.md`). Every class, property and
method named below was read from the Python SDK at
`sdk/python/packages/flet/src/flet/` (abbreviated `SDK/` below) or from an extension
package under `sdk/python/packages/flet-*`. Anything not found there is marked **GAP**.

Ionic app: `excluded/pycon-us-mobile/src/app`
(abbreviated `APP/`).

Status legend: **exists** = direct control with the needed props/events; **partial** = can
be reproduced by composing existing controls, with a caveat; **gap** = nothing in the local
tree does this; extension or custom code required.

---

## 0. Architectural decisions this map assumes

| Ionic concept | Flet (declarative) | Where verified |
|---|---|---|
| `ion-app` + Angular router, `ion-router-outlet` | `ft.run(lambda page: page.render_views(App))`; `App` returns `ft.Router([...ft.Route(...)], manage_views=True)`; each page component returns an `ft.View(route=..., appbar=..., controls=[...])`. `manage_views=True` gives swipe-back, system back and AppBar implicit back (`AppBar.automatically_imply_leading=True` -> Dart `automaticallyImplyLeading`). | `SDK/components/router.py:593-660` (`Router(routes, not_found, manage_views)`), `Route` dataclass fields `path, index, component, children, loader, outlet, modal, recursive` (`router.py:45-108`); hooks `use_route_params`, `use_route_location`, `use_view_path`, `use_route_outlet`, `use_route_loader_data`, `is_route_active` (`router.py:340-430`); `Page.render_views()` (`SDK/controls/page.py:776`), `Page.navigate()` sync wrapper over `push_route()` (`page.py:1094`, `1013`), `Page.pop_views_until()` (`page.py:1108`); Dart `packages/flet/lib/src/controls/app_bar.dart:26`. Examples: `sdk/python/examples/apps/router/{app_drawer,nested_outlet_views,modal_routes,layout_outlet,loaders}/main.py`. |
| Angular services / RxJS state | `@ft.observable` dataclasses for conference data + favorites; `ft.use_state` for ephemeral UI state; `ft.use_effect` for async loading; `ft.use_memo` for filtered lists. | `SDK/components/observable.py:18` (`observable`, `Observable`, `ObservableList`, `ObservableDict`), `components/hooks/use_state.py:48`, `use_effect.py:42` (`setup, dependencies, cleanup`), `use_memo.py:25`, `use_callback.py`, `use_ref.py`, `use_context.py`. Maintainer skill: `.agents/skills/imperative-to-declarative-flet/SKILL.md`. |
| Ionic overlay controllers | `ft.use_dialog(dialog_or_None)` hook (portals any `DialogControl` to the page overlay) or imperative `page.show_dialog()` / `page.pop_dialog()`. | `SDK/components/hooks/use_dialog.py:62`, `SDK/controls/base_page.py:402,427`, `SDK/controls/dialog_control.py` (`DialogControl.open`, `on_dismiss`). Cookbook `website/docs/cookbook/declarative-dialogs.md`. |
| `ion-modal` with `presentingElement` (card modal) / `ModalController.create({component})` | `ft.Route(path=..., component=..., modal=True)` + component returns `ft.View(fullscreen_dialog=True, ...)`; deep-linkable. Result passing ("onWillDismiss data"): keep selection in an observable model or `page.pop_views_until(route, result=...)`. | `router.py:107` (`modal`), `SDK/controls/core/view.py` (`fullscreen_dialog: bool`), example `apps/router/modal_routes/main.py`. |
| iOS/Android look | `page.adaptive = True` + `adaptive=True` on `AdaptiveControl`s (AppBar, NavigationBar, ListTile, Switch, Checkbox, TextField, AlertDialog, Dismissible, Tabs, Card, ...). `View.appbar` accepts `AppBar | CupertinoAppBar`, `View.navigation_bar` accepts `NavigationBar | CupertinoNavigationBar`. | `SDK/controls/adaptive_control.py`, `core/view.py` (`appbar`, `navigation_bar` type hints), Dart `view.dart:240` (`CupertinoPageScaffold` branch). Cookbook `website/docs/cookbook/adaptive-apps.md`. |

Material and Cupertino come from `material_ui ^1.6.0` / `cupertino_ui ^1.1.2`
(`packages/flet/pubspec.yaml:27,39`). Any extension proposed below must follow
`.agents/skills/implement-flet-extension/SKILL.md` (no `package:flutter/material.dart`).

---

## 1. Ionic component -> Flet control map

Counts are tag occurrences in `APP/**/*.html` (grep `<ion-...`).

### 1.1 Layout and page chrome

| Ionic | n | Flet | Key properties / events | Status | Notes |
|---|---|---|---|---|---|
| `ion-app` | 1 | `ft.Page` (one per session) + `ft.View` stack | `page.theme`, `page.dark_theme`, `page.theme_mode`, `page.adaptive`, `page.views` | exists | `SDK/controls/base_page.py:159-181`. |
| `ion-header` + `ion-toolbar` + `ion-title` + `ion-buttons` | 36/48/31/42 | `ft.AppBar` (or `ft.CupertinoAppBar`) on `View.appbar` | `leading`, `title`, `actions: list[Control]`, `center_title`, `bgcolor`, `elevation_on_scroll`, `toolbar_height`, `automatically_imply_leading`, `force_material_transparency`; Cupertino: `trailing` (single control), `large`, `previous_page_title`, `transition_between_routes` | exists | `SDK/controls/material/app_bar.py`, `cupertino/cupertino_app_bar.py`. Second toolbar rows (search bar / segment under the title as in `schedule.html`, `conference-map.page.html`) are not an AppBar `bottom` slot - **partial**: there is no `AppBar.bottom`; put the second row as the first child of `View.controls` (View is a Column) or use `toolbar_height` + a `Column` as `title`. |
| `ion-menu-button` | 27 | `ft.IconButton(ft.Icons.MENU, on_click=lambda: page.show_drawer())` as `AppBar.leading` | `Page.show_drawer()`, `close_drawer()`, `show_end_drawer()` (`base_page.py:493-517`); also `View.show_drawer()` | exists | Example `apps/declarative/navigation_drawer/main.py`. With `manage_views=True` and a non-root view, `automatically_imply_leading` shows a back arrow instead, so the hamburger must be explicit on root views only. |
| `ion-back-button [defaultHref]` | 4 | implicit: `AppBar.automatically_imply_leading=True` (default) with `Router(manage_views=True)`; `View.can_pop`, `View.on_confirm_pop` + `View.confirm_pop()` for intercepting | | exists | `core/view.py` (`can_pop`, `on_confirm_pop`, `confirm_pop`), Dart `view.dart:282` `PopScope`. `defaultHref` (deep-link with no stack) is handled by Router: it rebuilds the full chain from URL (`router.py` `_build_view_level`). |
| `ion-content` (scroll area, `fullscreen`, `scrollEvents`/`(ionScroll)` title-fade, `[scrollY]=false`) | 38 | `ft.View` itself is a `ScrollableControl`: `View.scroll=ft.ScrollMode.AUTO`, `View.on_scroll` (`OnScrollEvent.pixels`, `.max_scroll_extent`, `.event_type: ScrollType`), `View.scroll_to(offset|delta|scroll_key)`; or a `ft.ListView(expand=True)` child | `padding` (default `Padding.all(10)` - set `0` to mimic Ionic), `bgcolor`, `spacing` | exists | `core/view.py:38` `class View(ScrollableControl, LayoutControl)`, `SDK/controls/scrollable_control.py:197-262` (`OnScrollEvent`), `:343-381`, `:386` (`scroll_to`). `ScrollType` = `START/UPDATE/END/USER/OVERSCROLL` (`scrollable_control.py:26-55`). Title fade on scroll (`showTitle = scrollTop > 100`) = `on_scroll` + `use_state`. |
| `ion-footer` | 6 | `View.bottom_appbar=ft.BottomAppBar(content=..., bgcolor, padding, elevation, border_radius)`; or `ft.Pagelet(bottom_appbar=..., bottom_sheet=...)` | | exists | `material/bottom_app_bar.py:39-110`, `core/pagelet.py`. Dart `view.dart:219`: `bottomNavigationBar: navigation_bar ?? bottom_appbar` - a View shows **one** of them; see tabs row below. |
| `ion-grid` / `ion-row` / `ion-col` | 5/12/14 | `ft.ResponsiveRow(columns=12, controls=[... col={...}])`, `Control.col`, `breakpoints`; or plain `ft.Row`/`ft.Column` | `ResponsiveRow.columns`, `spacing`, `run_spacing`, `breakpoints: dict[ResponsiveRowBreakpoint|str, Number]` | exists | `core/responsive_row.py:54-104`, `SDK/controls/control.py:59` (`col: ResponsiveNumber = 12`). `ion-col size="5"/"7"` (redemption footer) -> `col=5` / `col=7`. |
| `ion-split-pane` (permanent side menu on tablets) | 1 | **compose**: `page.width` (`base_page.py:255`) + `page.on_resize` (`:218`, `PageResizeEvent.width/height`) -> wide: `ft.Row([ft.NavigationRail(extended=True, ...)` or a fixed-width `Container(width=304, content=<drawer content>)`, `ft.VerticalDivider(width=1)`, `Column(expand=True, controls=[outlet])])`; narrow: `View.drawer=ft.NavigationDrawer(...)` | `NavigationRail.extended`, `min_extended_width`, `label_type`, `leading`, `trailing`, `scrollable`, `on_change`; `use_route_outlet()` for the content pane | partial | No split-pane control. Pattern verified in `examples/controls/material/navigation_drawer/adaptive_navigation/main.py` (width >= 450 switches layout) and `apps/router/app_drawer/main.py` (drawer + outlet + Router). In declarative mode read `ft.context.page.width` inside the component and subscribe via `use_effect` on `on_resize`, or hold width in `use_state` set from `page.on_resize`. The Ionic menu is a scrollable list with headers and accordions - `NavigationDrawer.controls: list[Control]` accepts arbitrary controls (`material/navigation_drawer.py` "The list typically contains NavigationDrawerDestination items and/or other controls"), so the same menu component can be rendered into either the drawer or the permanent pane. |
| `ion-menu` + `ion-menu-toggle` + `routerLinkActive` | 1/16 | `View.drawer=ft.NavigationDrawer(controls=[...], selected_index, on_change, on_dismiss, width, indicator_color, tile_padding)`; items either `ft.NavigationDrawerDestination(label, icon, selected_icon)` (indexed selection) **or** `ft.ListTile(selected=ft.is_route_active(path), on_click=lambda: page.navigate(path))` for a mixed list with headers/accordions; close with `page.close_drawer()` (`autoHide`) | | exists | `material/navigation_drawer.py`, `router.py:428` `is_route_active(path, exact=False)`. Section headers (`ion-list-header`) inside the drawer = `ft.Container(padding=..., content=ft.Text(..., theme_style=ft.TextThemeStyle.TITLE_SMALL))` as in the adaptive_navigation example. Caveat from `app_drawer` example comment: do not call `is_route_active()` a variable number of times per render (hook ordering). |
| `ion-tabs` + `ion-tab-bar` + `ion-tab-button` (5-7 tabs, conditional buttons) | 1/2/7 | `View.navigation_bar=ft.NavigationBar(destinations=[ft.NavigationBarDestination(icon, selected_icon, label)], selected_index, on_change, label_behavior, adaptive=True)`; adaptive renders `CupertinoNavigationBar` on iOS (`icon_size`, `active_color`, `inactive_color`, `border`) | `NavigationBar` validates `>= 2` visible destinations and `selected_index` range in `before_update()` | exists | `material/navigation_bar.py` (`NavigationBarLabelBehavior.ALWAYS_SHOW/ALWAYS_HIDE/ONLY_SHOW_SELECTED`), `cupertino/cupertino_navigation_bar.py:27-75`. Tab routing: a layout `Route(component=TabsLayout, outlet=True, children=[speakers, conference-map, schedule, now, ...])`; `TabsLayout` maps `use_route_location()` -> `selected_index` and `on_change` -> `page.navigate()` (same pattern as `app_drawer` example's Tabs). The Ionic "Scanner" button that opens a sheet instead of a tab: handle in `on_change` by not navigating and calling `use_dialog(BottomSheet)`. |
| Banner-sponsor strip rendered as a second `ion-tab-bar slot="bottom"` | 1 | `View.bottom_appbar=ft.BottomAppBar(padding=0, content=ft.Column(spacing=0, controls=[SponsorBanner(), ft.NavigationBar(...)]))` - `NavigationBar` is a `LayoutControl` and can live anywhere | | partial | Because `view.dart:219` renders either `navigation_bar` **or** `bottom_appbar`, stack the banner + nav bar inside `bottom_appbar`. `SnackBar(behavior=FIXED)` positioning above a `NavigationBar` (`material/snack_bar.py` `SnackBarBehavior.FIXED` docs) only applies to `View.navigation_bar`, so prefer `FLOATING` with `margin` if you go the `bottom_appbar` route. |
| `ion-modal [breakpoints]="[0,0.35]" [initialBreakpoint]` (staff tools sheet) | 1 | `ft.BottomSheet(content, draggable=True, show_drag_handle=True, dismissible, scrollable, size_constraints: BoxConstraints, use_safe_area, maintain_bottom_view_insets_padding, shape, barrier_color, on_dismiss)` via `use_dialog` | | exists | `material/bottom_sheet.py`. Breakpoint snapping (0.35 of height) is approximated with `size_constraints`/`height` on the content; there is no multi-breakpoint snap. |

### 1.2 Lists and items

| Ionic | n | Flet | Key properties / events | Status | Notes |
|---|---|---|---|---|---|
| `ion-list` (`lines="none|full|inset"`) | 41 | `ft.ListView(controls, spacing, padding, divider_thickness, item_extent, first_item_prototype, build_controls_on_demand=True, cache_extent, on_scroll, scroll_to)` for long lists; `ft.Column` for short ones | `divider_thickness` gives `lines="full"`; `lines="inset"` = `ft.Divider(leading_indent=...)` between tiles | exists | `core/list_view.py:32-127`. Cookbook `website/docs/cookbook/large-lists.md`. ListView needs a bounded height (`expand=True`). |
| `ion-item` (`button`, `detail`, `routerLink`, `lines`, `slot=start/end`) | 121 | `ft.ListTile(leading: IconDataOrControl, title: StrOrControl, subtitle, trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT) for detail, is_three_line, dense, selected, selected_tile_color, bgcolor, content_padding, shape, on_click, on_long_press, url, action, adaptive)`; iOS: `ft.CupertinoListTile(title, subtitle, additional_info, leading, trailing, notched, bgcolor_activated, on_click)` | `ListTile` is an `ActionControl` -> `action=ft.OpenUrl(...)` for `href` items with no round-trip | exists | `material/list_tile.py`, `cupertino/cupertino_list_tile.py:40-134`. `ion-item` with rich multi-line `ion-label` (h3 + badges + two `p` meta rows, as in `schedule.html`) exceeds ListTile's title/subtitle/three-line model: use `ft.Container(ink=True, on_click=..., content=ft.Column([...]))` (`material/container.py:109 ink`, `:222 on_click`). |
| `ion-label` (`h2/h3/p`, `color`, `ion-text-wrap`) | 154 | `ft.Text(value, theme_style: TextThemeStyle, style: TextStyle, max_lines, overflow, selectable, spans: list[TextSpan], color)`; `ft.Column` of `Text`s for h2+p blocks | `TextThemeStyle.TITLE_MEDIUM/TITLE_SMALL/BODY_MEDIUM/LABEL_SMALL/HEADLINE_SMALL...` | exists | `core/text.py:235-397`, `SDK/controls/text_style.py:60-160`. |
| `ion-list-header` | 20 | `ft.Container(padding=ft.Padding.only(left=16, top=16, bottom=8), content=ft.Text(..., theme_style=ft.TextThemeStyle.TITLE_SMALL))` | | partial | No dedicated control; same idiom as `adaptive_navigation` example's drawer header. |
| `ion-item-divider` (`sticky`) + `ion-item-group` | 4/1 | Non-sticky: `ft.Container(bgcolor=ft.Colors.SURFACE_CONTAINER, content=ft.Text(...))` or `ft.Divider(height, thickness, color, leading_indent, trailing_indent)` | | partial | **Sticky headers are a GAP**: `grep -rniE "sticky|pinned" SDK/controls` finds nothing except DataTable docs. Workaround: a header row pinned above the list (`Column([header, ListView(expand=True)])`) whose text is updated from `ListView.on_scroll` by comparing `OnScrollEvent.pixels` against cumulative group offsets (feasible with `item_extent`, or by giving each divider a `key=ft.ScrollKey(...)`). Extension option: wrap `sliver_tools`/`flutter_sticky_header` (needs the material_ui gate check). |
| `ion-avatar` + `<img>` | 5 | `ft.CircleAvatar(foreground_image_src=url, background_image_src, content=ft.Text(initials), radius, bgcolor, on_image_error)` | | exists | `material/circle_avatar.py:34-123`. |
| `ion-img` (lazy) | 1 | `ft.Image(src, fit: BoxFit, border_radius, placeholder_src, placeholder_fit, fade_in_animation, error_content, cache_width/cache_height, semantics_label)` | | exists | `core/image.py:36-168` (src accepts URL, asset path, base64 or bytes). |
| `ion-badge` | 1 | Attached to a control: any `Control.badge=ft.Badge(label, bgcolor, text_color, offset, alignment, small_size, large_size)`; standalone pill: `ft.Container(border_radius=999, padding=..., bgcolor=..., content=ft.Text(...))` | | exists | `SDK/controls/control.py:101` (`badge: Optional[BadgeValue]`), `material/badge.py:13-112`. The app's `.track-badge` spans are CSS pills -> `Container` pills. |
| `ion-chip` (`outline`, with `ion-avatar`, `ion-icon`) | 7 | `ft.Chip(label, leading: Control, selected, on_click, on_select, on_delete, delete_icon, bgcolor, shape, border_side, padding, label_text_style, show_checkmark=False)` | `border_side=ft.BorderSide(1, color)` + `bgcolor=TRANSPARENT` for `outline="true"` | exists | `material/chip.py:986-1175`. |
| `ion-text color="medium|danger"` | 8 | `ft.Text(color=ft.Colors.ON_SURFACE_VARIANT / ft.Colors.ERROR)` | | exists | `core/text.py`. |
| `ion-spinner name="dots"` | 2 | `ft.ProgressRing(stroke_width, color, size_constraints)` / `ft.CupertinoActivityIndicator(radius, color, animating)`; dotted variants: `flet_spinkit.ThreeBounce`, `Wave`, `Pulse`, ... | | exists | `material/progress_ring.py`, `cupertino/cupertino_activity_indicator.py:24-48`, `sdk/python/packages/flet-spinkit/src/flet_spinkit/spinkit.py:55-426` (`ThreeBounce` at `:176`). |
| `ion-infinite-scroll` (speakers / schedule-list paging) | 2 | `ft.ListView(build_controls_on_demand=True)` already virtualizes; for API paging use `ListView.on_scroll` and trigger when `e.pixels >= e.max_scroll_extent - threshold` and `e.event_type == ft.ScrollType.END` (or `USER` with `direction == ScrollDirection.FORWARD`), append to an `ObservableList`, show a trailing `ProgressRing` row | `ScrollableControl.scroll_interval` throttles `on_scroll` (`scrollable_control.py:376`) | partial | No dedicated infinite-scroll control; the above is a 10-line hook. In this app the "paging" is client-side (`generateSpeakers()` slices an in-memory array) so plain `ListView` is enough. |
| `ion-item-sliding` + `ion-item-options` + `ion-item-option` (swipe to Favorite / Remove) | 1/1/2 | `ft.Dismissible(content, background, secondary_background, dismiss_direction=ft.DismissDirection.START_TO_END|END_TO_START|HORIZONTAL, dismiss_thresholds: dict[DismissDirection, Number], on_update(DismissibleUpdateEvent.progress/reached), on_confirm_dismiss(DismissibleDismissEvent.direction) + await e.control.confirm_dismiss(False), on_dismiss, resize_duration, movement_duration)` | Returning `confirm_dismiss(False)` performs the action (toggle favorite + SnackBar) and snaps the row back, so nothing is removed from the list | partial | `core/dismissible.py:65-197`, `DismissDirection` enum in `material/snack_bar.py`. Difference from Ionic: no persistent "revealed buttons" state; the swipe is a one-shot gesture with a colored `background` (e.g. `Container(bgcolor=AMBER, alignment=CENTER_LEFT, content=Row([Icon(STAR), Text("Favorite")]))`). A `flutter_slidable` extension would give the exact Ionic behavior but `flutter_slidable` is not in the local pub cache and must pass the material_ui import gate before being adopted. |
| `ion-refresher` + `ion-refresher-content` (pull-to-refresh) | 5 | **GAP in core** | | gap | Confirmed: `grep -rniE "refresh|pull_to" SDK/controls` -> only `theme.py:2710 refresh_bgcolor` (a `ProgressIndicatorTheme` field) and a Cupertino docstring; `grep -rnlE "RefreshIndicator|CupertinoSliverRefreshControl" packages sdk --include='*.dart'` -> nothing. Both widgets **do exist** in the packages Flet already depends on: `~/.pub-cache/hosted/pub.dev/material_ui-1.6.0/lib/src/refresh_indicator.dart` and `cupertino_ui-1.1.2/lib/src/refresh.dart`. **Proposal**: add a core `RefreshIndicator(LayoutControl, AdaptiveControl)` control (`content`, `on_refresh` awaited until Python calls `complete()`, `displacement`, `edge_offset`, `color`, `bgcolor`, `stroke_width`, `trigger_mode`, `elevation`; adaptive -> `CustomScrollView` + `CupertinoSliverRefreshControl`), Python at `SDK/controls/material/refresh_indicator.py`, Dart at `packages/flet/lib/src/controls/refresh_indicator.dart`, no third-party dependency. Until then: workaround A - `ListView.on_scroll` with `e.event_type == ScrollType.OVERSCROLL and e.overscroll < -80` (fields verified `scrollable_control.py:253,262`) triggers the reload and shows a top `ProgressRing`; workaround B - `AppBar.actions=[IconButton(ft.Icons.REFRESH)]` (the app already has such a button on the schedule error state). |

### 1.3 Buttons, inputs, selection

| Ionic | n | Flet | Key properties / events | Status | Notes |
|---|---|---|---|---|---|
| `ion-button` (`fill="clear|outline|solid"`, `expand="block"`, `size`, `color`, `slot="icon-only"`, `strong`) | 43 | `ft.Button` / `ft.FilledButton` / `ft.FilledTonalButton` (solid), `ft.OutlinedButton` (outline), `ft.TextButton` (clear), `ft.IconButton` / `ft.FilledIconButton` / `ft.OutlinedIconButton` (icon-only); `expand=True` inside a `Row` or `width=float("inf")`-style via `Container(expand)` for `expand="block"`; `style=ft.ButtonStyle(...)`; all are `ActionControl`s (`action=ft.OpenUrl/CopyToClipboard/ShareText`) | `content`, `icon`, `on_click`, `disabled`, `style`, `url`, `adaptive` | exists | `material/button.py:26`, `filled_button.py`, `filled_tonal_button.py`, `outlined_button.py:24`, `text_button.py:21`, `icon_button.py:32,248,263,279`. `CupertinoButton`, `CupertinoFilledButton`, `CupertinoTintedButton` for iOS. |
| `ion-icon name="..."` | 217 | `ft.Icon(icon=ft.Icons.X | ft.CupertinoIcons.Y, color, size, fill, weight, grade, optical_size, semantics_label)`; most places accept `IconDataOrControl` directly | | exists | `core/icon.py:26-124`. Name map in section 2. |
| `ion-searchbar` (`debounce`, `showCancelButton`, `ionClear`, `ionCancel`, `ionChange`, `inputmode="search"`) | 8 | Inline filter field: `ft.TextField(prefix_icon=ft.Icons.SEARCH, hint_text, keyboard_type=ft.KeyboardType.WEB_SEARCH, suffix_icon=IconButton(CLOSE) for clear, on_change, on_submit, border=ft.NoInputBorder(), filled=True, dense)  # `InputBorder.NONE` is a legacy alias, see form_field_control.py:34-60`; overlay search with suggestions: `ft.SearchBar(bar_hint_text, bar_leading, bar_trailing, controls: list[Control] suggestions, on_change, on_submit, on_tap, open_view(), close_view(text), full_screen, view_hint_text)` | Debounce: `use_ref` + `asyncio` task cancel in the handler, or `use_effect` with dependency on the typed value | exists | `material/search_bar.py`, `material/textfield.py:320-696`, `form_field_control.py:390 hint_text, :478 prefix_icon, :513 suffix_icon`. The expo-hall search with a results dropdown maps 1:1 to `SearchBar.controls`. |
| `ion-segment` + `ion-segment-button` (day selector; map view selector) | 2/5 | `ft.SegmentedButton(segments=[ft.Segment(value, label, icon)], selected: list[str], allow_multiple_selection=False, allow_empty_selection=False, show_selected_icon=False, style, on_change)`; iOS: `ft.CupertinoSlidingSegmentedButton(controls, selected_index, thumb_color, bgcolor, on_change)` or `CupertinoSegmentedButton`; many days -> `ft.Tabs(length, selected_index, on_change, content=ft.TabBar(tabs=[ft.Tab(label)], scrollable=True, tab_alignment=ft.TabAlignment.START))` | | exists | `material/segmented_button.py:546-668`, `cupertino/cupertino_sliding_segmented_button.py:36-87`, `material/tabs.py:133-526` (`Tabs`, `TabBar`, `TabBarView`, `Tab`, `UnderlineTabIndicator`, `TabBarIndicatorSize`). Example composing `Tabs`+`TabBar`+`TabBarView`: `examples/controls/core/types/tab_alignment/showcase/main.py`. `ion-segment` in the toolbar: see "second toolbar row" caveat in 1.1. |
| `ion-toggle` (7, notification settings) | 7 | `ft.Switch(label, label_position, value, on_change, active_color, thumb_icon, adaptive=True)` / `ft.CupertinoSwitch`; inside a row: `ft.ListTile(title, subtitle, trailing=ft.Switch(...), toggle_inputs=True)` | | exists | `material/switch.py:37-208`, `material/list_tile.py` (`toggle_inputs`). |
| `ion-checkbox` (filter tracks, redemption products, `labelPlacement`, `justify`, `disabled`) | 2 | `ft.Checkbox(label, value, tristate, label_position=ft.LabelPosition.RIGHT, active_color, on_change, disabled, adaptive)` / `ft.CupertinoCheckbox`; in list rows `ListTile(..., trailing/leading=Checkbox, toggle_inputs=True)` | | exists | `material/checkbox.py:36-178`. |
| `ion-input type="email|password"` + `appAutofill` + floating label | 2 | `ft.TextField(label, value, keyboard_type=ft.KeyboardType.EMAIL, password=True, can_reveal_password=True, autofill_hints=[ft.AutofillHint.EMAIL] / [ft.AutofillHint.PASSWORD], autocorrect=False, capitalization=ft.TextCapitalization.NONE, enable_suggestions, error_text, on_submit)`; wrap both in `ft.AutofillGroup` | | exists | `material/textfield.py:339 keyboard_type, :403 password, :408 can_reveal_password, :636 autofill_hints`; `core/autofill_group.py:11 AutofillHint` (`EMAIL :236`, `PASSWORD :454`, `USERNAME :744`). `KeyboardType.EMAIL` at `textfield.py:120`. `CupertinoTextField(TextField)` for iOS (`cupertino/cupertino_textfield.py:51`). |
| `ion-textarea` (lead note) | 1 | `ft.TextField(multiline=True, min_lines=3, max_lines=8, keyboard_type=ft.KeyboardType.MULTILINE)` | | exists | `textfield.py:344-368`. |
| `ion-select interface="action-sheet"` + `ion-select-option` (theme picker) | 1/4 | iOS-faithful: `use_dialog(ft.CupertinoBottomSheet(content=ft.CupertinoActionSheet(title, message, actions=[ft.CupertinoActionSheetAction(content, default, destructive, on_click)], cancel=...)))`; Material: `use_dialog(ft.BottomSheet(content=ft.RadioGroup(value, on_change, content=ft.Column([ft.Radio(value, label) ...]))))` or `ft.Dropdown(options=[ft.DropdownOption(key, text)], value, on_change)` | | exists | `cupertino/cupertino_action_sheet.py`, `cupertino_action_sheet_action.py`, `cupertino/cupertino_bottom_sheet.py:18-39`, `material/radio_group.py:17-36`, `material/radio.py`, `material/dropdown.py:86-416`. |
| `ion-accordion-group` + `ion-accordion` (menu "Presentations"/"About", dev info) | 3/3 | `ft.ExpansionTile(title, subtitle, leading, trailing, controls: list[Control], expanded, maintain_state, affinity: TileAffinity, tile_padding, controls_padding, shape, collapsed_shape, bgcolor, collapsed_bgcolor, show_trailing_icon, on_change)`; multi-panel with single-open semantics: `ft.ExpansionPanelList(controls=[ft.ExpansionPanel(header, content, expanded, can_tap_header)], on_change(ExpansionPanelListChangeEvent.index/expanded))` | | exists | `material/expansion_tile.py:723-953`, `material/expansion_panel.py:47-202`. |
| `ion-card` / `ion-card-header` / `ion-card-title` / `ion-card-subtitle` / `ion-card-content` (`button` cards, `color="danger"`) | 31/15/15/5/31 | `ft.Card(content=ft.Container(padding=16, content=ft.Column([ft.Text(title, theme_style=TITLE_LARGE), ft.Text(subtitle, theme_style=LABEL_MEDIUM, color=ON_SURFACE_VARIANT), ...])), variant=ft.CardVariant.ELEVATED|FILLED|OUTLINED, elevation, bgcolor, shape, clip_behavior, adaptive)`; clickable card: inner `Container(ink=True, on_click=...)` | | exists | `material/card.py:14-118`. No separate card-title/subtitle controls - they are plain `Text`s. |
| `ion-fab` | 0 | not used in the app (`grep ion-fab` -> none). `View.floating_action_button` exists if needed | | n/a | `core/view.py`. The custom "Jump to Now" floating pill = `View.floating_action_button=ft.FloatingActionButton(content=Row([Icon, Text]), shape=StadiumBorder)` + `floating_action_button_location`. |

### 1.4 Overlays used from TypeScript (counts = `grep -c` of controller references in `APP/**/*.ts`)

| Ionic controller | n | How the app uses it | Flet | Status | Notes |
|---|---|---|---|---|---|
| `ToastController` | 20 | `message`/`header`, `duration` 1500-3000, `position: 'top'|'bottom'`, `color: 'success'`, `icon`, `buttons:[{text:'Close', role:'cancel'}]` / `{icon:'close', side:'end'}` | `page.show_dialog(ft.SnackBar(content=Text(...), duration=ft.Duration(milliseconds=1500), behavior=ft.SnackBarBehavior.FLOATING, margin, width, bgcolor, show_close_icon=True, action=ft.SnackBarAction(label="Close", on_click), persist, dismiss_direction, on_action, on_visible))` or `use_dialog(...)` | partial | `material/snack_bar.py`. Material snack bars are **bottom-anchored only**; `position: 'top'` (push-notification toast in `app.component.ts:147`, redemption toasts) has no SnackBar equivalent. Top-anchored option: `ft.Banner(content, actions, leading, bgcolor, margin, force_actions_below, on_visible)` (`material/banner.py:21-151`, a `DialogControl`) or a custom `Stack`-positioned `Container` with `animate_opacity` in `page.overlay`. |
| `AlertController` | 8 | `header`, `subHeader`, `message`, `buttons:[{text, role:'cancel', handler}]`, `backdropDismiss:false`, `inputs:[{type:'radio', label, value}]` (sponsor picker), `cssClass` | `ft.AlertDialog(title, content, actions=[ft.TextButton(...)], modal=True  # backdropDismiss:false, icon, actions_alignment, scrollable, shape, barrier_color, on_dismiss, adaptive=True)`; radio inputs: `content=ft.RadioGroup(value, on_change, content=ft.Column([ft.Radio(label, value), ...]))`; iOS: `ft.CupertinoAlertDialog(title, content, actions=[ft.CupertinoDialogAction(...)])` | exists | `material/alert_dialog.py`, `cupertino/cupertino_alert_dialog.py`, `cupertino/cupertino_dialog_action.py`, `material/radio_group.py`. Validation rule: AlertDialog must have at least one of title/content/actions (`alert_dialog.py` `__validation_rules__`). |
| `ActionSheetController` | 5 | `header`, `buttons:[{text, icon (non-iOS), role:'destructive'|'cancel', handler}]` | `use_dialog(ft.CupertinoBottomSheet(ft.CupertinoActionSheet(title, actions=[ft.CupertinoActionSheetAction(content, destructive, default, on_click)], cancel=ft.CupertinoActionSheetAction(...))))`; Material variant `ft.BottomSheet(content=ListView([ListTile(leading=Icon, title, on_click) ...]))` | exists | `cupertino/cupertino_action_sheet.py`, `cupertino_action_sheet_action.py`, `material/bottom_sheet.py`. |
| `ModalController` | 27 | `create({component, componentProps, presentingElement})`, `present()`, `onWillDismiss()` -> `{data, role}` (filter page, floor-plan modal, lead-note modal, redemption modal) | Route modals: `ft.Route(path="filter", component=ScheduleFilter, modal=True)` returning `ft.View(fullscreen_dialog=True, appbar=AppBar(leading=IconButton(CLOSE), actions=[TextButton("Done")]))`; result flows through an `@ft.observable` model (e.g. `filters.excluded_tracks`) rather than a dismiss payload; small forms (lead note) can instead be `ft.AlertDialog`/`ft.BottomSheet(fullscreen=True, scrollable=True)` with `use_dialog` | exists | `router.py:107`, `apps/router/modal_routes/main.py`, `material/bottom_sheet.py` (`fullscreen`, `scrollable`). `page.pop_views_until(route, result=...)` (`page.py:1108`) exists for an imperative result hand-off. |
| `LoadingController` | 16 | `create({message:'Fetching latest...', duration:10000})`, `present()`, `dismiss()` after data arrives | No loading control. Compose: `use_dialog(ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(), ft.Text(message)], tight=True)) if loading else None)`; iOS: `ft.CupertinoAlertDialog(content=Row([CupertinoActivityIndicator(), Text]))`; the 10 s safety timeout = `asyncio.wait_for` in the loader | partial | Better UX for the port: do not block - render `ft.Shimmer` skeleton rows (next table) while `loading` is `True`. |
| `PopoverController` | 0 | not referenced in `APP/**/*.ts` | `ft.PopupMenuButton(items=[ft.PopupMenuItem(content, icon, on_click)], menu_position, on_select)` if ever needed | n/a | `material/popup_menu_button.py:40-241`. |

### 1.5 Rich content, media, special interactions

| Need | Where in app | Flet | Status | Notes |
|---|---|---|---|---|
| Markdown rendering (`markdown-to-txt` is only used to **strip** markdown from slot names in `providers/conference-data.ts:309-575`) | schedule names | For stripping: Python `markdown` + `html.parser`/`re`, or render with `ft.Markdown(value, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, selectable, on_tap_link, auto_follow_links, auto_follow_links_target, md_style_sheet=ft.MarkdownStyleSheet(...), code_theme, soft_line_break, image_error_content)` | exists | `core/markdown.py:28-51` (`MarkdownExtensionSet.NONE/COMMON_MARK/GITHUB_WEB/GITHUB_FLAVORED`), `Markdown` fields `:1532-1623` of the concatenated read (`value`, `selectable`, `extension_set`, `code_theme`, `auto_follow_links`, `shrink_wrap`, `fit_content`, `soft_line_break`, `md_style_sheet`, `on_tap_link`, `on_tap_text`, `on_selection_change`). Dart: `flutter_markdown_plus ^1.0.7` + `markdown ^7.3.0` (`packages/flet/pubspec.yaml:32,38`). |
| HTML rendering of API fields: `session.description`, `speaker.about`, `sponsor.description`, `sprint.description_html`, `content.about`, `content['about-psf']`, `job listing description_html`, venues `section.html` (`[innerHtml]` in 9 templates) | session-detail, speaker-detail, sponsor-detail, sprints, about-pycon, about-psf, venues-hours, job-listings | **No HTML renderer in core.** Options: (1) convert HTML -> Markdown in Python (`markdownify` or `html2text`) and render with `ft.Markdown(extension_set=GITHUB_WEB, on_tap_link=...)` - covers `<p>/<a>/<ul>/<ol>/<strong>/<em>/<h2>/<img>/<code>/<pre>/<blockquote>`, loses inline styles/tables-with-colspan; (2) `flet_webview.WebView` + `await wv.load_html(html, base_url)` - **iOS, Android, macOS only** (`flet-webview/src/flet_webview/webview.py:129-143` `_check_mobile_or_mac_platform`, docstring "Supported only on iOS, Android, macOS and Web; `load_html` works only on iOS, Android, macOS"), heavy, and scrolling inside a scrolling page is awkward; (3) extension wrapping `flutter_html` / `flutter_widget_from_html_core` (must pass the material_ui gate). | partial | Markdown Dart side has no HTML pass-through: `grep -rni html flutter_markdown_plus-1.0.12/lib` -> only `encodeHtml: false` (`widget.dart:387`), so raw HTML tags inside Markdown are printed literally. Recommendation: option (1) in the data layer, with a sanitizer that drops `<script>/<style>` and maps `<br>` to hard line breaks (`soft_line_break=False`). Keep option (3) as a follow-up extension (`flet-html`) if fidelity complaints arise. |
| Pinch-zoom floor plans (`@ciag/ngx-pinch-zoom`: `doubleTap`, `wheel`, `limitZoom='original image size'`, `autoZoomOut=false`, `draggableImage=false`) | floor-plan-modal, conference-map job-fair, expo-hall-map | `ft.InteractiveViewer(content=ft.Image(src, fit=BoxFit.CONTAIN), min_scale=1, max_scale=4, pan_enabled=True, scale_enabled=True, constrained=True, boundary_margin=ft.Margin.all(0), trackpad_scroll_causes_scale=True  # wheel, clip_behavior, interaction_update_interval, on_interaction_start/update/end)`; methods `await iv.zoom(factor)`, `await iv.pan(dx, dy)`, `await iv.reset(animation_duration)`, `save_state()/restore_state()` | exists | `core/interactive_viewer.py:22-260`. Double-tap zoom: wrap in `ft.GestureDetector(on_double_tap=lambda e: iv.zoom(2.0))` (`core/gesture_detector.py:358 on_double_tap`). CHANGELOG 1.0.2 fixed `InteractiveViewer` + `alignment`. "limitZoom = original image size" = `max_scale = natural_px / displayed_px`, computable from `Image` size via `LayoutControl.on_size_change` (`layout_control.py:28-45 LayoutSizeChangeEvent.width/height`, `:301 on_size_change`). |
| Expo-hall booth hit-targets positioned as % of image, highlight + popup | expo-hall-map | `InteractiveViewer(content=ft.Stack([ft.Image(...), *[ft.Container(left=pct_x*W, top=pct_y*H, width=w, height=h, border=..., on_click=select_booth) for booth in booths]]))`; W/H from the image `on_size_change`; selected booth popup = `ft.Container` positioned in an outer `Stack` or a `BottomSheet`; "scroll to booth" = `await iv.pan(dx, dy)` + `zoom` | exists | `SDK/controls/layout_control.py:76-103` (`left/top/right/bottom` inside `Stack`), `core/stack.py`, `container.py:222 on_click`. Pulsing pin (`floor-plan-pin-pulse`) = `Container(animate_scale=..., animate_opacity=...)` toggled by `use_effect` timer, or `flet_lottie.Lottie` (`flet-lottie/src/flet_lottie/lottie.py:19-71`). |
| 3D venue tour `<iframe src="https://map.concept3d.com/?id=1802">` | conference-map "3D Tour" segment | `flet_webview.WebView(url=..., on_page_started, on_page_ended, on_url_change, prevent_links)` (iOS/Android/macOS/Web) or open externally with `ft.UrlLauncher().launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW)` | exists | `flet-webview/src/flet_webview/webview.py:22-105`, `SDK/controls/services/url_launcher.py:19-36 LaunchMode`, `:248-341 UrlLauncher.launch_url/can_launch_url/close_in_app_web_view/open_window`. |
| Skeleton / shimmer loading | app uses `LoadingController` spinners, no `ion-skeleton-text` (`grep ion-skeleton` -> none) | `ft.Shimmer(content=Column([Container(height=72, bgcolor=GREY_300) ...]), base_color, highlight_color, period=1500, direction=ft.ShimmerDirection.LTR, loop)` | exists | `core/shimmer.py:226-322`. Recommended replacement for most `LoadingController` uses. |
| Hero sections with big icon (`.page-hero`) | now, speakers, sponsors, wifi, about | `ft.Container(gradient=ft.LinearGradient(...), padding, content=Column([Icon(size=64), Text(theme_style=HEADLINE_MEDIUM), Text(...)]))` | exists | `container.py:74 gradient`. |
| Inline SVG python logo in error state | schedule | `ft.Image(src="python-logo.svg")` (Flutter `Image` renders SVG assets through Flet's image loader) or a PNG asset | exists | `core/image.py`. |
| Haptics (`@capacitor/haptics` is in `package.json` but **not imported** in `src/app` TS) | - | `ft.HapticFeedback()` service: `heavy_impact()`, `light_impact()`, `medium_impact()`, `vibrate()`, `selection_click()` | exists | `SDK/controls/services/haptic_feedback.py:4-30`. |
| Clipboard (`navigator.clipboard.writeText` in notification-settings, wifi) | wifi, dev tools | `await ft.Clipboard().set(value)` / `get()`; gesture-gated no-round-trip variant `action=ft.CopyToClipboard(data=...)` on buttons | exists | `services/clipboard.py:45-139`. CHANGELOG 1.0.0 "Client actions". |
| Share (`@capacitor/share`, 2 imports) | about-pycon "Share Debug Info", session share | `ft.Share().share_text(text, title, subject)`, `share_uri()`, `share_files([ft.ShareFile.from_bytes(...)])`; or `action=ft.ShareText(text, title)` | exists | `services/share.py:157-367`. |
| In-app browser (`@capacitor/inappbrowser`, 5 imports) | links, `mailto:`, `tel:` | `ft.UrlLauncher().launch_url(url, mode=ft.LaunchMode.IN_APP_BROWSER_VIEW|EXTERNAL_APPLICATION)`; buttons/ListTile/TextSpan: `url=` or `action=ft.OpenUrl(url, target)`; Markdown links: `auto_follow_links` / `on_tap_link` | exists | `services/url_launcher.py`, `list_tile.py url`, `core/text_span.py`. |
| Network status (`@capacitor/network`) | offline banner / error state | `ft.Connectivity(on_change=...)`, `await get_connectivity() -> list[ConnectivityType]` | exists | `services/connectivity.py:148-216`. |
| Storage (`@ionic/storage-angular`, 16 imports: schedule cache, favorites, auth token, prefs) | providers | `ft.SharedPreferences()` (`set/get/contains_key/remove/get_keys/clear`) for cache/prefs; `flet_secure_storage.SecureStorage` (`set/get/get_all/contains_key/remove/clear/get_availability`) for the auth token; large JSON cache -> file under `ft.StoragePaths` | exists | `services/shared_preferences.py:13-97`, `flet-secure-storage/src/flet_secure_storage/secure_storage.py:29-260`, `services/storage_paths.py:12`. Example `apps/declarative/trolli/components/dialogs.py:48`. |
| App lifecycle (`@capacitor/app` resume -> refresh "Now") | app.component | `page.on_app_lifecycle_state_change` with `ft.AppLifecycleState.RESUME/PAUSE/...` | exists | `page.py:630`, `SDK/controls/types.py:1106-1189`. |
| Theme picker: light / dark / high-contrast-light / high-contrast-dark | app.component `setTheme()` | `page.theme_mode = ft.ThemeMode.LIGHT|DARK|SYSTEM`; `page.theme = ft.Theme(color_scheme_seed=..., color_scheme=ft.ColorScheme(...), surfaces=ft.ThemeSurfaces.NEUTRAL|TONAL, use_material3, font_family, text_theme, list_tile_theme, navigation_bar_theme, navigation_drawer_theme, snackbar_theme, chip_theme, card_theme, dialog_theme, bottom_sheet_theme, segmented_button_theme, search_bar_theme, expansion_tile_theme, system_overlay_style, page_transitions)`; high-contrast = a second `Theme` with an explicit `ColorScheme` swapped into `page.theme`/`page.dark_theme`; `page.platform_brightness` / `on_platform_brightness_change` for system | exists | `types.py:860-876 ThemeMode`, `theme.py:145 ColorScheme`, `:3304 Theme` (fields `:3309-3632`), `page.py:572,615`. CHANGELOG 1.1.0: neutral default surfaces + `Theme.surfaces`. |
| Keyboard avoidance (`@capacitor/keyboard`) | forms | `ft.SafeArea(content, avoid_intrusions_*, maintain_bottom_view_padding, minimum_padding)`, `page.media.view_insets/padding/view_padding` + `on_media_change`, `BottomSheet.maintain_bottom_view_insets_padding` | exists | `core/safe_area.py:29-71`, `base_page.py:61-93 PageMediaData`, `:232`. |
| Status bar / splash (`@capacitor/status-bar`, `splash-screen`) | init | `Theme.system_overlay_style`; splash via `flet build` splash options / `flet-platform-assets` | exists | `theme.py:3606`, `sdk/python/packages/flet-platform-assets/src/flet_platform_assets/_splash.py`. |
| Tutorial (single static slide, `startApp()`) | tutorial | `ft.View` with `Image` + `Button`; multi-slide onboarding would be `ft.PageView(controls, selected_index, on_change, snap)` | exists | `core/page_view.py:30-130`. |

### 1.6 Native capabilities with no Flet counterpart (not UI, but they shape the UI plan)

| Capacitor plugin | Used for | Flet | Status |
|---|---|---|---|
| `@capacitor-mlkit/barcode-scanning` (4 imports: lead scanner, door check, swag pickup, CoC) | QR badge scanning with live camera | **GAP**. `flet_camera.Camera` (`flet-camera/src/flet_camera/camera.py:24-255`: `initialize`, `take_picture() -> bytes`, `start_image_stream()`, `set_flash_mode`, `set_zoom_level`) gives frames but no decoding; `grep -rliE "barcode|qr_code|mobile_scanner"` across packages -> only `flet-cli` run tests and a Lucide icon. Proposal: `flet-barcode-scanner` extension wrapping pub.dev `mobile_scanner` (not in local pub cache; check it builds on `widgets.dart`, not `flutter/material.dart`, per the extension skill). Interim: `Camera.take_picture()` + Python `zxing-cpp`/`pyzbar` decode (slow, no live overlay). Permission flow: `flet_permission_handler.PermissionHandler().request(flet_permission_handler.Permission.CAMERA)`, `open_app_settings()` (`flet-permission-handler/.../permission_handler.py:40-74`, `types.py:189 CAMERA, :296 NOTIFICATION`). | gap |
| `@capacitor-firebase/messaging` + `@capacitor/local-notifications` (push + local reminders, notification-settings page) | | **GAP**: `grep -rliE "local_notification|push_notification|firebase_messaging"` -> nothing. Needs an extension (e.g. `flutter_local_notifications`, `firebase_messaging`). The settings page itself is just `Switch`es + `SharedPreferences`. | gap |
| `@ebarooni/capacitor-calendar` (add session to calendar) | session-detail | **GAP** (`grep add_to_calendar|device_calendar` -> nothing). Fallback: open a Google Calendar / `.ics` URL via `UrlLauncher`, or share an `.ics` via `Share.share_files`. | gap |
| `@capacitor/live-updates` (OTA web bundle, "New version available" banner) | app shell | **GAP** as a mechanism; the banner itself = `ft.Banner` or a `Container` at the top of the tabs layout. Flet apps ship Python code inside the native bundle; OTA of Python code is out of scope here. | gap |
| `@capacitor-firebase/analytics` | | **GAP** in Flet; call Firebase/GA4 Measurement Protocol over HTTP from Python instead. | gap |
| `@capacitor/filesystem` | caching | `ft.StoragePaths` + Python `pathlib` | exists |

---

## 2. Ionicons -> `ft.Icons` / `ft.CupertinoIcons`

Every `ft.Icons.*` name below was checked against
`SDK/controls/material/icons.json` (8825 names; `icons.py` loads this JSON lazily via
`_IconsProxy` and `icons.pyi` is the typing stub) and every `ft.CupertinoIcons.*` against
`SDK/controls/cupertino/cupertino_icons.json` (1322 names). Zero misses. Sources:
`grep -rhoE 'name="[a-z0-9-]+"' APP/**/*.html` (117 distinct, includes a few `<meta name>`
false positives which are excluded) and `icon: '...'` strings in `APP/**/*.ts`.

Ionic `-outline` variants map to Material `_OUTLINED`/`_OUTLINE`/`_BORDER`; Ionic filled maps to
the plain Material name. Where a Cupertino name is listed it was verified in
`cupertino_icons.json` and is the natural `adaptive` pick for iOS.

| ionicon (uses) | ft.Icons | ft.CupertinoIcons |
|---|---|---|
| `time-outline` (8) | `ACCESS_TIME` / `SCHEDULE_OUTLINED` | `CLOCK` |
| `location-outline` (7), `location` | `LOCATION_ON_OUTLINED` / `PLACE_OUTLINED`; filled `LOCATION_ON` | `LOCATION` |
| `globe-outline` (6) | `LANGUAGE` / `PUBLIC_OUTLINED` | `GLOBE` |
| `chevron-forward` (6), `chevron-forward-outline` (3) | `CHEVRON_RIGHT` | `CHEVRON_FORWARD` |
| `calendar-outline` (6 + ts), `calendar` | `CALENDAR_TODAY_OUTLINED` / `CALENDAR_MONTH_OUTLINED`; `CALENDAR_TODAY` | `CALENDAR` |
| `star-outline` (5 + ts), `star` (5) | `STAR_BORDER` / `STAR_OUTLINE`; `STAR` | `STAR`; `STAR_FILL` |
| `open-outline` (5) | `OPEN_IN_NEW` | `ARROW_UP_RIGHT_SQUARE` |
| `people-outline` (4 + ts), `people` (2) | `PEOPLE_OUTLINE` / `GROUP_OUTLINED`; `PEOPLE` | `PERSON_2`; `PERSON_2_FILL` |
| `people-circle-outline` (ts) | `GROUPS_OUTLINED` / `SUPERVISED_USER_CIRCLE_OUTLINED` | |
| `shield-checkmark-outline` (3 + ts), `shield-checkmark` | `VERIFIED_USER_OUTLINED` / `GPP_GOOD_OUTLINED`; `VERIFIED_USER` | |
| `person-outline` (3), `person`, `person-circle`, `person-add-outline` | `PERSON_OUTLINE`; `PERSON`; `ACCOUNT_CIRCLE`; `PERSON_ADD_OUTLINED` | `PERSON`; `PERSON_FILL` |
| `notifications-outline` (3) | `NOTIFICATIONS_OUTLINED` / `NOTIFICATIONS_NONE` | `BELL` |
| `logo-python` (3 + ts) | no brand icon in Material: `CODE` / `DATA_OBJECT`, or ship `assets/python-logo.svg` as `ft.Image` | |
| `information-circle-outline` (3 + ts), `information-circle` | `INFO_OUTLINE` / `INFO_OUTLINED`; `INFO` | `INFO` |
| `document-text-outline` (3), `document-text`, `document-outline` | `DESCRIPTION_OUTLINED`; `DESCRIPTION`; `INSERT_DRIVE_FILE_OUTLINED` | |
| `cloud-download-outline` (3) | `CLOUD_DOWNLOAD_OUTLINED` | |
| `cloud-offline-outline` | `CLOUD_OFF_OUTLINED` | |
| `warning-outline` (2), `nuclear-outline` | `WARNING_AMBER_OUTLINED`; `DANGEROUS_OUTLINED` | |
| `shirt-outline` (2) | `CHECKROOM` / `CHECKROOM_OUTLINED` | |
| `scan-outline` (2), `scan` | `QR_CODE_SCANNER` | `QRCODE_VIEWFINDER` |
| `qr-code` (2), `qr-code-outline` | `QR_CODE`; `QR_CODE_2` / `QR_CODE_OUTLINED` | `QRCODE` |
| `refresh-outline` (2) | `REFRESH` | `REFRESH` |
| `pulse` (2) | `MONITOR_HEART_OUTLINED` / `SHOW_CHART` | |
| `pricetag-outline` (2), `pricetags`, `pricetags-outline` (ts) | `LABEL_OUTLINED` / `SELL_OUTLINED`; `LABEL` / `SELL` | |
| `pin-outline` (2 + ts), `pin` | `PUSH_PIN_OUTLINED`; `PUSH_PIN` | |
| `newspaper-outline` (2), `newspaper` | `NEWSPAPER_OUTLINED` / `ARTICLE_OUTLINED`; `NEWSPAPER` | |
| `map-outline` (2 + ts), `map` (2) | `MAP_OUTLINED`; `MAP` | `MAP`; `MAP_FILL` |
| `logo-mastodon`, `logo-linkedin`, `logo-youtube`, `logo-twitter`, `logo-discord` | no brand icons in Material (`ALTERNATE_EMAIL`, `WORK`, `SMART_DISPLAY`, `TAG`, `FORUM` are semantic stand-ins); recommended: bundle simple-icons SVGs as `ft.Image` (the 1.1.0 `flet_shadcn_ui.LucideIcons` set has no brand icons either: `grep -E "GITHUB|TWITTER|LINKEDIN|YOUTUBE|DISCORD" flet-shadcn-ui/src/flet_shadcn_ui/lucide_icons.py` -> none) | |
| `log-out-outline` (2), `log-in` (2) | `LOGOUT`; `LOGIN` | `SQUARE_ARROW_RIGHT` |
| `heart-outline` (2), `heart` (2) | `FAVORITE_BORDER`; `FAVORITE` | `HEART`; `HEART_FILL` |
| `expand-outline` (2) | `OPEN_IN_FULL` / `FULLSCREEN` | |
| `copy-outline` (2) | `CONTENT_COPY_OUTLINED` / `CONTENT_COPY` | |
| `code-slash-outline` (2), `code-outline` | `CODE` | |
| `close-outline` (2), `close` (ts), `close-circle-outline` | `CLOSE`; `CANCEL_OUTLINED` / `HIGHLIGHT_OFF` | `XMARK` |
| `checkmark-outline` (2), `checkmark` (2), `check` (ts), `checkmark-circle` | `CHECK`; `CHECK_CIRCLE` | |
| `checkbox-outline` (2) | `CHECK_BOX_OUTLINED` / `CHECK_BOX_OUTLINE_BLANK` | |
| `business-outline` (2 + ts), `business` | `BUSINESS_OUTLINED` / `APARTMENT`; `BUSINESS` | |
| `briefcase-outline` (2 + ts), `briefcase` | `WORK_OUTLINE` / `BUSINESS_CENTER_OUTLINED`; `WORK` | |
| `alert-circle-outline` (2), `alert-circle`, `alert` (ts), `exclamation` (ts) | `ERROR_OUTLINE`; `ERROR`; `PRIORITY_HIGH` | |
| `add-circle-outline` (2) | `ADD_CIRCLE_OUTLINE` | |
| `wifi`, `wifi-outline` (ts) | `WIFI`; `WIFI_OUTLINED` | `WIFI` |
| `trash-outline` | `DELETE_OUTLINE` / `DELETE_OUTLINED` | |
| `storefront-outline` (+ts) | `STOREFRONT_OUTLINED` | |
| `stop-circle-outline` | `STOP_CIRCLE_OUTLINED` | |
| `sparkles-outline` | `AUTO_AWESOME_OUTLINED` | |
| `share-social`, `share-outline` | `SHARE`; `SHARE_OUTLINED` / `IOS_SHARE` | `SHARE` |
| `settings-outline` | `SETTINGS_OUTLINED` | `SETTINGS` |
| `server-outline` | `DNS_OUTLINED` / `STORAGE` | |
| `search` | `SEARCH` | `SEARCH` |
| `school-outline` | `SCHOOL_OUTLINED` | |
| `rocket`, `rocket-outline` (ts) | `ROCKET_LAUNCH` / `ROCKET`; `ROCKET_LAUNCH_OUTLINED` | |
| `restaurant-outline` | `RESTAURANT_OUTLINED` | |
| `radio` (Now tab) | `SENSORS` / `PODCASTS` / `RADIO_BUTTON_CHECKED` | `DOT_RADIOWAVES_LEFT_RIGHT` |
| `phone-portrait-outline` | `PHONE_IPHONE` / `SMARTPHONE` | |
| `navigate-outline` | `NAVIGATION_OUTLINED` / `NEAR_ME_OUTLINED` | |
| `moon-outline` | `DARK_MODE_OUTLINED` / `NIGHTLIGHT_OUTLINED` | |
| `mail-outline`, `mail`, `email` | `MAIL_OUTLINE`; `MAIL`; `EMAIL` | `MAIL` |
| `help-circle-outline` (+ts), `help-buoy` | `HELP_OUTLINE`; `SUPPORT` | |
| `hand-left-outline` | `BACK_HAND_OUTLINED` / `PAN_TOOL_OUTLINED` | |
| `git-network-outline` | `ACCOUNT_TREE_OUTLINED` / `HUB_OUTLINED` | |
| `funnel-outline`, `funnel` | `FILTER_ALT_OUTLINED` / `FILTER_LIST`; `FILTER_ALT` | `LINE_HORIZONTAL_3_DECREASE` |
| `flask-outline` | `SCIENCE_OUTLINED` | |
| `flash`, `flash-outline` (ts) | `BOLT` / `FLASH_ON`; `BOLT_OUTLINED` | |
| `create-outline` | `EDIT_OUTLINED` | |
| `contrast-outline` | `CONTRAST` / `BRIGHTNESS_6_OUTLINED` | |
| `construct-outline` | `BUILD_OUTLINED` / `CONSTRUCTION_OUTLINED` | |
| `cash-outline` | `PAYMENTS_OUTLINED` / `ATTACH_MONEY` | |
| `call-outline`, `call` | `CALL_OUTLINED`; `CALL` | `PHONE` |
| `bulb-outline` | `LIGHTBULB_OUTLINE` | |
| `bug-outline` | `BUG_REPORT_OUTLINED` | |
| `book-outline` (+ts) | `MENU_BOOK_OUTLINED` / `BOOK_OUTLINED` | |
| `arrow-forward-circle`, `arrow-forward` | `ARROW_CIRCLE_RIGHT`; `ARROW_FORWARD` | |
| `analytics-outline` | `ANALYTICS_OUTLINED` / `INSIGHTS` | |
| `chatbubbles-outline` (ts) | `FORUM_OUTLINED` / `CHAT_OUTLINED` | |
| `mic-outline` (ts) | `MIC_NONE` / `MIC_OUTLINED` | |
| `hardware-chip-outline` (ts) | `MEMORY_OUTLINED` | |
| `easel-outline` (ts) | `CO_PRESENT_OUTLINED` / `PRESENT_TO_ALL` | |
| `ellipsis-horizontal-circle`, spinner `dots` | `MORE_HORIZ` (or `ProgressRing`) | |
| (hamburger) | `MENU` | `BARS` |
| (implicit back) | `ARROW_BACK` (Flutter picks per platform automatically) | |

Status: **exists** for all 117 names (semantic substitutes for the 6 brand logos and the
Python logo). Suggest a single `icons.py` module in the port: `ION = {"time-outline": ft.Icons.ACCESS_TIME, ...}` plus an `adaptive_icon(name)` helper that returns the Cupertino member when `page.platform in (IOS, MACOS)`.

---

## 3. Composition reference: AppBar + NavigationDrawer + NavigationBar + Tabs in Flet 1.x

Verified examples to copy from:

- `sdk/python/examples/apps/declarative/navigation_drawer/main.py` - `ft.View(appbar=ft.AppBar(leading=IconButton(MENU, on_click=page.show_drawer)), drawer=ft.NavigationDrawer(selected_index, on_change, controls=[Container(height=12), *NavigationDrawerDestination...]))` with `use_state`; closes via `await ft.context.page.close_drawer()`.
- `sdk/python/examples/apps/router/app_drawer/main.py` - `Router(manage_views=True)`, nested `Route(path=":app_id", component=AppDetails, outlet=True, children=[...])`, `use_route_outlet()` deciding whether the drawer is open, `ft.Tabs(length=2, selected_index, on_change, content=ft.TabBar(scrollable=False, tabs=[ft.Tab(label=...)]))` inside the drawer, URL <-> tab sync with `use_route_location()` + `use_effect(sync, dependencies=[location])`, and the on_change echo guard.
- `sdk/python/examples/apps/router/nested_outlet_views/main.py` - layout route returning `ft.View(route=ft.use_view_path(), appbar=..., controls=[Container(content=outlet, expand=True), ...])`; children return plain controls.
- `sdk/python/examples/apps/router/modal_routes/main.py` - `Route(modal=True)` + `View(fullscreen_dialog=True)` for global and local modals.
- `sdk/python/examples/controls/material/navigation_drawer/adaptive_navigation/main.py` - width-switch between `NavigationBar` (narrow) and `NavigationRail` + `VerticalDivider` + drawer (wide), `page.on_resize`.
- `sdk/python/examples/controls/core/types/tab_alignment/showcase/main.py` - `Tabs(length, selected_index, content=Column([TabBar(tabs=[...]), TabBarView(controls=[...])]))`.
- `sdk/python/examples/controls/core/pagelet/pagelet_declarative/main.py` - `ft.Pagelet(appbar, navigation_bar|bottom_appbar, drawer, end_drawer, floating_action_button, bottom_sheet)` for a page-within-a-page (useful for the tablet split pane's right side).

Proposed shell for the port (all names verified above):

```python
@ft.component
def TabsLayout():
    page = ft.context.page
    outlet = ft.use_route_outlet()
    location = ft.use_route_location()
    wide = page.width is not None and page.width >= 900        # ion-split-pane breakpoint
    tab_routes = ["/speakers", "/map", "/schedule", "/now", "/scanner"]
    idx = next((i for i, r in enumerate(tab_routes) if location.startswith(r)), 0)

    nav_bar = ft.NavigationBar(
        adaptive=True, selected_index=idx,
        on_change=lambda e: page.navigate(tab_routes[e.control.selected_index]),
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.PEOPLE_OUTLINE, selected_icon=ft.Icons.PEOPLE, label="Speakers"),
            ft.NavigationBarDestination(icon=ft.Icons.MAP_OUTLINED, selected_icon=ft.Icons.MAP, label="Map"),
            ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_TODAY_OUTLINED, selected_icon=ft.Icons.CALENDAR_TODAY, label="Schedule"),
            ft.NavigationBarDestination(icon=ft.Icons.SENSORS, label="Now"),
            ft.NavigationBarDestination(icon=ft.Icons.QR_CODE_SCANNER, label="Scanner"),
        ],
    )
    menu = SideMenu()   # the ion-menu content: list headers, ListTiles, ExpansionTiles, theme picker
    if wide:
        body = ft.Row(expand=True, spacing=0, controls=[
            ft.Container(width=304, content=menu), ft.VerticalDivider(width=1),
            ft.Column(expand=True, controls=[outlet]),
        ])
        return ft.View(route=ft.use_view_path(), padding=0, controls=[body],
                       bottom_appbar=ft.BottomAppBar(padding=0, content=ft.Column(spacing=0, controls=[SponsorBanner(), nav_bar])))
    return ft.View(route=ft.use_view_path(), padding=0, controls=[outlet],
                   drawer=ft.NavigationDrawer(controls=[menu]),
                   bottom_appbar=ft.BottomAppBar(padding=0, content=ft.Column(spacing=0, controls=[SponsorBanner(), nav_bar])))
```

Each tab page component returns its own `ft.View(route=ft.use_view_path(), appbar=ft.AppBar(leading=ft.IconButton(ft.Icons.MENU, on_click=lambda: page.show_drawer()), title=..., actions=[...]), scroll=ft.ScrollMode.AUTO, on_scroll=..., controls=[...])` and detail pages are child routes so the AppBar back arrow and swipe-back come for free.

---

## 4. Gaps and proposals (summary)

| # | Gap | Proposal | Effort |
|---|---|---|---|
| G1 | Pull-to-refresh (`ion-refresher`, 5 pages) | Core `RefreshIndicator` control (material_ui `refresh_indicator.dart` + cupertino_ui `refresh.dart` already available; no new dependency). Interim: overscroll detection via `on_scroll` or AppBar refresh button. | S (core PR) |
| G2 | HTML description rendering (9 templates) | HTML -> Markdown in the data layer + `ft.Markdown`; optional `flet-html` extension later. | S / M |
| G3 | Barcode / QR scanning (4 staff tools) | `flet-barcode-scanner` extension over `mobile_scanner` (verify material_ui gate); interim `flet_camera` + Python decode. | M-L |
| G4 | Push + local notifications | Extension(s); settings UI itself is trivial. | L |
| G5 | Add-to-calendar | `.ics` share / URL via `Share`/`UrlLauncher`; native calendar extension optional. | S |
| G6 | Sticky `ion-item-divider` headers | Pinned header driven by `ListView.on_scroll`; or sticky-header extension. | S / M |
| G7 | Toast at `position: 'top'` | `ft.Banner` or overlay `Container`; SnackBar is bottom-only. | S |
| G8 | `ion-item-sliding` persistent reveal | `Dismissible` one-shot swipe (acceptable); `flutter_slidable` extension if exact parity required. | S / M |
| G9 | Live updates / Firebase analytics | Out of scope for Flet; HTTP analytics from Python. | - |
| G10 | Brand logos (python, mastodon, linkedin, youtube, twitter, discord) | Bundle SVGs as assets (`ft.Image` renders SVG: `packages/flet/lib/src/utils/images.dart`); Lucide has no brand icons. | S |
