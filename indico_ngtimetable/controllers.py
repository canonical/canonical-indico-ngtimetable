import dateutil.parser
import pytz
from flask import request, session
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
from indico.web.util import jsonify_data
from werkzeug.exceptions import Forbidden

from .serializer import NGTimetableSerializer
from .views import WPNGTimetable


class RHNGTimetable(RHTimetableProtectionBase):
    MANAGEMENT = False

    def _process_args(self):
        super()._process_args()

        from .plugin import NGTimetablePlugin

        self.plugin = NGTimetablePlugin

    def _process(self):
        self.event.preload_all_acl_entries()
        use_track_colors = self.plugin.settings.get("timetable_use_track_colors")

        serializer = NGTimetableSerializer(
            self.event,
            use_track_colors=use_track_colors,
            management=self.__class__.MANAGEMENT,
        )
        timetable = serializer.serialize_timetable(strip_empty_days=True)

        published = contribution_settings.get(self.event, "published")

        unscheduled = (
            serializer.serialize_unscheduled_contributions()
            if self.__class__.MANAGEMENT
            else []
        )

        return WPNGTimetable(
            self,
            self.event,
            management=self.__class__.MANAGEMENT,
            unscheduled=unscheduled,
            timetable=timetable,
            rooms=serializer.room_map,
            published=published,
        ).display()


class RHNGTimetableManage(RHNGTimetable):
    MANAGEMENT = True

    def _check_access(self):
        if not self.event.can_manage(session.user):
            raise Forbidden()


class RHNGTimetableMove(RHManageEventBase):
    POST_JSON_SCHEMA = {
        "type": "object",
        "properties": {
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
                    },
                    {
                        "type": "object",
                        "properties": {
                            "inheriting": {"type": "boolean"},
                            "room_name": {"type": "string"},
                        },
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
            },
        },
    }

    def _check_access(self):
        if not self.event.can_manage(session.user):
            raise Forbidden()

    def _process_args(self):
        super()._process_args()
        self.validate_json(RHNGTimetableMove.POST_JSON_SCHEMA)

        self.entry = None
        if "entry_id" in request.view_args:
            self.entry = self.event.timetable_entries.filter_by(
                id=request.view_args["entry_id"]
            ).first_or_404()
            self.contribution = self.entry.contribution
            print("CA", self.contribution)

        self.targetSessionTimetableEntry = None
        self.session = None
        if request.json.get("session", None):
            self.targetSessionTimetableEntry = self.event.timetable_entries.filter_by(
                id=request.json["session"]
            ).first_or_404()
            self.session = self.targetSessionTimetableEntry.session_block.session

    def _process_POST(self):
        tz = pytz.timezone(request.json["startDate"]["timezone"])
        new_start_dt = tz.localize(
            dateutil.parser.parse("{date}T{time}".format(**request.json["startDate"]))
        ).astimezone(pytz.utc)

        json_location_data = request.json["locationData"]
        location_data = {"inheriting": json_location_data["inheriting"]}
        if "room_id" in json_location_data and "venue_id" in json_location_data:
            location_data["room"] = Room.get(int(json_location_data["room_id"]))
            location_data["venue"] = Location.get(int(json_location_data["venue_id"]))
        elif "room_name" in json_location_data:
            location_data["room_name"] = json_location_data["room_name"]

        with (
            track_time_changes(auto_extend=True, user=session.user),
            track_location_changes(),
        ):
            tt_updates = {
                "parent": self.targetSessionTimetableEntry,
                "start_dt": new_start_dt,
            }
            contrib_updates = {
                "location_data": location_data,
                "session": None,
                "session_block": None,
            }
            if self.targetSessionTimetableEntry:
                contrib_updates[
                    "session"
                ] = self.targetSessionTimetableEntry.session_block.session
                contrib_updates[
                    "session_block"
                ] = self.targetSessionTimetableEntry.session_block

            update_timetable_entry(self.entry, tt_updates)
            update_contribution(self.contribution, contrib_updates)

        return jsonify_data(flash=False)


class RHNGTimetableSchedule(RHManageEventBase):
    def _process_args(self):
        super()._process_args()
        self.contrib = (
            Contribution.query.with_parent(self.event)
            .filter_by(id=request.view_args["contrib_id"])
            .first_or_404()
        )

    def _process_POST(self):
        tz = pytz.timezone(request.json["startDate"]["timezone"])
        new_start_dt = tz.localize(
            dateutil.parser.parse("{date}T{time}".format(**request.json["startDate"]))
        ).astimezone(pytz.utc)

        json_location_data = request.json["locationData"]
        location_data = {"inheriting": json_location_data["inheriting"]}
        if "room_id" in json_location_data and "venue_id" in json_location_data:
            location_data["room"] = Room.get(int(json_location_data["room_id"]))
            location_data["venue"] = Location.get(int(json_location_data["venue_id"]))
        elif "room_name" in json_location_data:
            location_data["room_name"] = json_location_data["room_name"]

        session_block = None
        if request.json["session"]:
            session_block = self.event.get_session_block(request.json["session"])

        with (
            track_time_changes(auto_extend=False, user=session.user),
            track_location_changes(),
        ):
            contrib_updates = {
                "location_data": location_data,
                "session": session_block.session if session_block else None,
                "session_block": session_block,
            }
            update_contribution(self.contrib, contrib_updates)
            entry = schedule_contribution(
                self.contrib,
                new_start_dt,
                session_block=session_block,
                extend_parent=False,
            )

        return jsonify_data(flash=False, id=entry.id)
