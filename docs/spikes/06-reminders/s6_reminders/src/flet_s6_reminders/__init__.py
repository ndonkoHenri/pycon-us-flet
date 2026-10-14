"""S6 throwaway extension: scheduled local notifications (docs/spikes/06-reminders.md).

The API is the one docs/flet-gaps-and-extensions.md §4.1 proposes for E3,
reduced to what the spike exercises. It is not a package for the app.
"""

from flet_s6_reminders.reminders import LaunchDetails, Pending, S6Reminders, TapEvent

__all__ = ["LaunchDetails", "Pending", "S6Reminders", "TapEvent"]
