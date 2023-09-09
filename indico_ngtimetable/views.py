from flask_pluginengine import render_plugin_template
from indico.core.plugins import WPJinjaMixinPlugin
from indico.modules.events.management.views import WPEventManagement
from indico.modules.events.views import WPConferenceDisplayBase


class WPNGTimetableSettings(WPJinjaMixinPlugin, WPEventManagement):
    sidemenu_option = "ngtimetable"


class WPNGTimetable(WPJinjaMixinPlugin, WPConferenceDisplayBase):
    def __init__(self, rh, event, timetable, rooms, published, **kwargs):
        super().__init__(rh, event, **kwargs)
        self.timetable = timetable
        self.rooms = rooms
        self.published = published

    def _get_head_content(self):
        return (
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            + super()._get_head_content()
        )

    def _get_body(self, params):
        return render_plugin_template(
            "ngtimetable.html",
            timetable=self.timetable,
            rooms=self.rooms,
            published=self.published,
            **params
        )
