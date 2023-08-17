import math
from datetime import datetime

from indico.modules.events.timetable.legacy import TimetableSerializer
from indico.modules.events.timetable.models.entries import TimetableEntryType
from indico.web.flask.util import url_for

from . import _


class NGTimetableSerializer(TimetableSerializer):
    def __init__(self, *args, hour_padding=1, use_track_colors=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.hour_padding = hour_padding
        self.use_track_colors = use_track_colors
        self._contrib_maxlen = 0
        self._in_session_block = False

    def _orig_serialize_timetable(
        self, days=None, hide_weekends=False, strip_empty_days=False, **kwargs
    ):
        """
        This is basically Indico's serialize_timetable, but I needed to add loading
        subcontributions to the SQLalchemy loading strategy.
        """
        from indico.modules.events.timetable.models.entries import TimetableEntry
        from indico.util.date_time import iterdays
        from sqlalchemy.orm import defaultload

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        self.event.preload_all_acl_entries()
        timetable = {}
        for day in iterdays(
            self.event.start_dt.astimezone(tzinfo),
            self.event.end_dt.astimezone(tzinfo),
            skip_weekends=hide_weekends,
            day_whitelist=days,
        ):
            date_str = day.strftime("%Y%m%d")
            timetable[date_str] = {}

        contributions_strategy = defaultload("contribution")
        contributions_strategy.subqueryload("person_links")
        contributions_strategy.subqueryload("references")
        contributions_strategy.subqueryload("subcontributions")
        query_options = (
            contributions_strategy,
            defaultload("session_block").subqueryload("person_links"),
        )
        query = (
            TimetableEntry.query.with_parent(self.event)
            .options(*query_options)
            .order_by(TimetableEntry.type != TimetableEntryType.SESSION_BLOCK)
        )

        for entry in query:
            day = entry.start_dt.astimezone(tzinfo).date()
            date_str = day.strftime("%Y%m%d")
            if date_str not in timetable:
                continue
            if not entry.can_view(self.user):
                continue
            data = self.serialize_timetable_entry(entry, load_children=False)
            key = self._get_entry_key(entry)
            if entry.parent:
                parent_code = f"s{entry.parent_id}"
                timetable[date_str][parent_code]["entries"][key] = data
            else:
                if (
                    entry.type == TimetableEntryType.SESSION_BLOCK
                    and entry.start_dt.astimezone(tzinfo).date()
                    != entry.end_dt.astimezone(tzinfo).date()
                ):
                    # If a session block lasts into another day we need to add it to that day, too
                    timetable[
                        entry.end_dt.astimezone(tzinfo).date().strftime("%Y%m%d")
                    ][key] = data
                timetable[date_str][key] = data
        if strip_empty_days:
            timetable = self._strip_empty_days(timetable)
        return timetable

    def serialize_timetable(self, **kwargs):
        self.room_map = {}
        self._lastsessionhour = {}

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        self._day_start_time = self.event.start_dt.astimezone(tzinfo).hour
        day_start = self._day_start_time - self.hour_padding
        if day_start < 0:
            day_start = self._day_start_time
            self.hour_padding = 0

        data = self._orig_serialize_timetable(**kwargs)

        for key in data:
            keydate = datetime.strptime(key, "%Y%m%d").date()
            data[key] = {
                "weekday": _(keydate.strftime("%A")),
                "date": keydate,
                "day_start": day_start,
                "day_end": self._lastsessionhour[key] + self.hour_padding,
                "timetable": data[key],
            }

        return data

    def _get_location_data(self, obj):
        data = {}
        data["location_data"] = obj.widget_location_data
        return data

    def _get_ng_entry_data(self, entry):
        data = {}

        if entry.type == TimetableEntryType.CONTRIBUTION:
            start_dt = entry.contribution.start_dt_display
            end_dt = entry.contribution.end_dt_display
        else:
            start_dt = entry.start_dt
            end_dt = entry.end_dt

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        start_dt = start_dt.astimezone(tzinfo)
        end_dt = end_dt.astimezone(tzinfo)

        halfhours = (
            math.floor((60 * start_dt.hour + start_dt.minute) / 30)
            - 2 * self._day_start_time
            + 1
            + (2 * self.hour_padding)
        )
        data["halfhour_start"] = halfhours

        halfhours = (
            math.ceil(
                (60 * end_dt.hour + end_dt.minute) / 30
            )  # half hours since beginning of day
            - 2 * self._day_start_time  # remove half hours before the day started
            + 1  # Add one since CSS is 1-based
            + (2 * self.hour_padding)  # Add hour padding to the beginning/end
        )
        data["halfhour_span"] = halfhours - data["halfhour_start"]

        return data

    def serialize_session_block_entry(self, entry, load_children=True):
        self._contrib_maxlen = 0
        self._in_session_block = True
        data = super().serialize_session_block_entry(entry, load_children)
        data.update(self._get_ng_entry_data(entry))

        if entry.session_block.room_name not in self.room_map:
            room_data = entry.session_block.widget_location_data
            room_data["index"] = len(self.room_map) + 1
            self.room_map[entry.session_block.room_name] = room_data

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        daykey = entry.start_dt.astimezone(tzinfo).strftime("%Y%m%d")
        endhour = entry.end_dt.astimezone(tzinfo).time().hour
        self._lastsessionhour[daykey] = max(
            self._lastsessionhour.get(daykey, 0), endhour
        )

        data["contribution_maxlen"] = self._contrib_maxlen
        self._in_session_block = False
        return data

    def serialize_contribution_entry(self, entry):
        data = super().serialize_contribution_entry(entry)
        data.update(self._get_ng_entry_data(entry))
        self._contrib_maxlen = max(self._contrib_maxlen, data["duration"])

        if self._in_session_block:
            # Force room to be the session block room
            data["location_data"] = {"inheriting": True}
        elif entry.contribution.room_name not in self.room_map:
            room_data = entry.contribution.widget_location_data
            room_data["index"] = len(self.room_map) + 1
            self.room_map[entry.contribution.room_name] = room_data

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        daykey = entry.start_dt.astimezone(tzinfo).strftime("%Y%m%d")
        endhour = entry.end_dt.astimezone(tzinfo).time().hour
        self._lastsessionhour[daykey] = max(
            self._lastsessionhour.get(daykey, 0), endhour
        )

        if (
            self.use_track_colors
            and entry.contribution.track
            and entry.contribution.track.default_session
        ):
            data.update(self._get_color_data(entry.contribution.track.default_session))

        data["subcontributions"] = [
            self.serialize_subcontribution(x)
            for x in entry.contribution.subcontributions
        ]

        return data

    def serialize_subcontribution(self, subcontribution):
        return {
            "entryType": "Subcontribution",
            "subcontributionId": subcontribution.id,
            "duration": subcontribution.duration.total_seconds() / 60.0,
            "title": subcontribution.title,
            "description": subcontribution.description,
            "url": url_for("contributions.display_contribution", subcontribution),
        }

    def serialize_break_entry(self, entry, management=False):
        data = super().serialize_break_entry(entry, management)
        data.update(self._get_ng_entry_data(entry))
        return data
