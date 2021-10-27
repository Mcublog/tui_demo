import threading, queue
import os, pathlib, time, argparse

from asciimatics.widgets import Frame, TextBox, Layout, Label, Divider, Text, Button, PopUpDialog
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.exceptions import ResizeScreenError, NextScene

from bms3_base.bms3_dongle import BMS3Client
from bms3_base.params import get_bitflags
import emulib.tools.emulib_debug_print as my_print
from emulib.tools.emulib_console_helper import DEFAULT_UART_SPEED

if os.name == "posix":
    my_print.DO_PRINT = False
    my_print.DO_DEBUG_PRINT = False
    my_print.DO_ERROR_PRINT = False


class ExitFromApp(Exception):
    pass

os.system('mode con: cols=120 lines=29')

class FlagFrame(Frame):
    FLAGS_NUMBER_IN_ROW = 8
    def __init__(self, screen, callbacks):
        super(FlagFrame, self).__init__(screen,
                                        int(screen.height),
                                        int(screen.width),
                                        data=None,
                                        has_shadow=True,
                                        name="FlagDescription")
        self.callbacks = callbacks
        self.callbacks.update({"on_flag_handler": self.on_flag_handler})
        layout = Layout([1] * 2, False)
        self.add_layout(layout)
        bf = get_bitflags()
        for i in range(len(bf)):
            flag = Text(label=str(bf[i] + ":"), name=f"flag{i}", readonly=True, disabled=True, max_length=20)
            flag.custom_colour = "field"
            layout.add_widget(flag, column=int(i/16))

        layout = Layout([1])
        self.add_layout(layout)
        layout.add_widget(Divider())
        layout.add_widget(Button("Return to main screen", self._return), 0)
        self.fix()

    def _return(self):
        raise NextScene("Main")

    def on_flag_handler(self, data):
        if "flags" in data:
            bf = get_bitflags(data["flags"])
            for i, flag in enumerate(bf):
                f = self.find_widget(f"flag{i}")
                if f:
                    f.value = str(f"{bf[flag]}")



class BmsToolFrame(Frame):
    MAX_ROW = 17
    MAX_CRITICAL_TIMEOUTS_NUMBER = 3

    def __init__(self, screen, callbacks, init_data):
        super(BmsToolFrame, self).__init__(screen,
                                        int(screen.height),
                                        int(screen.width),
                                        data=init_data,
                                        has_shadow=True,
                                        name="Bms3ToolConsole")
        self.__first_run = True
        self.callbacks = callbacks
        self.callbacks.update(
            {
                "on_info_handler": self.on_info_handler,
                "on_status_handler": self.on_status_handler,
                "on_trace_handler": self.on_trace_handler,
                "on_timeout_handler": self.on_timeout_handler,
                "on_get_dongle_info_handler": self.on_get_dongle_info_handler,
                "on_port_disconnect": self.on_port_disconnect,
                "on_no_device_found": self.on_no_device_found
            })

        self.layout = Layout([1] * 2)
        self.add_layout(self.layout)
        bms_info = Text(label="BMS INFO:", name="bms_info_lbl", readonly=False, disabled=True)
        bms_info.custom_colour = "field"
        bal_info = Text(label="BAL INFO:", name="bal_info_lbl", readonly=False, disabled=True)
        bal_info.custom_colour = "field"
        bmsid = Text(label="BMS ID:", name="bms_id_lbl", readonly=False, disabled=True)
        bmsid.value = "-- "
        bmsid.custom_colour = "field"
        balid = Text(label="BAL ID:", name="bal_id_lbl", readonly=False, disabled=True)
        balid.value = " -- "
        balid.custom_colour = "field"
        self.layout.add_widget(bms_info, 0)
        self.layout.add_widget(bal_info, 0)
        self.layout.add_widget(bmsid, 1)
        self.layout.add_widget(balid, 1)

        self.layout = Layout([1] + [1] * self.MAX_ROW, fill_frame=False)
        self.add_layout(self.layout)
        self.layout.add_widget(Label("CELL NUM:"), 0)
        self.layout.add_widget(Label("CELL V:"), 0)
        self.layout.add_widget(Label("CELL T:"), 0)
        for i in range(1, self.MAX_ROW):
            tlbl = Text(readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="%d" % i
            self.layout.add_widget(tlbl, i)
            tlbl = Text(name="v%d" % i, readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="0.00"
            self.layout.add_widget(tlbl, i)
            tlbl = Text(name="t%d" % i, readonly=False, disabled=True)
            tlbl.custom_colour = "field"
            tlbl.value="0"
            self.layout.add_widget(tlbl, i)

        self.layout = Layout([1])
        self.add_layout(self.layout)
        self.layout.add_widget(Divider(height=1), 0)
        flags = Text(label="FLAGS:", name="flags_lbl", readonly=False, disabled=True)
        flags.custom_colour = "field"
        common = Text(label="COMMON:", name="common_lbl", readonly=False, disabled=True)
        common.custom_colour = "field"
        self.layout.add_widget(flags)
        self.layout.add_widget(common)

        self.layout = Layout([1])
        self.add_layout(self.layout)
        flags.custom_colour = "field"
        self.layout.add_widget(Button("Flag verbose", self._to_flag_description, add_box=True), 0)

        self.layout_trace = Layout([1], fill_frame=False)
        self.add_layout(self.layout_trace)
        self.layout_trace.add_widget(Divider(height=1), 0)
        text_box = TextBox(height=10, line_wrap=True, as_string = True, readonly=False, name="traces_box")
        text_box.custom_colour= "field"
        self.layout_trace.add_widget(text_box)

        self.layout = Layout([1])
        self.add_layout(self.layout)
        self.layout.add_widget(Divider(height=1), 0)
        path = Text(name="path", readonly=False, disabled=False, label="PATH TO TRACE FILE:")
        path_to_trace = pathlib.Path(__file__).parent.resolve()
        if os.name == "nt":
            path.value  = str(path_to_trace) + "\\traces.log"
        else:
            path.value  = str(path_to_trace) + "/traces.log"
        self.layout.add_widget(path, 0)
        self.layout.add_widget(Divider(height=1), 0)

        self.layout = Layout([1]*3)
        self.add_layout(self.layout)
        self.layout.add_widget(Button("Save trace", self._save_trace), 0)
        self.layout.add_widget(Button("Clear trace", self._clear_trace), 0)

        self.layout.add_widget(Button("Trace: ON", lambda: self.callbacks["trace_ctrl"](True)),       1)
        self.layout.add_widget(Button("Trace: OFF", lambda: self.callbacks["trace_ctrl"](False)),     1)

        self.layout.add_widget(Button("Trace BAL: ON", lambda: self.callbacks["bal_trace_ctrl"](True)),   2)
        self.layout.add_widget(Button("Trace BAL: OFF",lambda: self.callbacks["bal_trace_ctrl"](False)),  2)

        self.layout = Layout([1] * 2)
        self.add_layout(self.layout)
        self.layout.add_widget(Divider(height=1), 0)
        self.layout.add_widget(Divider(height=1), 1)
        self.layout.add_widget(Label(label=f"PORT: | CAN ADAPTER: ", name="port_info_lbl"))
        self.layout.add_widget(Button("Quit", self._quit), 1)

        self.fix()
        if "update_port_info" in self.callbacks:
            self.callbacks["update_port_info"]()

    def on_get_dongle_info_handler(self, portname:str, canadapter:bool, bms_id:int, bal_id:int):
        inf = self.find_widget("port_info_lbl")
        inf.text = f"PORT: {portname} | CAN ADAPTER: {canadapter}"
        inf = self.find_widget("bms_id_lbl")
        inf.value = "0x%x" % bms_id
        inf = self.find_widget("bal_id_lbl")
        inf.value = "0x%x" % bal_id

    def on_info_handler(self, data):
        device_name = data["name"] if "name" in data else None
        hardware_version = data["hwver"] if "hwver" in data else None
        firmware_version = data["fwver"] if "fwver" in data else None
        tlbl = self.find_widget("bms_info_lbl")
        if data["name"] == "BAL3" and tlbl:
            tlbl = self.find_widget("bal_info_lbl")
        if tlbl:
            tlbl.value = str(f"Name: {device_name} FW: {firmware_version} HW: {hardware_version}")

    def on_status_handler(self, data):
        if self.data["first_run"]:
            self.data["first_run"] = False
            if "trace_ctrl" in self.callbacks and "bal_trace_ctrl" in self.callbacks:
                self.callbacks["trace_ctrl"](True)
                self.callbacks["bal_trace_ctrl"](True)
        if "id" in data:
            v = self.find_widget("v%d" % (data["id"] + 1))
            if v:
                v.value = "%.3f" % (data["v"] / 1000)
            t = self.find_widget("t%d" % (data["id"] + 1))
            if t:
                t.value = str(data["t"])
        elif "flags" in data:
            flag_lbl = self.find_widget("flags_lbl")
            if flag_lbl:
                bf = get_bitflags(data["flags"])
                flag_state = str(bf.flags)
                for k,v in bf.items():
                    if v:
                        flag_state += f" | {k}"
                flag_lbl.value = flag_state
            common = self.find_widget("common_lbl")
            if common:
                status = ""
                for k, v in data.items():
                    if k != "flags" and k != "qty" and "v" in k or "curr" == k or "soc" == k:
                        mod = 1
                        if "v" in k:
                            mod = 1000
                        status += f"{k}: {v/mod if mod == 1000 else int(v/mod)} | "
                common.value = status

    def on_trace_handler(self, trace, trace_log:str) -> str:
        trace_log += trace
        text = self.find_widget("traces_box")
        if text:
            text.value = trace_log
        return trace_log

    def on_timeout_handler(self, timeouts):
        if timeouts > self.MAX_CRITICAL_TIMEOUTS_NUMBER:
            self._scene.add_effect(PopUpDialog(self._screen, f"Critical number of timeout error: {timeouts}. Exit from program", ["OK"], on_close=self._quit_on_yes))

    def get_traces(self) -> str:
        return self.find_widget("traces_box").value

    def _save_trace(self):
        path = self.find_widget("path")
        info_msg = "Trace saved: %s" % path.value
        theme = "green"
        try:
            with open(path.value, "w") as f:
                f.write(self.find_widget("traces_box").value)
        except:
            info_msg = "Trace NOT saved: %s" % path.value
            theme = "warrning"
        self._scene.add_effect(PopUpDialog(self._screen, info_msg, ["OK"], theme=theme))

    def _clear_trace(self):
        self._scene.add_effect(
                PopUpDialog(self._screen,
                            "Clear trace",
                            ["Yes", "No"],
                            on_close=self._clear_on_yes)
        )

    def _clear_on_yes(self, selected):
        if selected == 0:
            traces = self.find_widget("traces_box")
            if traces:
                if "on_clear_log" in self.callbacks:
                    self.callbacks["on_clear_log"]()
                traces.value = ""
                self.save()

    def _quit(self):
        self._scene.add_effect(
                PopUpDialog(self._screen,
                            "Are you sure?",
                            ["Yes", "No"],
                            on_close=self._quit_on_yes)
        )

    def _quit_on_yes(self, selected):
        # Yes is the first button
        if selected == 0:
            raise ExitFromApp("exit")

    def _to_flag_description(self):
        raise NextScene("FlagTable")

    def on_port_disconnect(self):
        self._scene.add_effect(PopUpDialog(self._screen, "Port is disconnect. Exit from program", ["OK"], on_close=self._quit_on_yes))

    def on_no_device_found(self):
        self._scene.add_effect(PopUpDialog(self._screen, "No device found on CAN bus. Exit from program", ["OK"], on_close=self._quit_on_yes))

class ConsoleDongle(BMS3Client):
    def __init__(self, serial_port, can_adapter=False, callbacks:dict={}):
        self.can_adapter = can_adapter
        self.__trace_log = ""
        self.timeouts = 0
        self.callbacks = {
            "on_clear_log": self.__on_clear_log,
            "trace_ctrl": self.trace_ctrl,
            "bal_trace_ctrl": self.bal_trace_ctrl,
            "update_port_info": self.update_port_info
        }

        self.callbacks.update(callbacks)
        self.msgq = queue.Queue()
        self._sender = threading.Thread(target=self.__sender, name="__sender", daemon=True)
        self._info_thread = threading.Thread(target=self.__info_updating, name="__info_updating", daemon=True)
        self._status_thread = threading.Thread(target=self.__status_updating, name="__status_updating", daemon=True)
        super().__init__(serial_port, DEFAULT_UART_SPEED, rtscts=False, can_adapter=can_adapter, key=None)
        if self._adapter.device_port == None:
            my_print.error_print(f"Port: {serial_port} is busy or wrong")
            return
        if can_adapter:
            self.enumeration(False)
            if self.get_devlist() == []:
                my_print.error_print(f"Devices on port: {serial_port} not found")
                return
    def is_open(self):
        return self._adapter.device_port

    def start(self):
        self.start_threads()
        self._sender.start()
        self._info_thread.start()
        self._status_thread.start()

    def send_data_to_port(self, data, channel=None, flags=None):
        if self._adapter.device_port:
            return super().send_data_to_port(data, channel=channel, flags=flags)
        return 0

    def stop_threads(self):
        self._info_thread.do_run = False
        self._status_thread.do_run = False
        self._sender.do_run = False
        try:
            self._info_thread.join()
            self._status_thread.join()
            self._sender.join()
        except:
            my_print.debug_print("port not open")
        return super().stop_threads()

    def __info_updating(self):
        t = threading.current_thread()
        cnt = 10
        while getattr(t, "do_run", True):
            time.sleep(0.1)
            cnt +=1
            if cnt >= 10:
                cnt = 0
                self.msgq.put(["info"])
                self.msgq.put(["infobal"])

    def __status_updating(self):
        t = threading.current_thread()
        cnt = 0
        while getattr(t, "do_run", True):
            cnt +=1
            if cnt >= 10:
                cnt = 0
                self.msgq.put(["status"])
                for i in range(16):
                    self.msgq.put(["status" ,{"id": i}])
                    time.sleep(0.01)
            time.sleep(0.1)

    def __sender(self):
        t = threading.current_thread()
        while getattr(t, "do_run", True):
            if self.is_open() == None:
                if "on_port_disconnect" in self.callbacks:
                    self.callbacks["on_port_disconnect"]()
            if not self.msgq.empty():
                if self.get_devlist() != None and len(self.get_devlist()) == 0 and "on_no_device_found" in self.callbacks:
                    self.callbacks["on_no_device_found"]()
                if self.send_data_to_port(self.msgq.get()):
                    self.timeouts += 1
                else:
                    self.timeouts = 0
                self.on_timeout(self.timeouts)
            time.sleep(0.01)

    def update_port_info(self):
        if "on_get_dongle_info_handler" in self.callbacks:
            bms_id = 0
            bal_id = 0
            if self.can_adapter and len(self.get_devlist()):
                dev = self.get_devlist()[0]
                if dev:
                    bms_id = dev.serial
                    if dev.subnet_device:
                        bal_id = dev.subnet_device.serial
            self.callbacks["on_get_dongle_info_handler"](self.serial_port, self.can_adapter, bms_id, bal_id)

    def get_device_info_handler(self, data):
        if "on_info_handler" in self.callbacks:
            self.callbacks["on_info_handler"](data)

    def get_device_status_handler(self, data):
        if "on_status_handler" in self.callbacks:
            self.callbacks["on_status_handler"](data)
        if "flags" in data and "on_flag_handler" in self.callbacks:
            self.callbacks["on_flag_handler"](data)

    def get_trace_handler(self, data):
        if "on_trace_handler" in self.callbacks:
            trace = ""
            if type(data["s"]) == bytes:
                trace = data["s"].decode("utf-8")
            trace = trace.replace("\r", "")
            self.__trace_log = self.callbacks["on_trace_handler"](trace, self.__trace_log)

    def on_timeout(self, timeouts):
        if "on_timeout_handler" in self.callbacks:
            self.callbacks["on_timeout_handler"](timeouts)

    def trace_ctrl(self, state:bool):
        self.msgq.put(["trace" ,{"on": state}])

    def bal_trace_ctrl(self, state:bool):
        self.msgq.put(["trace" ,{"bal": state}])

    def get_trace_log(self)->str:
        return self.__trace_log

    def __on_clear_log(self):
        self.__trace_log = ""

init_data = {"first_run": True}

def demo(screen, scene, dongle):
    init_data.update({"traces_box": dongle.get_trace_log()})
    scenes = [
        Scene([BmsToolFrame(screen, dongle.callbacks, init_data)], -1, name="Main"),
        Scene([FlagFrame(screen, dongle.callbacks)], -1, name="FlagTable"),
    ]
    # dongle.update_port_info()
    screen.play(scenes, stop_on_resize=True, start_scene=scene, allow_int=True)

class ScreenUpdating(threading.Thread):
    def __init__(self, screen) -> None:
        super().__init__(group=None, target=self.__updating, name="updating_screen", args=[], daemon=True)
        self.set_screen(screen)

    def __updating(self):
        t = threading.current_thread()
        while getattr(t, "do_run", True):
            time.sleep(0.25)
            if self.__screen:
                try:
                    self.__screen.force_update()
                except:
                    pass

    def set_screen(self, screen):
        self.__screen = screen

def restart_screen(screen, updating) -> Screen:
    screen.close(False)
    screen = Screen.open()
    updating.set_screen(screen)
    return screen

VERSION = "0.0.1"

def main():
    global init_data
    parser = argparse.ArgumentParser(prog='Bms3ToolConsole', description='Tool for visualisation data from BMS3 v' + VERSION)
    parser.add_argument('-p', '--port', type=str, help='Com port with BMS or CanAdapter', required=True)
    parser.add_argument('-a', '--adapter', help='Work with adapter, by default: FALSE', action='store_true')
    parser.set_defaults(adapter=False)
    try:
        args = parser.parse_args()
    except:
        return
    dongle = ConsoleDongle(args.port, can_adapter=args.adapter, callbacks={})
    if dongle.is_open():
        dongle.start()
    else:
        my_print.error_print("Couldn't connect")
        os.system('pause')
        return
    last_scene = None
    screen = Screen.open()
    updating = None
    while True:
        try:
            if updating == None:
                updating = ScreenUpdating(screen)
                updating.start()
            demo(screen, last_scene, dongle)
        except (ResizeScreenError, AttributeError) as e:
            init_data = {"first_run": False}
            last_scene = None
            if type(e) == AttributeError or screen.current_scene.name == "FlagTable":
                screen = restart_screen(screen, updating)
            if type(e) == ResizeScreenError:
                last_scene = e.scene
        except (ExitFromApp, KeyboardInterrupt) as e:
            if dongle:
                dongle.stop_threads()
                dongle = None
            if updating:
                updating.do_run = False
                updating.join()
                updating = None
            break


if __name__ == "__main__":
    main()
