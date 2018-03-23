from bisect import bisect
import importlib
import itertools
import json
import keyword
import multiprocessing
import pathlib
import pprint
from queue import Empty
import re
import sys
import tempfile
import textwrap
from tkinter import Button as TKButton
from tkinter import Frame as TKFrame
from tkinter import Label as TKLabel
from tkinter import Menu, StringVar, PanedWindow, Text, Tk, Toplevel
from tkinter.ttk import Button, Entry, Frame, Label, Notebook, Scrollbar
import traceback
from urllib.parse import parse_qsl, urlencode
from urllib.request import HTTPError, Request, urlopen


class PositionSaver:
    """
    >>> pos_saver = PositionSaver()
    >>> overlapping_positions = []
    >>> for start_stop_list in [[(20, 40), (100, 300)],
    ...                         [(5, 8), (22, 25), (400, 403)],
    ...                         [(11, 13), (30, 32), (401, 402)]]:
    ...    fp, lp = pos_saver.new_record()
    ...    for start, stop in start_stop_list:
    ...        if pos_saver.has(start):
    ...            overlapping_positions.append(start)
    ...        else:
    ...            fp.append(start)
    ...            lp.append(stop)
    ...
    >>> overlapping_positions
    [22, 30, 401]
    """

    def __init__(self):
        self.first_positions = []
        self.last_positions = []
        self._nb_list = -1

    def new_record(self):
        self._nb_list += 1
        first = []
        last = []
        self.first_positions.append(first)
        self.last_positions.append(last)
        return first, last

    def has(self, pos):
        for i in range(self._nb_list):
            j = bisect(self.first_positions[i], pos) - 1
            if j >= 0 and self.first_positions[i][j] <= pos <= self.last_positions[i][j]:
                return True
        return False


class CodeEditor(Frame):
    def __init__(self, master):
        super().__init__(master)
        self.text = Text(self, font=("Mono", 12))
        self.text.tag_configure(
            'keyword', foreground='purple', font=("Mono", 12, 'bold'))
        self.text.tag_configure('string', foreground='blue')
        self.text.tag_configure('multiline_string', foreground='red')

        self.vscroll = Scrollbar(
            self, orient="vertical", command=self.text.yview)
        self.text.config(yscrollcommand=self.vscroll.set)

        self.vscroll.pack(side='right', fill='y')
        self.text.pack(side='right', fill='both', expand=1)

        re_kw = ''
        for kw in keyword.kwlist:
            re_kw += r'\b%s\b|' % kw
        re_kw = re_kw[:-1]

        self.tag_and_regexs = (
            ('multiline_string', re.compile(
                '(?P<quote>\'\'\'|""")(?:.|\\n)*?(?P=quote)')),
            ('string', re.compile(r'''(?P<quote>['"]).*?(?<!\\)(?P=quote)''')),
            ('keyword', re.compile(re_kw))
        )

        self.text.bind('<KeyRelease>', self.highlight)
        self.text.bind('<Tab>', self._spaces_on_tab)

    def highlight(self, event=None):
        text_widget = self.text
        text_widget.tag_remove('keyword', '1.0', 'end')

        text = text_widget.get('1.0', 'end')[:-1]  # \n final

        pos_saver = PositionSaver()

        for tag, regex in self.tag_and_regexs:
            last_pos = 0
            first_pos_records, last_pos_records = pos_saver.new_record()
            while True:
                match = regex.search(text, last_pos)
                if match is None:
                    break

                start_pos = match.start()
                last_pos = match.end()

                if not pos_saver.has(start_pos):
                    first_pos_records.append(start_pos)
                    last_pos_records.append(last_pos)

                    text_widget.tag_add(
                        tag,
                        '%s + %d chars' % ('1.0', start_pos),
                        '%s + %d chars' % ('1.0', last_pos))

    def insert(self, *args, **kwargs):
        self.text.insert(*args, **kwargs)
        self.highlight()

    def get(self, *args, **kwargs):
        return self.text.get(*args, **kwargs)

    def _spaces_on_tab(self, event=None):
        self.text.insert('insert', '    ')
        return 'break'


class VariableSet:
    def set_master(self, master):
        self.host = StringVar(master)
        self.team = StringVar(master)
        self.member_id = StringVar(master)
        self._tempdir = tempfile.TemporaryDirectory(prefix='asteriostk')
        self.tempdir = pathlib.Path(self._tempdir.name)
        self.tmp_file = self.tempdir / 'astrios_solver.py'
        self.module_solver = None
        self.puzzle = None
        sys.path.insert(0, str(self.tempdir))


VARIABLES = VariableSet()


class NotificationViewer(TKFrame):
    class Notif(TKFrame):
        def __init__(self, master, message, bg='white'):
            super().__init__(master, bg=bg, highlightthickness=1,
                             borderwidth=0, padx=1, pady=1, relief='flat')
            TKLabel(self,
                    bg=bg,
                    text=message,
                    justify='left',
                    anchor='w').pack(side='left',
                                     fill='x',
                                     expand=1,
                                     anchor='w')
            TKButton(self,
                     bg=bg,
                     text='❌',
                     width='1',
                     height='1',
                     padx=4, pady=2,
                     relief='flat',
                     border=0,
                     highlightthickness=0,
                     command=self.destroy).pack(side='left',
                                                expand=1,
                                                anchor='ne')

    def __init__(self, master, **kwarg):
        super().__init__(master, **kwarg)

    def notify(self, message, severity=None):
        if severity == 'error':
            bg_color = 'red'
        elif severity == 'success':
            bg_color = 'green'
        else:
            bg_color = 'white'

        self.Notif(self, message, bg_color).pack(
            fill='x', expand=1, anchor='n')


class Configurator(Toplevel):
    """
    """

    def __init__(self, app=None, *args, **kwargs):
        start_command = kwargs.pop('start_command')
        super().__init__(app.root, *args, **kwargs)
        text = StringVar(app.root)
        self.transient(app.root)
        self.title('client configuration')

        VARIABLES.host.set('http://127.0.0.1:8000')

        def _start_command():
            """
            Wrapper calling `start_command` before closing the toplevel.
            """
            start_command()
            self.destroy()

        Label(self, text='host:').grid(row=1, column=1)
        Entry(self, textvariable=VARIABLES.host).grid(row=1, column=2)
        Label(self, text='team:').grid(row=2, column=1)
        Entry(self, textvariable=VARIABLES.team).grid(row=2, column=2)
        Label(self, text='member id:').grid(row=3, column=1)
        Entry(self, textvariable=VARIABLES.member_id).grid(row=3, column=2)
        Button(self, text='Start', command=_start_command).grid(
            row=4, column=2, sticky='e')


class PuzzleViewer(Frame):

    @classmethod
    def _format(cls, obj, indent=0):
        prefix = '  ' * indent
        if isinstance(obj, list):
            return textwrap.indent(
                '\n[' + ','.join(cls._format(e, indent + 1)
                                 for e in obj) + '\n]',
                prefix)
        elif isinstance(obj, dict):
            return textwrap.indent(
                '\n{' + (','.join(
                         '{}:{}'.format(cls._format(k, indent + 1),
                                        cls._format(v, indent + 1))
                         for k, v
                         in obj.items())) + '\n}',
                prefix)
        return textwrap.indent('\n' + str(obj), prefix)

    def __init__(self, master):
        super().__init__(master)
        self._text = Text(self, font=("Mono", 12))
        self.button = Button(self, text='repr',
                             command=self.toggle)
        self._raw_text = ''
        self._text.pack(fill='both', expand=1)
        self.button.pack()

    def update_text(self, obj):
        self._raw_text = obj
        self._text.delete('0.0', 'end')
        if self.button.cget('text') == 'repr':
            self._text.insert('end', pprint.pformat(obj))
        else:
            self._text.insert('end', self._format(obj))

    def toggle(self):
        if self.button.cget('text') == 'repr':
            self.button.config(text='str')
            self.update_text(self._raw_text)
        else:
            self.button.config(text='repr')
            self.update_text(self._raw_text)


class GameOverToplevel(Toplevel):
    def __init__(self, master, text_label):
        super().__init__(master)
        self.title('Asterios: Game Over')
        label = TKLabel(self, text=text_label,
                        font=("Mono", 40, 'bold'))
        label.pack(fill='both', expand=1)

        for toplevel in master.children.values():
            if toplevel != self:
                self.wm_transient(toplevel)
        self.wm_transient(master)

        sprites = self._sprites(text_label)

        def animate():
            time, text = next(sprites)
            label.config(text=text)
            self.after(time, animate)

        animate()

    @staticmethod
    def _sprites(text):
        nb_spaces = len(text) - 3
        return itertools.cycle(
            [(125, ' ' * i + char + ' ' * (nb_spaces - i))
             for i, char
             in enumerate(
                [''.join(e) for e in zip(text, text[1:], text[2:])]
            )] + [(250, ' ' * len(text)), (3000, text)]
        )


class Application:
    def __init__(self):
        self.root = Tk()
        VARIABLES.set_master(self.root)
        self.root.wm_title('asterios')
        self._init_menu()

        paned_window = PanedWindow(self.root, orient='vertical')

        nb = Notebook(paned_window)

        self.tips_text = Text(nb)
        nb.add(self.tips_text, text='tips')

        self.puzzle_text = PuzzleViewer(nb)
        nb.add(self.puzzle_text, text='puzzle')

        self.solver_text = CodeEditor(nb)
        nb.add(self.solver_text, text='solver')
        self.solver_text.insert(
            'end',
            textwrap.dedent('''\
                def solve(puzzle):
                    """
                    Complete cette fonction
                    """
                    puzzle_solved = '...'

                    return puzzle_solved
            ''')
        )

        self.notif_text = NotificationViewer(paned_window, relief='ridge', border=3)

        paned_window.add(nb, sticky='nsew')
        paned_window.add(self.notif_text, sticky='nsew', minsize=80)
        paned_window.pack(fill='both', expand=1)
        self.show_configuration_window()

    def _init_menu(self):
        self.menubar = Menu(self.root)
        self.root.config(menu=self.menubar)
        self.menubar.insert_command(1, label="config",
                                    command=self.show_configuration_window)
        self.menubar.insert_command(2, label="run", command=self.solve)

    def show_configuration_window(self):
        Configurator(self, start_command=self.start_game)

    def run_menu_swith(self, **cfg):
        self.menubar.entryconfigure(2, cfg)

    def run_menu_restart(self):
        self.menubar.entryconfigure(2, label='run', command=self.solve)

    def notify(self, message, severity=None):
        self.notif_text.notify(message, severity)

    def start(self):
        self.root.mainloop()

    def start_game(self):
        self.set_puzzle_and_tips_text()

    def set_puzzle_and_tips_text(self):
        url = '{host}/asterios/{team}/member/{member_id}'.format(
            host=VARIABLES.host.get(),
            team=VARIABLES.team.get(),
            member_id=VARIABLES.member_id.get()
        )

        request = Request(url, method='GET')  # headers=dict(headers)
        try:
            response = urlopen(request)  # timeout=120
        except HTTPError as error:
            msg = error.read().decode('utf-8')

            try:
                data = json.loads(msg)
            except:
                self.notify(msg)
            else:
                if data['exception'] == 'LevelSet.DoneException':
                    GameOverToplevel(self.root, 'Victory')
                else:
                    self.notify(msg)

        else:
            data = json.loads(response.read().decode('utf-8'))
            self.tips_text.delete('0.0', 'end')
            self.tips_text.insert('end', data['tip'])
            self.puzzle_text.update_text(data['puzzle'])
            VARIABLES.puzzle = data['puzzle']

    def _display_solved_puzzle(self, solved_puzzle):
        """
        Shows a Toplevel containing the `solved_puzzle`.
        """
        top_level = Toplevel(self.root)
        viewer = PuzzleViewer(top_level)
        viewer.pack()
        viewer.update_text(solved_puzzle)
        top_level.wm_transient(self.root)

    def solve(self):

        def filter_traceback(tb):
            new_tb = tb[:1]
            iter_tb = iter(tb)
            expected_line = '  File "{}",'.format(VARIABLES.tmp_file)
            for line in iter_tb:
                if line.startswith(expected_line):
                    new_tb.append(line)
                    break
            new_tb.extend(iter_tb)
            return new_tb

        code = self.solver_text.get('0.0', 'end')
        with VARIABLES.tmp_file.open('w') as py_file:
            py_file.write(code)

        try:
            importlib.invalidate_caches()
            if hasattr(VARIABLES.module_solver, 'solve'):
                del VARIABLES.module_solver.solve

            if VARIABLES.module_solver is None:
                VARIABLES.module_solver = importlib.import_module(
                    'astrios_solver')
            else:
                VARIABLES.module_solver = importlib.reload(
                    VARIABLES.module_solver)

        except Exception as error:
            tb = traceback.format_exception(
                type(error), error, error.__traceback__)
            tb = filter_traceback(tb)
            self.notify(''.join(tb), 'error')
            return

        if not (hasattr(VARIABLES.module_solver, 'solve') and
                callable(VARIABLES.module_solver.solve)):
            self.notify('Error: `solve` function not found', 'error')
            return

        def target(queue):
            """
            Try to run solve function and push the result
            in the `queue` (True, result) or (False, error)
            """
            try:
                solution = VARIABLES.module_solver.solve(VARIABLES.puzzle)
                queue.put((True, solution))
            except Exception as error:
                tb = traceback.format_exception(
                    type(error), error, error.__traceback__)
                tb = filter_traceback(tb)
                queue.put((False, tb))

        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=target, args=(queue,))

        def wait_for_solver():
            try:
                success, solution_or_error = queue.get_nowait()
            except Empty:
                self.root.after(250, wait_for_solver)
                return None
            # except OSError:
            #

            if not success:
                self.notify(''.join(solution_or_error), 'error')
            else:
                self._display_solved_puzzle(solution_or_error)
                try:
                    solution = json.dumps(solution_or_error)
                except (ValueError, TypeError) as error:
                    self.notify('The solve function should return a'
                                ' JSON serializable object ({})'.format(error), 'error')
                    return

                url = '{host}/asterios/{team}/member/{member_id}'.format(
                    host=VARIABLES.host.get(),
                    team=VARIABLES.team.get(),
                    member_id=VARIABLES.member_id.get()
                )

                try:
                    # headers=dict(headers)
                    request = Request(url, method='POST')
                except ValueError:
                    self.notify('Error: Wrong url: `{}`'.format(url), 'error')
                else:
                    request.data = solution.encode('utf-8')
                    try:
                        response = urlopen(request)  # timeout=120
                    except HTTPError as error:
                        self.notify(json.loads(error.read().decode('utf-8')))

                    else:
                        self.notify(json.loads(
                            response.read().decode('utf-8')), 'success')
                        self.set_puzzle_and_tips_text()

            self.run_menu_restart()

        process.start()

        def kill():
            queue.put((False, 'killed'))
            process.terminate()
            self.run_menu_restart()

        self.run_menu_swith(label='kill', command=kill)
        self.root.after(0, wait_for_solver)


if __name__ == '__main__':
    app = Application()
    app.start()
