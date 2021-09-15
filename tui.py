import random, time

from asciimatics.widgets import Frame, TextBox, Layout, Label, Divider, Text, \
    Button, PopUpDialog, frame
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError, NextScene, StopApplication, \
    InvalidFields
import sys

# Initial data for the form
form_data = {
    "TA": ["Hello world!", "How are you?"],
    "TB": "alphabet",
    "TC": "123",
    "TD": "a@b.com",
    "Things": 2,
    "CA": False,
    "CB": True,
    "CC": False,
}


class DemoFrame(Frame):
    MAX_ROW = 17
    def __init__(self, screen):
        super(DemoFrame, self).__init__(screen,
                                        int(screen.height),
                                        int(screen.width),
                                        data=form_data,
                                        has_shadow=True,
                                        name="Bms3ToolConsole")
        layout = Layout([1])
        self.add_layout(layout)
        self.bms_id = random.randrange(1000000, 50000000)
        self.bal_id = random.randrange(1000000, 50000000)
        layout.add_widget(Label("BMS ID: 0x%x" % self.bms_id), 0)
        layout.add_widget(Label("BAL ID: 0x%x" % self.bal_id), 0)

        layout.add_widget(Divider(height=2), 0)
        self.table_layout = Layout([2] + [1] * self.MAX_ROW)
        self.add_layout(self.table_layout)
        self.table_layout.add_widget(Label("CELL NUM:"), 0)
        self.table_layout.add_widget(Label("CELL V:"), 0)
        self.table_layout.add_widget(Label("CELL T:"), 0)
        for i in range(1, self.MAX_ROW):
            tlbl = Text(readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="%d" % i
            self.table_layout.add_widget(tlbl, i)
            tlbl = Text(name="v%d" % i, readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="%.2f" % (random.randrange(2500, 3800) / 1000)
            self.table_layout.add_widget(tlbl, i)
            tlbl = Text(name="t%d" % i, readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="%d" % random.randrange(10, 48)
            self.table_layout.add_widget(tlbl, i)
        layout2 = Layout([1])
        self.add_layout(layout2)
        layout2.add_widget(Divider(height=2), 0)
        layout2.add_widget(Button("Quit", self._quit), 0)
        self.find_widget(name="v1")
        self.fix()

    def _on_change(self):
        changed = False
        self.save()
        for key, value in self.data.items():
            if key not in form_data or form_data[key] != value:
                changed = True
                break

    def _reset(self):
        self.reset()
        raise NextScene()

    def _view(self):
        # Build result of this form and display it.
        try:
            self.save(validate=True)
            message = "Values entered are:\n\n"
            for key, value in self.data.items():
                message += "- {}: {}\n".format(key, value)
        except InvalidFields as exc:
            message = "The following fields are invalid:\n\n"
            for field in exc.fields:
                message += "- {}\n".format(field)
        self._scene.add_effect(
            PopUpDialog(self._screen, message, ["OK"]))

    def _quit(self):
        self._scene.add_effect(
            PopUpDialog(self._screen,
                        "Are you sure?",
                        ["Yes", "No"],
                        on_close=self._quit_on_yes))

    @staticmethod
    def _quit_on_yes(selected):
        # Yes is the first button
        if selected == 0:
            raise StopApplication("User requested exit")


screen = Screen.open()
frame = DemoFrame(screen)
scenes = [
    Scene([ frame ]),
]
screen.set_scenes(scenes)
while True:
    try:
        screen.draw_next_frame(repeat=True)
        time.sleep(1)
        new_data = {}
        for i in range(1, frame.MAX_ROW):
            new_data["v%d" % i] = "%.2f" % (random.randrange(2500, 3800) / 1000)
            new_data["t%d" % i] = "%d" % random.randrange(10, 48)
        frame.data = new_data
        screen.force_update()
    except ResizeScreenError as e:
        last_scene = e.scene
    except StopApplication as e:
        sys.exit(0)