"""Regex Tester - Visual regex testing tool with GTK4/Adwaita."""
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, Pango
import re
import json
import os
import gettext
from datetime import datetime
from regex_tester.accessibility import AccessibilityManager

_ = gettext.gettext
APP_ID = "io.github.yeager.RegexTester"
SAVED_PATTERNS_FILE = os.path.expanduser("~/.config/regex-tester/patterns.json")

CHEATSHEET = [
    (".", _("Any character")),
    ("\\d", _("Digit [0-9]")),
    ("\\D", _("Non-digit")),
    ("\\w", _("Word char [a-zA-Z0-9_]")),
    ("\\W", _("Non-word char")),
    ("\\s", _("Whitespace")),
    ("\\S", _("Non-whitespace")),
    ("^", _("Start of line")),
    ("$", _("End of line")),
    ("*", _("0 or more")),
    ("+", _("1 or more")),
    ("?", _("0 or 1")),
    ("{n}", _("Exactly n")),
    ("{n,m}", _("Between n and m")),
    ("(…)", _("Capture group")),
    ("(?:…)", _("Non-capture group")),
    ("(?P<name>…)", _("Named group")),
    ("[abc]", _("Character class")),
    ("[^abc]", _("Negated class")),
    ("a|b", _("Alternation")),
    ("\\b", _("Word boundary")),
]



def _wlc_settings_path():
    import os
    xdg = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    d = os.path.join(xdg, "regex-tester")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "welcome.json")

def _load_wlc_settings():
    import os, json
    p = _wlc_settings_path()
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"welcome_shown": False}

def _save_wlc_settings(s):
    import json
    with open(_wlc_settings_path(), "w") as f:
        json.dump(s, f, indent=2)

class RegexTesterWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs, title=_("Regex Tester"), default_width=1000, default_height=700)
        self.saved_patterns = self._load_patterns()

        # Header bar
        header = Adw.HeaderBar()
        self.theme_btn = Gtk.Button(icon_name="weather-clear-night-symbolic", tooltip_text=_("Toggle theme"))
        self.theme_btn.connect("clicked", self._toggle_theme)
        header.pack_end(self.theme_btn)

        save_btn = Gtk.Button(icon_name="document-save-symbolic", tooltip_text=_("Save pattern"))
        save_btn.connect("clicked", self._save_pattern)
        header.pack_end(save_btn)

        about_btn = Gtk.Button(icon_name="help-about-symbolic", tooltip_text=_("About"))
        about_btn.connect("clicked", self._show_about)
        header.pack_end(about_btn)

        # Split pane
        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_shrink_start_child(False)
        split.set_shrink_end_child(False)

        # Main content (left)
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_margin_start(12)
        main_box.set_margin_end(6)
        main_box.set_margin_top(8)
        main_box.set_margin_bottom(8)
        main_box.set_hexpand(True)

        # Regex entry
        main_box.append(Gtk.Label(label=_("Regular Expression:"), xalign=0, css_classes=["heading"]))
        self.regex_entry = Gtk.Entry(placeholder_text=_("Enter regex pattern..."))
        self.regex_entry.add_css_class("monospace")
        self.regex_entry.connect("changed", self._on_changed)
        main_box.append(self.regex_entry)

        # Flags
        flags_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.flag_i = Gtk.CheckButton(label=_("Case insensitive (i)"))
        self.flag_m = Gtk.CheckButton(label=_("Multiline (m)"))
        self.flag_s = Gtk.CheckButton(label=_("Dotall (s)"))
        for f in (self.flag_i, self.flag_m, self.flag_s):
            f.connect("toggled", self._on_changed)
            flags_box.append(f)
        main_box.append(flags_box)

        # Test text
        main_box.append(Gtk.Label(label=_("Test Text:"), xalign=0, css_classes=["heading"]))
        sw = Gtk.ScrolledWindow(vexpand=True, min_content_height=150)
        self.text_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True)
        self.text_view.get_buffer().connect("changed", self._on_changed)
        sw.set_child(self.text_view)
        main_box.append(sw)

        # Matches
        main_box.append(Gtk.Label(label=_("Matches:"), xalign=0, css_classes=["heading"]))
        sw2 = Gtk.ScrolledWindow(vexpand=True, min_content_height=150)
        self.match_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, monospace=True, editable=False, cursor_visible=False)
        sw2.set_child(self.match_view)
        main_box.append(sw2)

        # Saved patterns combo
        saved_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        saved_box.append(Gtk.Label(label=_("Saved:")))
        self.saved_combo = Gtk.DropDown()
        self._update_saved_combo()
        self.saved_combo.connect("notify::selected", self._load_saved)
        self.saved_combo.set_hexpand(True)
        saved_box.append(self.saved_combo)
        del_btn = Gtk.Button(icon_name="edit-delete-symbolic", tooltip_text=_("Delete saved"))
        del_btn.connect("clicked", self._delete_saved)
        saved_box.append(del_btn)
        main_box.append(saved_box)

        split.set_start_child(main_box)

        # Sidebar - cheatsheet
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_margin_start(6)
        sidebar.set_margin_end(12)
        sidebar.set_margin_top(8)
        sidebar.set_margin_bottom(8)
        sidebar.set_size_request(250, -1)
        sidebar.append(Gtk.Label(label=_("Regex Cheatsheet"), xalign=0, css_classes=["title-3"]))

        sw3 = Gtk.ScrolledWindow(vexpand=True)
        cheat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for pattern, desc in CHEATSHEET:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            plbl = Gtk.Label(label=pattern, xalign=0, css_classes=["monospace"], width_chars=14)
            dlbl = Gtk.Label(label=desc, xalign=0, hexpand=True, wrap=True)
            row.append(plbl)
            row.append(dlbl)
            cheat_box.append(row)
        sw3.set_child(cheat_box)
        sidebar.append(sw3)

        split.set_end_child(sidebar)
        split.set_position(650)

        # Status bar
        self.statusbar = Gtk.Label(label="", xalign=0, css_classes=["dim-label"], margin_start=12, margin_bottom=4)

        # Layout
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(header)
        content.append(split)
        content.append(self.statusbar)
        self.set_content(content)

        # Create highlight tag
        buf = self.text_view.get_buffer()
        buf.create_tag("highlight", background="yellow", foreground="black")

        self._update_status()
        GLib.timeout_add_seconds(1, self._update_status)

    def _get_flags(self):
        flags = 0
        if self.flag_i.get_active(): flags |= re.IGNORECASE
        if self.flag_m.get_active(): flags |= re.MULTILINE
        if self.flag_s.get_active(): flags |= re.DOTALL
        return flags

    def _on_changed(self, *_args):
        buf = self.text_view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
        pattern = self.regex_entry.get_text()

        # Remove old highlights
        buf.remove_tag_by_name("highlight", buf.get_start_iter(), buf.get_end_iter())

        mbuf = self.match_view.get_buffer()

        if not pattern:
            mbuf.set_text("")
            return

        try:
            regex = re.compile(pattern, self._get_flags())
            self.regex_entry.remove_css_class("error")
        except re.error as e:
            mbuf.set_text(f"Error: {e}")
            self.regex_entry.add_css_class("error")
            return

        matches = list(regex.finditer(text))
        if not matches:
            mbuf.set_text(_("No matches"))
            return

        result_lines = []
        for i, m in enumerate(matches):
            # Highlight in text
            start_iter = buf.get_iter_at_offset(m.start())
            end_iter = buf.get_iter_at_offset(m.end())
            buf.apply_tag_by_name("highlight", start_iter, end_iter)

            result_lines.append(f"Match {i+1}: \"{m.group()}\" [{m.start()}-{m.end()}]")
            if m.groups():
                for gi, g in enumerate(m.groups(), 1):
                    result_lines.append(f"  Group {gi}: \"{g}\"")
            if m.groupdict():
                for name, val in m.groupdict().items():
                    result_lines.append(f"  {name}: \"{val}\"")

        mbuf.set_text("\n".join(result_lines))

    def _update_status(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.statusbar.set_label(f"  {now}")
        return True

    def _toggle_theme(self, _btn):
        mgr = Adw.StyleManager.get_default()
        if mgr.get_dark():
            mgr.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            mgr.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def _load_patterns(self):
        try:
            with open(SAVED_PATTERNS_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_patterns_to_disk(self):
        os.makedirs(os.path.dirname(SAVED_PATTERNS_FILE), exist_ok=True)
        with open(SAVED_PATTERNS_FILE, 'w') as f:
            json.dump(self.saved_patterns, f, indent=2)

    def _save_pattern(self, _btn):
        pattern = self.regex_entry.get_text()
        if pattern and pattern not in self.saved_patterns:
            self.saved_patterns.append(pattern)
            self._save_patterns_to_disk()
            self._update_saved_combo()

    def _update_saved_combo(self):
        items = self.saved_patterns if self.saved_patterns else [_("(none)")]
        self.saved_combo.set_model(Gtk.StringList.new(items))

    def _load_saved(self, combo, _pspec):
        idx = combo.get_selected()
        if idx < len(self.saved_patterns):
            self.regex_entry.set_text(self.saved_patterns[idx])

    def _delete_saved(self, _btn):
        idx = self.saved_combo.get_selected()
        if idx < len(self.saved_patterns):
            self.saved_patterns.pop(idx)
            self._save_patterns_to_disk()
            self._update_saved_combo()

    def _show_about(self, _btn):
        about = Adw.AboutWindow(
            transient_for=self,
            application_name="Regex Tester",
            application_icon="accessories-text-editor",
            version="0.1.0",
            developer_name="Daniel Nylander",
            developers=["Daniel Nylander"],
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/yeager/regex-tester",
            issue_url="https://github.com/yeager/regex-tester/issues",
            translator_credits=_("translator-credits"),
            comments=_("Visual regex testing tool"),
        )
        about.add_link(_("Translations"), "https://www.transifex.com/danielnylander/regex-tester")
        about.present(self)


class RegexTesterApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = self.props.active_window or RegexTesterWindow(application=self)
        win.present()
        self._wlc_settings = _load_wlc_settings()
        if not self._wlc_settings.get("welcome_shown"):
            self._show_welcome(self.props.active_window or self)


    def do_startup(self):
        Adw.Application.do_startup(self)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])


def main():
    app = RegexTesterApp()
    app.run()


if __name__ == "__main__":
    main()

    def _show_welcome(self, win):
        dialog = Adw.Dialog()
        dialog.set_title(_("Welcome"))
        dialog.set_content_width(420)
        dialog.set_content_height(480)
        page = Adw.StatusPage()
        page.set_icon_name("edit-find-symbolic")
        page.set_title(_("Welcome to Regex Tester"))
        page.set_description(_(
            "Test and debug regular expressions.\n\n✓ Real-time regex matching\n✓ Match highlighting\n✓ Group capture display"
        ))
        btn = Gtk.Button(label=_("Get Started"))
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(12)
        btn.connect("clicked", self._on_welcome_close, dialog)
        page.set_child(btn)
        box = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        hb.set_show_title(False)
        box.add_top_bar(hb)
        box.set_content(page)
        dialog.set_child(box)
        dialog.present(win)

    def _on_welcome_close(self, btn, dialog):
        self._wlc_settings["welcome_shown"] = True
        _save_wlc_settings(self._wlc_settings)
        dialog.close()



# --- Session restore ---
import json as _json
import os as _os

def _save_session(window, app_name):
    config_dir = _os.path.join(_os.path.expanduser('~'), '.config', app_name)
    _os.makedirs(config_dir, exist_ok=True)
    state = {'width': window.get_width(), 'height': window.get_height(),
             'maximized': window.is_maximized()}
    try:
        with open(_os.path.join(config_dir, 'session.json'), 'w') as f:
            _json.dump(state, f)
    except OSError:
        pass

def _restore_session(window, app_name):
    path = _os.path.join(_os.path.expanduser('~'), '.config', app_name, 'session.json')
    try:
        with open(path) as f:
            state = _json.load(f)
        window.set_default_size(state.get('width', 800), state.get('height', 600))
        if state.get('maximized'):
            window.maximize()
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        pass


# --- Fullscreen toggle (F11) ---
def _setup_fullscreen(window, app):
    """Add F11 fullscreen toggle."""
    from gi.repository import Gio
    if not app.lookup_action('toggle-fullscreen'):
        action = Gio.SimpleAction.new('toggle-fullscreen', None)
        action.connect('activate', lambda a, p: (
            window.unfullscreen() if window.is_fullscreen() else window.fullscreen()
        ))
        app.add_action(action)
        app.set_accels_for_action('app.toggle-fullscreen', ['F11'])


# --- Plugin system ---
import importlib.util
import os as _pos

def _load_plugins(app_name):
    """Load plugins from ~/.config/<app>/plugins/."""
    plugin_dir = _pos.path.join(_pos.path.expanduser('~'), '.config', app_name, 'plugins')
    plugins = []
    if not _pos.path.isdir(plugin_dir):
        return plugins
    for fname in sorted(_pos.listdir(plugin_dir)):
        if fname.endswith('.py') and not fname.startswith('_'):
            path = _pos.path.join(plugin_dir, fname)
            try:
                spec = importlib.util.spec_from_file_location(fname[:-3], path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                plugins.append(mod)
            except Exception as e:
                print(f"Plugin {fname}: {e}")
    return plugins
