import math
from datetime import datetime

from indico.modules.events.timetable.legacy import TimetableSerializer
from indico.modules.events.timetable.models.entries import TimetableEntryType

from . import _


class NGTimetableSerializer(TimetableSerializer):
    def __init__(self, *args, hour_padding=1, use_track_colors=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.hour_padding = hour_padding
        self.use_track_colors = use_track_colors
        self._contrib_maxlen = 0

    def serialize_timetable(self, **kwargs):
        self.room_map = {}
        self._lastsessionhour = {}

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        self._day_start_time = self.event.start_dt.astimezone(tzinfo).hour
        day_start = self._day_start_time - self.hour_padding
        if day_start < 0:
            day_start = self._day_start_time
            self.hour_padding = 0

        data = super().serialize_timetable(**kwargs)

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
            math.ceil((60 * start_dt.hour + start_dt.minute) / 30)
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
        data = super().serialize_session_block_entry(entry, load_children)
        data.update(self._get_ng_entry_data(entry))

        if entry.session_block.room_name not in self.room_map:
            self.room_map[entry.session_block.room_name] = len(self.room_map) + 1

        tzinfo = self.event.tzinfo if self.management else self.event.display_tzinfo
        daykey = entry.start_dt.astimezone(tzinfo).strftime("%Y%m%d")
        endhour = entry.end_dt.astimezone(tzinfo).time().hour
        self._lastsessionhour[daykey] = max(
            self._lastsessionhour.get(daykey, 0), endhour
        )

        data["contribution_maxlen"] = self._contrib_maxlen
        return data

    def serialize_contribution_entry(self, entry):
        data = super().serialize_contribution_entry(entry)
        data.update(self._get_ng_entry_data(entry))
        self._contrib_maxlen = max(self._contrib_maxlen, data["duration"])

        if entry.contribution.room_name not in self.room_map:
            self.room_map[entry.contribution.room_name] = len(self.room_map) + 1

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

        return data

    def serialize_break_entry(self, entry, management=False):
        data = super().serialize_break_entry(entry, management)
        data.update(self._get_ng_entry_data(entry))
        return data
