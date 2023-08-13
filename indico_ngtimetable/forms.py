from indico.web.forms.base import IndicoForm
from indico.web.forms.widgets import SwitchWidget
from markupsafe import Markup
from wtforms import Field
from wtforms.fields import BooleanField

from . import _


class HTMLDescriptionField(Field):
    def __init__(self, label="", validators=None, html="", **kwargs):
        super(HTMLDescriptionField, self).__init__(label, validators, **kwargs)
        self.html = html

    def __call__(self, **kwargs):
        return Markup(self.html)


class NGTimetableSettingsForm(IndicoForm):
    default_settings = {"timetable_use_track_colors": True}

    timetable_use_track_colors = BooleanField(
        _("Prefer Track Colors"),
        widget=SwitchWidget(),
        description=_(
            "Prefer the track's default session color in the timetable. Use this to assign colors by tracks instead of sessions. Make sure you DON'T assign contributions to a session if you want them to show up on the main schedule."
        ),
    )
