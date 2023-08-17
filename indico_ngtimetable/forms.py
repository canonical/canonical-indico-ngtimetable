from indico.web.forms.base import IndicoForm
from indico.web.forms.widgets import SwitchWidget
from wtforms.fields import BooleanField

from . import _


class NGTimetableSettingsForm(IndicoForm):
    default_settings = {"timetable_use_track_colors": True}

    timetable_use_track_colors = BooleanField(
        _("Prefer Track Colors"),
        widget=SwitchWidget(),
        description=_(
            "Prefer the track's default session color in the timetable. Use this to assign colors by tracks instead of sessions. Make sure you DON'T assign contributions to a session if you want them to show up on the main schedule."
        ),
    )
