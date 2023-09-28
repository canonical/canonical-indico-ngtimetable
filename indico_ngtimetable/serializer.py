import copy
import math
from datetime import datetime

from indico.modules.events.contributions.models.contributions import Contribution
from indico.modules.events.contributions.models.persons import AuthorType
from indico.modules.events.timetable.legacy import TimetableSerializer
from indico.modules.events.timetable.models.entries import (
    TimetableEntry,
    TimetableEntryType,
)
from indico.util.date_time import iterdays
from indico.web.flask.util import url_for
from sqlalchemy.orm import defaultload

from . import _


class NoTrack:
    def __init__(self):
        self.default_session = {"background_color": "f8f2e8", "text_color": "000000"}
        self.id = 0
        self.title = "(No Track)"


class NGTimetableSerializer(TimetableSerializer):
    def __init__(
        self,
        *args,
        hour_padding=1,
        granularity=30,
        use_track_colors=True,
        excludeRooms=set(),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.hour_padding = hour_padding
        self.use_track_colors = use_track_colors
        self._in_session_block = False
        self.tracks = set()
        self.noTrack = NoTrack()
        self.excludeRooms = excludeRooms

        self.granularity = granularity
        self.units_per_hour = 60 // self.granularity

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        self.max_date = tzinfo.localize(
            datetime.max.replace(year=datetime.max.year - 1)
        )
        self.min_date = tzinfo.localize(
            datetime.min.replace(year=datetime.min.year + 1)
        )

    def serialize_timetable(
        self, days=None, hide_weekends=False, strip_empty_days=False, **kwargs
    ):
        self._earliest_start = {}
        self._latest_end = {}
        self.room_map = {}

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
            timetable[date_str] = {
                "weekday": _(day.strftime("%A")),
                "date": day.date(),
                "day_start": 0,
                "day_end": 23,
                "timetable": {},
            }

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
            if data["location_data"]["room_name"] in self.excludeRooms:
                continue
            key = self._get_entry_key(entry)
            end_dt_key = entry.end_dt.astimezone(tzinfo).date().strftime("%Y%m%d")
            pastmidnight = (
                entry.start_dt.astimezone(tzinfo).date()
                != entry.end_dt.astimezone(tzinfo).date()
            )
            nextdaydata = (
                self.split_entry_dayboundary(entry, data) if pastmidnight else None
            )

            if entry.parent:
                parent_code = f"s{entry.parent_id}"
                timetable[date_str]["timetable"][parent_code]["entries"][key] = data
                if nextdaydata:
                    timetable[end_dt_key]["timetable"][parent_code]["entries"][
                        key
                    ] = nextdaydata
            else:
                timetable[date_str]["timetable"][key] = data
                if nextdaydata:
                    timetable[end_dt_key]["timetable"][key] = nextdaydata

        for key in timetable:
            if key in self._earliest_start:
                timetable[key]["day_start"] = max(
                    0, self._earliest_start[key].time().hour - self.hour_padding
                )
            if key in self._latest_end:
                timetable[key]["day_end"] = min(
                    23, self._latest_end[key].time().hour + self.hour_padding
                )

        if strip_empty_days:
            timetable = self._strip_empty_days(timetable)

        return timetable

    def split_entry_dayboundary(self, entry, data):
        # If an entry lasts into another day we need to add it to that day, too
        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        start_dt_key = entry.start_dt.astimezone(tzinfo).date().strftime("%Y%m%d")
        end_dt_key = entry.end_dt.astimezone(tzinfo).date().strftime("%Y%m%d")
        end_dt = entry.end_dt.astimezone(tzinfo).date().strftime("%Y-%m-%d")
        nextdaydata = copy.deepcopy(data)

        # Adjust dates so it appears to go until the end of the day
        units_per_day = 24 * self.units_per_hour
        nextdayspan = data["timeunit_start"] + data["timeunit_span"] - units_per_day - 1

        data["timeunit_span"] -= nextdayspan
        data["endDate"]["time"] = "00:00:00"
        data["startDate"]["date"] = end_dt

        nextdaydata["timeunit_span"] = nextdayspan
        nextdaydata["timeunit_start"] = 1
        nextdaydata["startDate"]["time"] = "00:00:00"
        nextdaydata["startDate"]["date"] = end_dt

        self._earliest_start[end_dt_key] = entry.end_dt.astimezone(tzinfo).replace(
            hour=0, minute=0, second=0
        )
        self._latest_end[start_dt_key] = entry.start_dt.astimezone(tzinfo).replace(
            hour=23, minute=59, second=59
        )

        return nextdaydata

    def serialize_unscheduled_contributions(self):
        query_options = (
            defaultload("abstract"),
            defaultload("person_links"),
            defaultload("subcontribution"),
        )
        query = (
            Contribution.query.with_parent(self.event)
            .options(*query_options)
            .filter(~Contribution.is_scheduled)
        )

        unscheduled = []
        for contribution in query:
            data = {
                "contributionId": contribution.id,
                "entryType": "Contribution",
                "title": contribution.title,
                "description": contribution.description,
                "duration": contribution.duration_display.seconds // 60,
                "trackId": contribution.track.id if contribution.track else 0,
                "url": url_for("contributions.display_contribution", contribution),
                "timeunit_span": math.ceil(
                    contribution.duration_display.seconds // 60 / self.granularity
                ),
                "location_data": {"room_name": "", "room_id": ""},
                "abstract_score": (
                    contribution.abstract.score if contribution.abstract else 0
                )
                or 0,
                "presenters": list(
                    map(
                        self._get_person_data,
                        sorted(
                            (p for p in contribution.person_links if p.is_speaker),
                            key=lambda x: (
                                x.author_type != AuthorType.primary,
                                x.author_type != AuthorType.secondary,
                                x.display_order_key,
                            ),
                        ),
                    )
                ),
                "_obj": contribution,
            }
            data["subcontributions"] = [
                self.serialize_subcontribution(x) for x in contribution.subcontributions
            ]

            if contribution.session:
                data.update(self._get_color_data(contribution.session))
            elif (
                self.use_track_colors
                and contribution.track
                and contribution.track.default_session
            ):
                data.update(self._get_color_data(contribution.track.default_session))

            unscheduled.append(data)

        return sorted(
            unscheduled, key=lambda val: (val["abstract_score"], -val["duration"])
        )

    def _get_location_data(self, obj):
        data = {}

        location_data = obj.location_data

        data["location_data"] = {
            "room_name": location_data["room_name"],
            "room_id": location_data["room"].id if location_data["room"] else "",
            "venue_name": location_data["venue_name"],
            "venue_id": location_data["venue"].id if location_data["venue"] else "",
            "capacity": location_data["room"].capacity if location_data["room"] else 0,
        }
        return data

    def _update_day_range(self, entry):
        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo

        start_dt = entry.start_dt.astimezone(tzinfo)
        end_dt = entry.end_dt.astimezone(tzinfo)
        startkey = start_dt.strftime("%Y%m%d")
        endkey = end_dt.strftime("%Y%m%d")

        self._earliest_start[startkey] = min(
            self._earliest_start.get(startkey, self.max_date), start_dt
        )
        self._latest_end[endkey] = max(
            self._latest_end.get(endkey, self.min_date), end_dt
        )

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

        data["timeunit_start"] = (
            (60 * start_dt.hour + start_dt.minute) // self.granularity
        ) + 1
        data["timeunit_span"] = math.ceil(
            entry.duration.total_seconds() / 60 / self.granularity
        )

        self._update_day_range(entry)

        return data

    def serialize_session_block_entry(self, entry, load_children=True):
        self._in_session_block = True
        data = super().serialize_session_block_entry(entry, load_children)
        data.update(self._get_ng_entry_data(entry))

        room_name = entry.session_block.room_name
        if room_name not in self.excludeRooms and room_name not in self.room_map:
            self.room_map[room_name] = self._get_location_data(entry.session_block)[
                "location_data"
            ]

        data["_obj"] = entry.session_block

        self._in_session_block = False
        return data

    def serialize_contribution_entry(self, entry):
        data = super().serialize_contribution_entry(entry)
        data.update(self._get_ng_entry_data(entry))
        if entry.contribution.track:
            data["trackId"] = entry.contribution.track.id
            self.tracks.add(entry.contribution.track)
        else:
            data["trackId"] = 0
            self.tracks.add(self.noTrack)

        room_name = entry.contribution.room_name
        if self._in_session_block:
            # Force room to be the session block room
            data["location_data"] = {"inheriting": True}
        elif room_name not in self.excludeRooms and room_name not in self.room_map:
            self.room_map[room_name] = self._get_location_data(entry.contribution)[
                "location_data"
            ]

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

        data["_obj"] = entry.contribution

        return data

    def serialize_subcontribution(self, subcontribution):
        return {
            "entryType": "Subcontribution",
            "subcontributionId": subcontribution.id,
            "duration": subcontribution.duration.total_seconds() // 60,
            "title": subcontribution.title,
            "description": subcontribution.description,
            "url": url_for("contributions.display_subcontribution", subcontribution),
            "_obj": subcontribution,
        }

    def serialize_break_entry(self, entry, management=False):
        data = super().serialize_break_entry(entry, management)
        data.update(self._get_ng_entry_data(entry))
        return data
