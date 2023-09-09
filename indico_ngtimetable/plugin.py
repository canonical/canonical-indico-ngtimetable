from flask import session
from indico.core import signals
from indico.core.plugins import IndicoPlugin, IndicoPluginBlueprint, url_for_plugin
from indico.modules.events.contributions import contribution_settings
from indico.modules.events.layout.util import MenuEntryData
from indico.web.menu import SideMenuItem

from . import _
from .controllers import (
    RHNGTimetable,
    RHNGTimetableEventSettings,
    RHNGTimetableManage,
    RHNGTimetableMove,
    RHNGTimetableSchedule,
)
from .views import WPNGTimetable


class NGTimetablePlugin(IndicoPlugin):
    """NG Timetable Plugin
    An opinionated timetable for open source tech conferences and beyond
    """

    default_event_settings = {
        "granularity": 30,
        "use_track_colors": True,
        "hours_per_screen": 6,
    }

    def init(self):
        super().init()

        self.connect(signals.event.sidemenu, self._inject_menulink)
        self.inject_bundle("ngtimetable.css", WPNGTimetable)
        self.inject_bundle("ngtimetablejs.js", WPNGTimetable)

        self.connect(
            signals.menu.items,
            self._inject_management_menuitems,
            sender="event-management-sidemenu",
        )

    def get_blueprints(self):
        blueprint = IndicoPluginBlueprint(
            "ngtimetable", __name__, url_prefix="/event/<int:event_id>/ngtimetable"
        )
        blueprint.add_url_rule("/", "view", RHNGTimetable)
        blueprint.add_url_rule("/manage", "manage", RHNGTimetableManage)
        blueprint.add_url_rule(
            "/settings", "settings", RHNGTimetableEventSettings, methods=("GET", "POST")
        )
        blueprint.add_url_rule(
            "/manage/move/<int:entry_id>", "move", RHNGTimetableMove, methods=("POST",)
        )
        blueprint.add_url_rule(
            "/manage/schedule/<int:contrib_id>",
            "schedule",
            RHNGTimetableSchedule,
            methods=("POST",),
        )
        return blueprint

    def _inject_menulink(self, sender, **kwargs):
        def _visible_timetable(event):
            return contribution_settings.get(event, "published") or event.can_manage(
                session.user
            )

        yield MenuEntryData(
            title=_("Timetable NG"),
            name="ngtimetable",
            endpoint="ngtimetable.view",
            is_enabled=False,
            position=3,
            visible=_visible_timetable,
        )

    def _inject_management_menuitems(self, sender, event, **kwargs):
        return SideMenuItem(
            "ngtimetable",
            _("NG Timetable"),
            url_for_plugin("ngtimetable.settings", event),
            section="customization",
        )
