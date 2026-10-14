// swift-tools-version: 5.9
// S6: the extension's iOS side, which only sets the notification center's
// delegate (docs/spikes/06-reminders.md).

import PackageDescription

let package = Package(
    name: "flet_s6_reminders",
    platforms: [
        .iOS("13.0")
    ],
    products: [
        .library(name: "flet-s6-reminders", targets: ["flet_s6_reminders"])
    ],
    dependencies: [
        .package(name: "FlutterFramework", path: "../FlutterFramework")
    ],
    targets: [
        .target(
            name: "flet_s6_reminders",
            dependencies: [
                .product(name: "FlutterFramework", package: "FlutterFramework")
            ]
        )
    ]
)
