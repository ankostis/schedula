#!/usr/bin/env/python
#-*- coding: utf-8 -*-
#
# Copyright 2013-2015 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
"""
The launching GUI formCO2MPAS.

Layout::

    #####################################################
    #:  ______________________________                  :#
    #: |                              |                 :#
    #: |                              | [  Add files  ] :#
    #: |                              |                 :#
    #: |                              | [  Add folder ] :#
    #: |___________(inputs)___________|                 :#
    #:  ______________________________                  :#
    #: |_________(Output dir)_________| [ Set Out Dir ] :#
    #:  ______________________________                  :#
    #: |________(Template file________| [Set Template ] :#
    #:                                                  :#
    #: [flag-1] [flag-2] [flag-3] [flag-4]              :#
    #:  ______________________________________________  :#
    #: |_________________(extra flags)________________| :#
    #: [ Help ]     [ Run-1 ]  ...             [ Run-2] :#
    #+--------------------------------------------------+#
    #:  ______________________________________________  :#
    #: |                                              | :#
    #: |                                              | :#
    #: |________________(log_frame)___________________| :#
    #####################################################

"""
## TODO: 5-Nov-2016
#  - Fix co2mpas's main() init-sequence with new GUI instead of *easyguis*.
#  - Make labels as hyperlinks or use ballons.
#  - Cannot enable DEBUG log level.
#
## Help (apart from PY-site):
#  - http://effbot.org/tkinterbook/tkinter-index.htm
#  - http://www.tkdocs.com/
#  - http://infohost.nmt.edu/tcc/help/pubs/tkinter/web/index.html

## Icons from:
#    - http://www.iconsdb.com/red-icons/red-play-icons.html
#    - https://material.io/icons/#

from collections import Counter, OrderedDict
import datetime
import io
import logging
import os
from pandalone import utils as putils
import re
import sys
from textwrap import dedent, indent
from threading import Thread
from tkinter import StringVar, ttk, filedialog, font as tkfont
import traceback
import webbrowser

from PIL import Image, ImageTk
from toolz import dicttoolz as dtz

from co2mpas import (__version__, __updated__, __copyright__, __license__, __uri__)
from co2mpas.__main__ import init_logging, _main as co2mpas_main, __doc__ as main_help_doc
import co2mpas.batch as co2mpas_batch
from co2mpas.utils import stds_redirected
import functools as fnt
import os.path as osp
import pkg_resources as pkg
import tkinter as tk


log = logging.getLogger('tkui')

_bw = 2
_pad = 2
_sunken = dict(relief=tk.SUNKEN, padx=_pad, pady=_pad, borderwidth=_bw)
app_name = 'co2mpas'

try:
    _levelsMap = logging._levelToName
except AttributeError:
    _levelsMap = {k: v for k, v
                  in logging._levelNames.items()  # @UndefinedVariable PY2-only
                  if isinstance(k, int)}


def set_ttk_styles():
    style = ttk.Style()
    style.configure('None.TButton', background='SystemButtonFace')
    style.configure('True.TButton', foreground='green')
    style.configure('False.TButton', foreground='red')
    style.configure('Sunk.TFrame', relief=tk.SUNKEN, padding=_pad)
    style.configure('Sunken.TLabelFrame', relief=tk.SUNKEN, padding=_pad)
    style.configure('TA.TButton', foreground='orange')
    style.configure('Prog.TLabel', foreground='blue')


def bang(cond):
    """ Returns a "!" if cond is true - used for ttk-states."""
    return cond and '!' or ''


def labelize_str(s):
    if not s.endswith(':'):
        s += ':'
    return s.title()


def open_file_with_os(fpath):
    if fpath.strip():
        log.info("Opening file %r...", fpath)
        try:
            putils.open_file_with_os(fpath.strip())
        except Exception as ex:
            log.error("Failed opening %r due to: %s", fpath, ex)


def find_longest_valid_dir(path, default=None):
    while path and not osp.isdir(path):
        path = osp.dirname(path)

    if not path:
        path = default

    return path


def get_file_infos(fpath):
    s = os.stat(fpath)
    mtime = datetime.datetime.fromtimestamp(s.st_mtime)  # @UndefinedVariable
    return (s.st_size, mtime.isoformat())


def run_python_job(function, cmd_args, job_name, stdout=None, stderr=None, on_finish=None):
    """
    Redirects stdout/stderr to logging, and notifies when finished.

    Suitable to be run within a thread.
    """
    with stds_redirected(stdout, stderr) as (stdout, stderr):
        try:
            function(*cmd_args)
        except SystemExit as ex:
            log.error("Job %s exited due to: %r", job_name, ex)
        except Exception as ex:
            log.error("Job %s failed due to: %s", job_name, ex, exc_info=1)

    if on_finish:
        try:
            on_finish(stdout, stderr)
        except Exception as ex:
            log.error("While ending job: %s", ex, exc_info=1)
    else:
        stdout = stdout.getvalue()
        if stdout:
            log.info("Job %s stdout: %s", job_name, stdout)

        stderr = stderr.getvalue()
        if stderr:
            log.error("Job %s stderr: %s", job_name, stderr)


def read_image(fpath):
    with pkg.resource_stream('co2mpas', fpath) as fd:  # @UndefinedVariable
        img = Image.open(fd)
        photo = ImageTk.PhotoImage(img)
    return photo


def add_icon(btn, icon_path):
    image = read_image(icon_path)
    btn['image'] = image
    btn.image = image  # Avoid GC.
    if btn['text']:
        btn['compound'] = tk.TOP


def tree_apply_columns(tree, columns):
    tree['columns'] = tuple(c for c, _ in columns if not c.startswith('#'))
    for c, col_kwds in columns:

        h_col_kwds = dtz.keyfilter((lambda k: k in set('text image anchor command'.split())), col_kwds)
        text = h_col_kwds.pop('text', c.title())
        tree.heading(c, text=text, **h_col_kwds)

        c_col_kwds = dtz.keyfilter((lambda k: k in set('anchor minwidth stretch width'.split())), col_kwds)
        tree.column(c, **c_col_kwds)


class HyperlinkManager:
    ## From http://effbot.org/zone/tkinter-text-hyperlink.htm
    def __init__(self, text):

        self.text = text

        self.text.tag_config("hyper", foreground="blue", underline=1)

        self.text.tag_bind("hyper", "<Enter>", self._enter)
        self.text.tag_bind("hyper", "<Leave>", self._leave)
        self.text.tag_bind("hyper", "<Button-1>", self._click)

        self.reset()

    def reset(self):
        self.links = {}

    def add(self, action):
        # add an action to the manager.  returns tags to use in
        # associated text widget
        tag = "hyper-%d" % len(self.links)
        self.links[tag] = action
        return "hyper", tag

    def _enter(self, event):
        self.text.config(cursor="hand2")

    def _leave(self, event):
        self.text.config(cursor="")

    def _click(self, event):
        for tag in self.text.tag_names(tk.CURRENT):
            if tag[:6] == "hyper-":
                self.links[tag]()
                return


class LinkLabel(ttk.Label):
    def __init__(self, *args, url=None, **kwds):
        super().__init__(*args, style='Link.TLabel', **kwds)
        self.url = url


class FlagButton(ttk.Button):
    """A button switching flag-states when clicked; 3-state by default: ``'', 'true', 'false'``.

    :ivar flag_styles:
        An ordered-dict ``{state --> ttk-style}``.
    :ivar flag_var:
        A :class:`t.Variable` holding the flag, which is a key in the `flag_syles`.
        Also provided on constructor as ``'variable'`` kwd.
    :ivar flag_name:
        The flag-name, extracted from the ``'text'`` option on construction; you may
        modify it attr later.

    """

    flag_styles = OrderedDict([
        ('', 'None.TButton'),
        ('true', 'True.TButton'),
        ('false', 'False.TButton'),
    ])

    def __init__(self, *args, variable=None, command=None, **kwds):
        def clicked():
            self.next_flag()
            if self._orig_command:
                self._orig_command()

        kwds['command'] = clicked
        super().__init__(*args, **kwds)
        self._orig_command = command
        self.flag_var = variable or tk.Variable()
        self.flag_name = kwds.get('text', '')

        ## Begin from 1st flag.
        #
        self._flag_ix = len(self.flag_styles) - 1
        self.next_flag()

    @property
    def flag(self):
        return self.flag_var.get()

    def _format_text(self, flag):
        """Override to modify the button text's among flags."""
        #return '%s: %s' % (self.flag_name, flag)
        return self.flag_name

    def next_flag(self):
        self._flag_ix = (self._flag_ix + 1) % len(self.flag_styles)
        flag = list(self.flag_styles)[self._flag_ix]
        flag_style = self.flag_styles[flag]

        self.flag_var.set(flag)
        self.configure(text=self._format_text(flag), style=flag_style)
        self.state((bang(not flag) + 'pressed', ))


class LogPanel(ttk.LabelFrame):

    """
    Instantiate only once(!), or logging and Tk's ex-handling will get borged.
    """

    LEVELS_MAP = sorted(_levelsMap.items(), reverse=True)

    TAG_META = 'meta'
    TAG_LOGS = 'logs'

    FORMATTER_SPECS = [
        dict(
            fmt='%(asctime)s:%(name)s:%(levelname)s:%(message)s', datefmt=None),
        dict(fmt='%(asctime)s:%(name)s:%(levelname)s:', datefmt=None)
    ]

    initted = False

    def __init__(self, *args,
                 log_threshold=logging.INFO, logger_name='', formatter_specs=None, **kw):
        """
        :param dict formatter_specs:
            A 2-element array of Formatter-args (note that python-2 has no `style` kw),
            where the 2nd should print only the Metadata.
            If missing, defaults to :attr:`LogPanel.FORMATTER_SPECS`
        :param logger_name:
            What logger to intercept to.
            If missing, defaults to root('') and DOES NOT change its threshold.
        """
        if LogPanel.initted:
            raise RuntimeError("I said instantiate me only ONCE!!!")
        LogPanel.inited = True

        super().__init__(*args, **kw)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._log_text = _log_text = tk.Text(self,
                                             state=tk.DISABLED, wrap=tk.NONE,
                                             font="Courier 8",
                                             **_sunken
                                             )
        _log_text.grid(row=0, column=0, sticky='nswe')

        # Setup scrollbars.
        #
        v_scrollbar = ttk.Scrollbar(self)
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        self._log_text.config(yscrollcommand=v_scrollbar.set)
        v_scrollbar.config(command=self._log_text.yview)
        self._log_text.config(xscrollcommand=h_scrollbar.set)
        h_scrollbar.config(command=self._log_text.xview)

        # Prepare Log-Tags
        #
        tags = [
            [LogPanel.TAG_LOGS, dict(lmargin2='+2c')],
            [LogPanel.TAG_META, dict(font="Courier 7")],

            [logging.CRITICAL, dict(background="red", foreground="yellow")],
            [logging.ERROR, dict(foreground="red")],
            [logging.WARNING, dict(foreground="magenta")],
            [logging.INFO, dict(foreground="blue")],
            [logging.DEBUG, dict(foreground="grey")],
            [logging.NOTSET, dict()],

        ]
        for tag, kws in tags:
            if isinstance(tag, int):
                tag = logging.getLevelName(tag)
            _log_text.tag_config(tag, **kws)
        _log_text.tag_raise(tk.SEL)

        self._log_counters = Counter()
        self._update_title()

        self._setup_logging_components(formatter_specs, log_threshold)

        self._setup_popup(self._log_text)

        self._intercept_logging(logger_name)
        self._intercept_tinker_exceptions()
        self.bind('<Destroy>', self._stop_intercepting_exceptions)

    def _setup_logging_components(self, formatter_specs, log_threshold):
        class MyHandler(logging.Handler):

            def __init__(self2, **kws):  # @NoSelf
                logging.Handler.__init__(self2, **kws)

            def emit(self2, record):  # @NoSelf
                try:
                    self.after_idle(lambda: self._write_log_record(record))
                except Exception:
                    self2.handleError(record)

        self._handler = MyHandler()

        if not formatter_specs:
            formatter_specs = LogPanel.FORMATTER_SPECS
        self.formatter = logging.Formatter(**formatter_specs[0])
        self.metadata_formatter = logging.Formatter(**formatter_specs[1])

        self.threshold_var = tk.IntVar()
        self.log_threshold = log_threshold

    def _intercept_logging(self, logger_name):
        logger = logging.getLogger(logger_name)
        logger.addHandler(self._handler)

    def _intercept_tinker_exceptions(self):
        def my_ex_interceptor(*args):
            # Must not raise any errors, or infinite recursion here.
            log.critical('Unhandled TkUI exception:', exc_info=True)
            self._original_tk_ex_handler(*args)

        self._original_tk_ex_handler = tk.Tk.report_callback_exception
        tk.Tk.report_callback_exception = my_ex_interceptor

    def _stop_intercepting_exceptions(self, event):
        root_logger = logging.getLogger()
        root_logger.removeHandler(self._handler)

    def _setup_popup(self, target):
        levels_map = LogPanel.LEVELS_MAP

        # Threshold sub-menu
        #
        def change_threshold():
            self.log_threshold = self.threshold_var.get()

        threshold_menu = tk.Menu(target, tearoff=0)
        for lno, lname in levels_map:
            threshold_menu.add_radiobutton(
                label=lname, value=lno,
                variable=self.threshold_var,
                command=change_threshold
            )
        filters_menu = tk.Menu(target, tearoff=0)

        # Filters sub-menu
        #
        self._filter_vars = [
            tk.BooleanVar(name=lname) for _, lname in levels_map]
        for i, (lno, lname) in enumerate(levels_map):
            filters_menu.add_checkbutton(
                label=lname,
                variable=self._filter_vars[i],
                command=self._apply_filters
            )

        # Popup menu
        #
        popup = tk.Menu(target, tearoff=0)
        popup.add_cascade(label="Log threshold", menu=threshold_menu)
        popup.add_cascade(label="Filter levels", menu=filters_menu)
        popup.add_checkbutton(
            label="Wrap lines", command=self.toggle_text_wrapped)
        popup.add_separator()
        popup.add_command(label="Save as...", command=self.save_log)
        popup.add_separator()
        popup.add_command(label="Clear logs", command=self.clear_log)

        def do_popup(event):
            popup.post(event.x_root, event.y_root)
        target.bind("<Button-3>", do_popup)

    def _apply_filters(self):
        for level_var in self._filter_vars:
            self._log_text.tag_configure(
                level_var._name, elide=level_var.get())

    @property
    def log_threshold(self):
        return self._handler.level

    @log_threshold.setter
    def log_threshold(self, level):
        self._handler.setLevel(level)
        self.threshold_var.set(level)

    def toggle_text_wrapped(self):
        self._log_text['wrap'] = tk.WORD if self._log_text[
            'wrap'] == tk.NONE else tk.NONE

    def _update_title(self):
        levels = ['Totals'] + [lname for _, lname in LogPanel.LEVELS_MAP]
        levels_counted = [(lname, self._log_counters[lname])
                          for lname in levels]
        self['text'] = 'Log (%s)' % ', '.join(
            '%s: %i' % (lname, count) for lname, count in levels_counted if count)

    def clear_log(self):
        self._log_text['state'] = tk.NORMAL
        self._log_text.delete('1.0', tk.END)
        self._log_text['state'] = tk.DISABLED
        self._log_counters.clear()
        self._update_title()

    def save_log(self):
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = 'co2dice-%s.log' % now
        fname = filedialog.SaveAs(
            parent=self,
            title='Select filename to save the Log',
            initialfile=fname,
            defaultextension='.log',
            filetypes=[('log', '*.log'), ('txt', '*.txt'), ('*', '*')],
        ).show()
        if fname:
            txt = self._log_text.get(1.0, tk.END)
            with io.open(fname, 'wt+') as fd:
                fd.write(txt)

    def _write_log_record(self, record):
        try:
            log_text = self._log_text
            # Test FAILS on Python-2! Its ok.
            was_bottom = (log_text.yview()[1] == 1)

            txt = self.formatter.format(record)
            if txt[-1] != '\n':
                txt += '\n'
            txt_len = len(txt) + 1  # +1 ??
            log_start = '%s-%ic' % (tk.END, txt_len)
            metadata_len = len(self.metadata_formatter.formatMessage(record))
            meta_end = '%s-%ic' % (tk.END, txt_len - metadata_len)

            log_text['state'] = tk.NORMAL
            self._log_text.mark_set('LE', tk.END)
            # , LogPanel.TAG_LOGS)
            log_text.insert(tk.END, txt, LogPanel.TAG_LOGS)
            log_text.tag_add(record.levelname, log_start, tk.END)
            log_text.tag_add(LogPanel.TAG_META, log_start, meta_end)
            log_text['state'] = tk.DISABLED

            # Scrolling to the bottom if
            #    log serious or log already at the bottom.
            #
            if record.levelno >= logging.ERROR or was_bottom:
                log_text.see(tk.END)

            self._log_counters.update(['Total', record.levelname])
            self._update_title()
        except Exception:
            # Must not raise any errors, or infinite recursion here.
            print("!!!!!!     Unexpected exception while logging exceptions(!): %s" %
                  traceback.format_exc())


class _MainPanel(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, style='Sunk.TFrame', *args, **kwargs)

        self._stop_job = False  # semaphore for the red button.
        self._job_thread = None

        frame = self._make_files_frame(self)
        frame.pack(fill=tk.BOTH, expand=1)

        frame = self._make_flags_frame(self)
        frame.pack(fill=tk.X)

        frame = self._make_buttons_frame(self)
        frame.pack(fill=tk.X)

        self.mediate_panel()

    def _make_files_frame(self, parent):
        frame = ttk.Frame(parent)

        kwds = {}

        (inp_label, tree, add_files_btn, add_folder_btn, del_btn) = self._build_inputs_tree(frame)
        inp_label.grid(column=0, row=0, sticky='nswe')
        tree.grid(column=0, row=1, rowspan=3, sticky='nswe', **kwds)
        add_files_btn.grid(column=1, row=1, sticky='nswe', **kwds)
        add_folder_btn.grid(column=1, row=2, sticky='nswe', **kwds)
        del_btn.grid(column=1, row=3, sticky='nswe', **kwds)
        self.inputs_tree = tree

        (out_label, out_entry, out_btn, out_var) = self._build_output_folder(frame)
        out_label.grid(column=0, row=4, sticky='nswe')
        out_entry.grid(column=0, row=5, sticky='nswe', **kwds)
        out_btn.grid(column=1, row=5, sticky='nswe', **kwds)
        self.out_folder_var = out_var

        (tmpl_label, tmpl_entry, tmpl_btn, tmpl_var) = self._build_template_file(frame)
        tmpl_label.grid(column=0, row=8, sticky='nswe')
        tmpl_entry.grid(column=0, row=9, sticky='nswe', **kwds)
        tmpl_btn.grid(column=1, row=9, sticky='nswe', **kwds)
        self.tmpl_folder_var = tmpl_var

        frame.rowconfigure(1, weight=3)
        frame.rowconfigure(2, weight=3)
        frame.rowconfigure(3, weight=1)
        frame.columnconfigure(0, weight=1)

        return frame

    def _build_inputs_tree(self, parent):
        inp_label = ttk.Label(parent, text='Inputs:')
        tree = ttk.Treeview(parent)
        columns = (
            ('#0', {
                'text': 'Filepath',
                'anchor': tk.W,
                'stretch': True,
                'minwidth': 96,
                'width': 362}),
            ('type', {'anchor': tk.W, 'width': 56, 'stretch': False}),
            ('size', {'anchor': tk.E, 'width': 64, 'stretch': False}),
            ('modified', {'anchor': tk.W, 'width': 164, 'stretch': False}),
        )
        tree_apply_columns(tree, columns)
        tree.excel_icon = read_image('icons/excel-olive-16.png')
        tree.file_icon = read_image('icons/file-olive-16.png')
        tree.folder_icon = read_image('icons/folder-olive-16.png')

        def ask_input_files():
            files = filedialog.askopenfilenames(
                title='Select CO2MPAS Input file(s)',
                multiple=True,
                filetypes=(('Excel files', '.xlsx .xlsm'),
                           ('All files', '*'),
                           ))
            for fpath in files:
                try:
                    icon = tree.excel_icon if re.search(r'\.xl\w\w$', fpath) else tree.file_icon
                    finfos = get_file_infos(fpath)
                    tree.insert('', 'end', fpath, text=fpath,
                                values=('FILE', *finfos), image=icon)
                except Exception as ex:
                    log.warning("Cannot add input file %r due to: %s", fpath, ex)
        files_btn = btn = ttk.Button(parent, text="Add File(s)...", command=ask_input_files)
        add_icon(btn, 'icons/add_file-olive-48.png')

        def ask_input_folder():
            folder = filedialog.askdirectory(
                title='Select CO2MPAS Input folder')
            if folder:
                try:
                    finfos = get_file_infos(folder)
                    tree.insert('', 'end', folder, text=folder + '/',
                                values=('FOLDER', *finfos), image=tree.folder_icon)
                except Exception as ex:
                    log.warning("Cannot add input folder %r due to: %s", folder, ex)
        folder_btn = btn = ttk.Button(parent, text="Add Folder...", command=ask_input_folder)
        add_icon(btn, 'icons/add_folder-olive-48.png')

        del_btn = btn = ttk.Button(parent, state=tk.DISABLED)
        add_icon(btn, 'icons/x_circle-olive-32.png')

        ## Tree events:
        ##s
        def del_input_file(ev=None):
            if not ev or ev.keysym == 'Delete':
                for item_id in tree.selection():
                    tree.delete(item_id)
                del_btn.state((tk.DISABLED, ))  # tk-BUG: Selection-vent is not fired.

        def tree_selection_changed(ev):
            del_btn.state((bang(tree.selection()) + tk.DISABLED, ))

        def on_double_click(ev):
            item = tree.identify('item', ev.x, ev.y)
            open_file_with_os(item)

        tree.bind("<Key>", del_input_file)
        del_btn['command'] = del_input_file
        tree.bind('<<TreeviewSelect>>', tree_selection_changed)
        tree.bind("<Double-1>", on_double_click)

        return (inp_label, tree, files_btn, folder_btn, del_btn)

    def _build_output_folder(self, frame):
        title = 'Output Folder'
        label = ttk.Label(frame, text=labelize_str(title))

        var = StringVar()
        entry = ttk.Entry(frame, textvariable=var)

        def ask_output_folder():
            initialdir = find_longest_valid_dir(var.get().strip())
            folder = filedialog.askdirectory(title="Select %s" % title, initialdir=initialdir)
            if folder:
                var.set(folder + '/')

        btn = ttk.Button(frame, command=ask_output_folder)
        add_icon(btn, 'icons/add_folder-olive-32.png')

        entry.bind("<Double-1>", lambda ev: open_file_with_os(var.get()))

        return label, entry, btn, var

    def _build_template_file(self, parent):
        title = 'Output Template file'
        label = ttk.Label(parent, text=labelize_str(title))

        var = StringVar()
        entry = ttk.Entry(parent, textvariable=var)

        def ask_template_file():
            initialdir = find_longest_valid_dir(var.get().strip())
            file = filedialog.askopenfilename(
                title='Select %s' % title,
                initialdir=initialdir,
                filetypes=(('Excel files', '.xlsx .xlsm'),
                           ('All files', '*'),
                           ))
            if file:
                var.set(file)

        btn = ttk.Button(parent, command=ask_template_file)
        add_icon(btn, 'icons/add_file-olive-32.png')
        entry.bind("<Double-1>", lambda ev: open_file_with_os(var.get()))

        return label, entry, btn, var

    def _make_flags_frame(self, parent):
        frame = ttk.Frame(parent)
        flags_frame = ttk.Frame(frame)
        flags_frame.pack(fill=tk.X)

        def make_flag(flag):
            flag_name = flag.replace('_', ' ').title()
            btn = FlagButton(flags_frame, text=flag_name,
                             command=self.mediate_panel,
                             padding=(_pad, 4 * _pad, _pad, 4 * _pad))
            btn.pack(side=tk.LEFT, ipadx=4 * _pad)

            return flag, btn.flag_var

        flags = (
            'engineering_mode',
            'run_plan',
            'soft_validation',
            'only_summary',
            'plot_workflow',
        )
        self.flag_vars = [make_flag(f) for f in flags]

        label = ttk.Label(frame, text=labelize_str("Extra Options and Flags"))
        label.pack(anchor=tk.W)

        self.extra_opts_var = StringVar()
        entry = ttk.Entry(frame, textvariable=self.extra_opts_var)
        entry.pack(fill=tk.X, expand=1, ipady=2 * _pad)

        return frame

    def _make_buttons_frame(self, parent):
        frame = ttk.Frame(parent)
        run_btns = []
        btn = ttk.Button(frame, text="Help",
                        command=fnt.partial(log.info, '%s', main_help_doc))
        add_icon(btn, 'icons/help-olive-32.png ')
        btn.grid(column=0, row=4, sticky='nswe')
        run_btns.append(btn)

        btn = ttk.Button(frame, text="Run",
                        command=fnt.partial(self._do_run_job, is_ta=False))
        add_icon(btn, 'icons/play-olive-32.png')
        btn.grid(column=1, row=4, sticky='nswe')
        run_btns.append(btn)

        self._run_ta_btn = btn = ttk.Button(frame,
                                            text="Run TA", style='TA.TButton',
                                            command=fnt.partial(self._do_run_job, is_ta=True))
        add_icon(btn, 'icons/play_doc-orange-32.png ')
        btn.grid(column=2, row=4, sticky='nswe')
        run_btns.append(btn)

        self._run_btns = run_btns

        def stop_job_clicked():
            self._stop_job = True
            self.mediate_panel()
        self._stop_job_btn = btn = ttk.Button(frame, text="Stop", command=stop_job_clicked)
        add_icon(btn, 'icons/hand-red-32.png')
        btn.grid(column=3, row=4, sticky='nswe')

        self.progr_var = tk.IntVar()
        self.progr_bar = ttk.Progressbar(frame, orient=tk.HORIZONTAL,
                                         mode='determinate', variable=self.progr_var)
        self.progr_bar.grid(column=0, row=6, columnspan=4, sticky='nswe')
        self.status_label = ttk.Label(self.progr_bar, style='Prog.TLabel')

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=2)
        frame.columnconfigure(2, weight=1)

        return frame

    def mediate_panel_T(self, msg=None, progr_step=None, progr_max=None):
        """To be nvoked by other threads."""
        self.after_idle(self.mediate_panel, msg, progr_step, progr_max)

    def mediate_panel(self, msg=None, progr_step=None, progr_max=None):
        """Handler of states for all panel's widgets."""
        progr_var = self.progr_var

        ## Update progress-bar.
        #
        if progr_max is not None:
            self.progr_bar['maximum'] = progr_max
            progr_var.set(0)
        if progr_step:
            progr_var.set(progr_var.get() + progr_step)
        if msg is not None:
            self._set_status(msg)

        job_alive = bool(self._job_thread)

        ## Update Stop-button.
        #
        self._stop_job_btn.state((bang(job_alive) + tk.DISABLED, ))
        stop_requested = job_alive and self._stop_job
        self._stop_job_btn.state((bang(not stop_requested) + 'pressed', ))

        ## Update Run-buttons.
        #
        any_flags = any(var.get() for _, var in self.flag_vars)
        run_btns_state = bang(not job_alive) + tk.DISABLED
        for btn in self._run_btns:
            btn.state((run_btns_state, ))
        self._run_ta_btn.state((bang(not job_alive and not any_flags) + tk.DISABLED, ))

    def _set_status(self, msg):
        """Overlays a message on the progressbar."""
        status_label = self.status_label
        if msg:
            status_label['text'] = msg
            self.status_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        else:
            status_label.place_forget()
            status_label['text'] = ''

    def reconstruct_cmd_args_from_gui(self, is_ta):
        cmd_args = ['ta' if is_ta else 'batch']

        cmd_args += self.extra_opts_var.get().strip().split()

        out_folder = self.out_folder_var.get()
        if out_folder:
            cmd_args += ['-O', out_folder]

        tmpl_folder = self.tmpl_folder_var.get()
        if tmpl_folder:
            cmd_args += ['-D', 'flag.output_template=%s' % tmpl_folder]

        for flag, flag_var in self.flag_vars:
            flag_value = flag_var.get()
            if flag_value:
                cmd_args += ['-D', 'flag.%s=%s' % (flag, flag_value)]

        inputs = self.inputs_tree.get_children()
        if not inputs:
            cwd = os.getcwd()
            log.warning("No inputs specified; assuming current directory: %s", cwd)
            cmd_args.append(cwd)
        else:
            cmd_args += inputs

        return cmd_args

    def _do_run_job(self, is_ta):
        job_name = "CO2MPAS-TA" if is_ta else "CO2MPAS"
        assert self._job_thread is None, self._job_thread
        self._stop_job = False

        cmd_args = self.reconstruct_cmd_args_from_gui(is_ta)
        log.info('Launching %s job:\n  %s', job_name, cmd_args)

        maingui = self
        mediate_panel = self.mediate_panel_T

        class ProgressUpdater:
            """
            A *tqdm* replacement that cooperates with :func:`run_python_job` to pump stdout/stderr when iterated.

            :ivar i:
                Enumarates progress calls.
            :ivar out_i:
                Tracks till where we have read and logged from the stdout StringIO stream.
            :ivar err_i:
                Tracks till where we have read and logged from the stderr StringIO stream.
            """
            def __init__(self):
                self.stdout = io.StringIO()
                self.stderr = io.StringIO()
                self.out_i = self.err_i = 0

            def __iter__(self):
                return self

            def __next__(self):
                mediate_panel(progr_step=1)
                cur_step = maingui.progr_var.get()
                self.pump_streams(cur_step)

                if maingui._stop_job:
                    log.warn("Canceled %s job: %s", job_name, cmd_args)
                    raise StopIteration()

                item = next(self.it)

                msg = 'Job %s %s of %s: %r...' % (job_name, cur_step, self.len, item)
                maingui.mediate_panel(msg)

                return item

            def pump_streams(self, cur_step):
                new_out = self.stdout.getvalue()[self.out_i:]
                if new_out:
                    self.out_i += len(new_out)
                    log.info("Job %s stdout(%s): %s", job_name, cur_step, new_out)

                new_err = self.stderr.getvalue()[self.err_i:]
                if new_err:
                    self.err_i += len(new_err)
                    log.info("Job %s stderr(%s): %s", job_name, cur_step, new_err)

            def tqdm_replacement(self, iterable, *args, **kwds):
                #maingui.progr_var.set(1)  Already set to 1.
                self.it = iter(iterable)
                self.len = len(iterable)
                mediate_panel(progr_max=2 + self.len)  # +1 on start, +1 final step.

                return self

            def on_finish(self, out, err):
                maingui._job_thread = None
                mediate_panel(msg='', progr_max=0)

                new_out = self.stdout.getvalue()[self.out_i:]
                new_err = self.stderr.getvalue()[self.err_i:]
                if new_out:
                    new_out = '\n  stdout: %s' % indent(new_out, '    ')
                if new_err:
                    new_err = '\n  stderr: %s' % indent(new_err, '    ')
                log.info('Finished %s job: %s%s%s', job_name, cmd_args, new_out, new_err)

        ## Monkeypatch *tqdm* on co2mpas-batcher.
        #
        updater = ProgressUpdater()
        co2mpas_batch._custom_tqdm = updater.tqdm_replacement

        self._job_thread = t = Thread(
            target=run_python_job,
            args=(co2mpas_main, cmd_args, job_name,
                  updater.stdout, updater.stderr,
                  updater.on_finish),
            daemon=False,  # To ensure co2mpas do not corrupt output-files.
        )
        t.start()

        self.progr_bar['maximum'] = len(self.inputs_tree.get_children())
        self.progr_var.set(1)
        self.mediate_panel('Launched %s job...' % job_name)


class TkUI(object):

    """
    CO2MPAS UI for predicting NEDC CO2 emissions from WLTP for type-approval purposes.
    """
    def __init__(self, root=None):
        if not root:
            root = tk.Tk()
        self.root = root

        root.title("%s-%s" % (app_name, __version__))

        set_ttk_styles()

        # Menubar
        #
        menubar = tk.Menu(root)
        menubar.add_command(label="About %r" % app_name, command=self._do_about,)
        root['menu'] = menubar

        self.master = master = ttk.PanedWindow(root, orient=tk.VERTICAL, height=16)
        self.master.pack(fill=tk.BOTH, expand=1)
        self.master.configure(height=960, width=960)

        self.model_panel = _MainPanel(self.master, height=-560)
        master.add(self.model_panel, weight=1)

        self.log_panel = LogPanel(master, height=-120)
        master.add(self.log_panel, weight=2)

        s = ttk.Sizegrip(root)
        s.pack(side=tk.RIGHT)

    def open_url(self, url):
        webbrowser.open_new(url)

    def _do_about(self):
        top = tk.Toplevel(self.master)
        top.title("About %s" % app_name)

        txt1 = '%s\n\n' % self.__doc__.strip()
        txt2 = dedent("""\n

            Version: %s (%s)
            Copyright: %s
            License: %s
            Python: %s
            """ % (__version__, __updated__, __copyright__, __license__, sys.version))
        txt = '%s\n\n%s' % (txt1, txt2)
        log.info(txt)
        print(txt)

        msg = tk.Text(top, wrap=tk.WORD)
        msg.pack(fill=tk.BOTH, expand=1)
        linkman = HyperlinkManager(msg)

        msg.insert(tk.INSERT, txt1)

        msg.photo = read_image('icons/CO2MPAS_logo.png')  # Avoid GC.
        msg.image_create(tk.INSERT, image=msg.photo)
        msg.insert(tk.INSERT, txt2)
        msg.insert(tk.INSERT, 'Home: ')
        msg.insert(tk.INSERT, __uri__,
                   linkman.add(fnt.partial(self.open_url, __uri__)))

        msg.configure(state=tk.DISABLED, bg='SystemButtonFace')

    def mainloop(self):
        try:
            self.root.mainloop()
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass


def main():
    init_logging(verbose=None)
    app = TkUI()
    app.mainloop()

if __name__ == '__main__':
    if __package__ is None:
        __package__ = "co2mpas"  # @ReservedAssignment
    main()
