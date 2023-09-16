import dateutil.parser
import pytz
from flask import flash, request, session
from indico.modules.events.contributions import contribution_settings
from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.contributions.operations import (
    schedule_contribution,
    update_contribution,
)
from indico.modules.events.management.controllers import RHManageEventBase
from indico.modules.events.timetable.controllers.display import (
    RHTimetableProtectionBase,
)
from indico.modules.events.timetable.operations import update_timetable_entry
from indico.modules.events.util import track_location_changes, track_time_changes
from indico.modules.rb.models.locations import Location
from indico.modules.rb.models.rooms import Room
from indico.web.forms.base import FormDefaults
from indico.web.util import jsonify_data
from werkzeug.exceptions import Forbidden

from . import _
from .forms import NGTimetableSettingsForm
from .serializer import NGTimetableSerializer
from .views import WPNGTimetable, WPNGTimetableSettings


class RHNGTimetable(RHTimetableProtectionBase):
    MANAGEMENT = False

    def _process_args(self):
        super()._process_args()

        from .plugin import NGTimetablePlugin

        self.plugin = NGTimetablePlugin

    def _process(self):
        self.event.preload_all_acl_entries()

        granularity = self.plugin.event_settings.get(self.event, "granularity")
        use_track_colors = self.plugin.event_settings.get(
            self.event, "use_track_colors"
        )
        hours_per_screen = self.plugin.event_settings.get(
            self.event, "hours_per_screen"
        )

        serializer = NGTimetableSerializer(
            self.event,
            use_track_colors=use_track_colors,
            granularity=granularity,
            management=self.__class__.MANAGEMENT,
        )
        timetable = serializer.serialize_timetable(strip_empty_days=True)

        published = contribution_settings.get(self.event, "published")

        unscheduled = (
            serializer.serialize_unscheduled_contributions()
            if self.__class__.MANAGEMENT
            else []
        )

        for index, (key, __) in enumerate(
            sorted(serializer.room_map.items(), key=lambda item: item[1]["capacity"])
        ):
            serializer.room_map[key]["index"] = index + 1

        return WPNGTimetable(
            self,
            self.event,
            management=self.__class__.MANAGEMENT,
            unscheduled=unscheduled,
            timetable=timetable,
            rooms=serializer.room_map,
            published=published,
            granularity=granularity,
            hours_per_screen=hours_per_screen,
        ).display()


class RHNGTimetableManage(RHNGTimetable):
    MANAGEMENT = True

    def _check_access(self):
        super()._check_access()
        if not self.event.can_manage(session.user):
            raise Forbidden()


class RNHGTimetableOperationsBase(RHManageEventBase):
    def _check_access(self):
        super()._check_access()
        if not self.event.can_manage(session.user):
            raise Forbidden()

    def _process_args(self):
        super()._process_args()

        self.targetSessionTimetableEntry = None
        self.session = None
        if request.json.get("session", None):
            self.targetSessionTimetableEntry = self.event.timetable_entries.filter_by(
                id=request.json["session"]
            ).first_or_404()
            self.session = self.targetSessionTimetableEntry.session_block.session

        if "timezone" in request.json["startDate"]:
            tz = pytz.timezone(request.json["startDate"]["timezone"])
        else:
            tz = self.event.tzinfo

        self.new_start_dt = tz.localize(
            dateutil.parser.parse("{date}T{time}".format(**request.json["startDate"]))
        ).astimezone(pytz.utc)

        json_location_data = request.json["locationData"]
        location_data = {"inheriting": json_location_data["inheriting"]}
        if "room_id" in json_location_data and "venue_id" in json_location_data:
            location_data["room"] = Room.get(int(json_location_data["room_id"]))
            location_data["venue"] = Location.get(int(json_location_data["venue_id"]))
        elif "room_name" in json_location_data:
            location_data["room_name"] = json_location_data["room_name"]

        self.contrib_updates = {
            "location_data": location_data,
            "session": None,
            "session_block": None,
        }

        if self.targetSessionTimetableEntry:
            self.contrib_updates[
                "session"
            ] = self.targetSessionTimetableEntry.session_block.session
            self.contrib_updates[
                "session_block"
            ] = self.targetSessionTimetableEntry.session_block


class RHNGTimetableMove(RNHGTimetableOperationsBase):
    POST_JSON_SCHEMA = {
        "type": "object",
        "properties": {
            "swapWith": {
                "anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]
            },
            "session": {"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]},
            "locationData": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": {
                            "inheriting": {"type": "boolean"},
                            "room_id": {"type": "integer", "minimum": 1},
                            "venue_id": {"type": "integer", "minimum": 1},
                        },
                        "additionalProperties": False,
                        "required": ["inheriting", "room_id", "venue_id"],
                    },
                    {
                        "type": "object",
                        "properties": {
                            "inheriting": {"type": "boolean"},
                            "room_name": {"type": "string"},
                        },
                        "additionalProperties": False,
                        "required": ["inheriting", "room_name"],
                    },
                ]
            },
            "startDate": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "format": "date"},
                    "time": {"type": "string", "format": "time"},
                    "timezone": {"type": "string"},
                },
                "additionalProperties": False,
                "required": ["date", "time"],
            },
        },
        "required": ["locationData", "startDate"],
        "additionalProperties": False,
    }

    def _process_args(self):
        super()._process_args()
        self.validate_json(RHNGTimetableMove.POST_JSON_SCHEMA)

        self.entry = None
        self.swapEntry = None
        if "entry_id" in request.view_args:
            self.entry = self.event.timetable_entries.filter_by(
                id=request.view_args["entry_id"]
            ).first_or_404()
            self.contribution = self.entry.contribution
        if request.json.get("swapWith", None):
            self.swapEntry = self.event.timetable_entries.filter_by(
                id=request.json["swapWith"]
            ).first_or_404()

    def _process_POST(self):
        with (
            track_time_changes(auto_extend=True, user=session.user),
            track_location_changes(),
        ):
            if self.swapEntry:
                swapParent = None
                if self.entry.session_block:
                    swapParent = self.event.timetable_entries.filter_by(
                        id=self.entry.session_block.session.id
                    ).first_or_404()

                update_timetable_entry(
                    self.swapEntry,
                    {
                        "start_dt": self.entry.contribution.start_dt,
                        "parent": swapParent,
                    },
                )
                update_contribution(
                    self.swapEntry.contribution,
                    {
                        "location_data": self.entry.contribution.location_data,
                        "session_block": self.entry.session_block,
                        "session": self.entry.session_block.session
                        if self.entry.session_block
                        else None,
                    },
                )

            update_timetable_entry(
                self.entry,
                {
                    "parent": self.targetSessionTimetableEntry,
                    "start_dt": self.new_start_dt,
                },
            )
            update_contribution(self.contribution, self.contrib_updates)

        return jsonify_data(flash=False)


class RHNGTimetableSchedule(RNHGTimetableOperationsBase):
    def _process_args(self):
        super()._process_args()
        self.contrib = (
            Contribution.query.with_parent(self.event)
            .filter_by(id=request.view_args["contrib_id"])
            .first_or_404()
        )

    def _process_POST(self):
        with (
            track_time_changes(auto_extend=False, user=session.user),
            track_location_changes(),
        ):
            update_contribution(self.contrib, self.contrib_updates)
            session_block = (
                self.targetSessionTimetableEntry.session_block
                if self.targetSessionTimetableEntry
                else None
            )

            entry = schedule_contribution(
                self.contrib,
                self.new_start_dt,
                session_block=session_block,
                extend_parent=False,
            )

        return jsonify_data(flash=False, id=entry.id)


class RHNGTimetableEventSettings(RHManageEventBase):
    def _process_args(self):
        super()._process_args()
        from .plugin import NGTimetablePlugin

        self.plugin = NGTimetablePlugin

    def _process(self):
        plugin_event_settings = self.plugin.event_settings.get_all(self.event)
        defaults = FormDefaults(
            {k: v for k, v in plugin_event_settings.items() if v is not None}
        )

        form = NGTimetableSettingsForm(obj=defaults)
        if form.validate_on_submit():
            self.plugin.event_settings.set_multi(self.event, form.data)
            flash(_("NGTimetable settings saved"), "success")

        return WPNGTimetableSettings.render_template(
            "ngtimetable_settings.html", self.event, form=form
        )
