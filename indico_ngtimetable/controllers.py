from indico.modules.events.contributions import contribution_settings
from indico.modules.events.controllers.base import RHDisplayEventBase

from .serializer import NGTimetableSerializer
from .views import WPNGTimetable


class RHNGTimetable(RHDisplayEventBase):
    def _process_args(self):
        super()._process_args()

        from .plugin import NGTimetablePlugin

        self.plugin = NGTimetablePlugin

    def _process(self):
        use_track_colors = self.plugin.settings.get("timetable_use_track_colors")

        serializer = NGTimetableSerializer(
            self.event, use_track_colors=use_track_colors
        )
        timetable = serializer.serialize_timetable(strip_empty_days=True)

        published = contribution_settings.get(self.event, "published")

        return WPNGTimetable(
            self,
            self.event,
            timetable=timetable,
            rooms=serializer.room_map,
            published=published,
        ).display()
