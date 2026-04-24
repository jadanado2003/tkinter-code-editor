from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

STARTER_TEXT = '# Write your code here\nprint("Hello world")\n'
BG = '#111111'
PANEL = '#181818'
GUTTER = '#0d0d0d'
TEXT_BG = '#101010'
TEXT_FG = '#e8e8e8'
CARET = '#f5f5f5'
ACCENT = '#2b2b2b'
TAB_ACTIVE = '#1f1f1f'
TAB_INACTIVE = '#141414'
LINE_NO = '#8f8f8f'
STATUS = '#202020'
OUTPUT_BG = '#0b0b0b'
OUTPUT_FG = '#d8d8d8'
ERROR_FG = '#ff8a8a'
SUCCESS_FG = '#9ae6b4'

RUN_MODES = ('Auto', 'Python', 'Lua', 'JavaScript')
RUN_SUFFIX = {
    'Python': '.py',
    'Lua': '.lua',
    'JavaScript': '.js',
}


@dataclass
class EditorTab:
    frame: ttk.Frame
    editor: 'CodeEditor'
    path: Path | None = None


class CodeEditor(tk.Frame):
    def __init__(self, master, text: str = STARTER_TEXT):
        super().__init__(master, bg=BG)

        self.line_numbers = tk.Text(
            self,
            width=4,
            padx=8,
            pady=8,
            takefocus=0,
            borderwidth=0,
            highlightthickness=0,
            background=GUTTER,
            foreground=LINE_NO,
            state='disabled',
            wrap='none',
            font=('Consolas', 12),
            cursor='arrow',
        )
        self.line_numbers.pack(side='left', fill='y')

        self.text = tk.Text(
            self,
            wrap='none',
            undo=True,
            borderwidth=0,
            highlightthickness=0,
            background=TEXT_BG,
            foreground=TEXT_FG,
            insertbackground=CARET,
            selectbackground='#2d4f7a',
            font=('Consolas', 12),
            padx=10,
            pady=8,
        )
        self.text.pack(side='left', fill='both', expand=True)

        self.y_scroll = ttk.Scrollbar(self, orient='vertical', command=self._on_scrollbar_y)
        self.y_scroll.pack(side='right', fill='y')
        self.x_scroll = ttk.Scrollbar(self, orient='horizontal', command=self.text.xview)
        self.x_scroll.pack(side='bottom', fill='x')

        self.text.configure(yscrollcommand=self._sync_vertical, xscrollcommand=self.x_scroll.set)
        self.line_numbers.configure(yscrollcommand=self.y_scroll.set)

        self.text.insert('1.0', text)
        self.text.edit_modified(False)
        self.update_line_numbers()

        self.text.bind('<KeyRelease>', self._on_change)
        self.text.bind('<ButtonRelease-1>', self._on_change)
        self.text.bind('<MouseWheel>', self._on_change)
        self.text.bind('<Configure>', self._on_change)
        self.text.bind('<Tab>', self._insert_spaces)
        self.text.bind('<<Modified>>', self._on_modified)

    def _insert_spaces(self, _event):
        self.text.insert('insert', '    ')
        return 'break'

    def _sync_vertical(self, first: str, last: str):
        self.y_scroll.set(first, last)
        try:
            self.line_numbers.yview_moveto(float(first))
        except (TypeError, ValueError):
            pass

    def _on_scrollbar_y(self, *args):
        self.text.yview(*args)
        self.line_numbers.yview(*args)

    def _on_change(self, _event=None):
        self.update_line_numbers()

    def _on_modified(self, _event=None):
        self.text.edit_modified(False)
        self.update_line_numbers()

    def update_line_numbers(self):
        end_line = int(self.text.index('end-1c').split('.')[0])
        content = '\n'.join(str(i) for i in range(1, end_line + 1))
        self.line_numbers.configure(state='normal')
        self.line_numbers.delete('1.0', 'end')
        self.line_numbers.insert('1.0', content)
        self.line_numbers.configure(state='disabled')
        yview = self.text.yview()
        if yview:
            self.line_numbers.yview_moveto(yview[0])

    def get_text(self) -> str:
        return self.text.get('1.0', 'end-1c')

    def set_text(self, value: str):
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', value)
        self.text.edit_modified(False)
        self.update_line_numbers()

    def focus_editor(self):
        self.text.focus_set()


class CodeEditorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Simple Code GUI')
        self.geometry('1200x760')
        self.minsize(860, 560)
        self.configure(bg=BG)
        self.fullscreen = False
        self.tab_counter = 1
        self.tabs: dict[str, EditorTab] = {}

        self.run_mode_var = tk.StringVar(value='Auto')
        self.status_var = tk.StringVar(value='Ready')
        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.temp_run_file: Path | None = None

        self._configure_style()
        self._build_toolbar()
        self._build_main_area()
        self._build_statusbar()
        self._bind_shortcuts()
        self.protocol('WM_DELETE_WINDOW', self.on_close)

        self.new_tab()
        self.after(100, self._poll_output_queue)
        self.update_status()

    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('TLabel', background=STATUS, foreground=TEXT_FG)
        style.configure(
            'TButton',
            background=ACCENT,
            foreground=TEXT_FG,
            borderwidth=0,
            focusthickness=0,
            padding=(10, 6),
        )
        style.map('TButton', background=[('active', '#333333')], foreground=[('active', TEXT_FG)])
        style.configure('Editor.TNotebook', background=BG, borderwidth=0)
        style.configure(
            'Editor.TNotebook.Tab',
            background=TAB_INACTIVE,
            foreground=TEXT_FG,
            padding=(14, 8),
            borderwidth=0,
        )
        style.map(
            'Editor.TNotebook.Tab',
            background=[('selected', TAB_ACTIVE), ('active', '#262626')],
            foreground=[('selected', '#ffffff')],
        )
        style.configure('TCombobox', fieldbackground=ACCENT, background=ACCENT, foreground=TEXT_FG)
        style.map('TCombobox', fieldbackground=[('readonly', ACCENT)], selectbackground=[('readonly', ACCENT)])

    def _build_toolbar(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', padx=8, pady=(8, 0))

        ttk.Button(toolbar, text='New Tab', command=self.new_tab).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Open', command=self.open_file).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Save', command=self.save_file).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Save As', command=self.save_file_as).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Close Tab', command=self.close_current_tab).pack(side='left', padx=(0, 12))

        ttk.Label(toolbar, text='Run As:').pack(side='left', padx=(0, 6))
        mode_box = ttk.Combobox(toolbar, textvariable=self.run_mode_var, values=RUN_MODES, state='readonly', width=12)
        mode_box.pack(side='left', padx=(0, 8))

        ttk.Button(toolbar, text='Run (F5)', command=self.run_code).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Stop', command=self.stop_code).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Clear Output', command=self.clear_output).pack(side='left', padx=(0, 6))
        ttk.Button(toolbar, text='Toggle Fullscreen', command=self.toggle_fullscreen).pack(side='right')

    def _build_main_area(self):
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=8, pady=8)

        self.vertical_pane = ttk.Panedwindow(container, orient=tk.VERTICAL)
        self.vertical_pane.pack(fill='both', expand=True)

        editor_container = ttk.Frame(self.vertical_pane)
        output_container = ttk.Frame(self.vertical_pane)

        self.vertical_pane.add(editor_container, weight=5)
        self.vertical_pane.add(output_container, weight=2)

        self.notebook = ttk.Notebook(editor_container, style='Editor.TNotebook')
        self.notebook.pack(fill='both', expand=True)
        self.notebook.bind('<<NotebookTabChanged>>', lambda _e: self.update_status())

        header = tk.Frame(output_container, bg=PANEL, height=30, borderwidth=0, highlightthickness=0)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text='Output', bg=PANEL, fg=TEXT_FG, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=10)

        output_body = tk.Frame(output_container, bg=OUTPUT_BG, borderwidth=0, highlightthickness=0)
        output_body.pack(fill='both', expand=True)

        self.output = tk.Text(
            output_body,
            wrap='word',
            borderwidth=0,
            highlightthickness=0,
            background=OUTPUT_BG,
            foreground=OUTPUT_FG,
            insertbackground=CARET,
            font=('Consolas', 11),
            padx=10,
            pady=8,
            state='disabled',
        )
        self.output.pack(side='left', fill='both', expand=True)

        out_scroll = ttk.Scrollbar(output_body, orient='vertical', command=self.output.yview)
        out_scroll.pack(side='right', fill='y')
        self.output.configure(yscrollcommand=out_scroll.set)

        self.output.tag_configure('stderr', foreground=ERROR_FG)
        self.output.tag_configure('stdout', foreground=OUTPUT_FG)
        self.output.tag_configure('system_ok', foreground=SUCCESS_FG)
        self.output.tag_configure('system_err', foreground=ERROR_FG)

    def _build_statusbar(self):
        status_frame = ttk.Frame(self)
        status_frame.pack(fill='x', side='bottom')
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor='w')
        self.status_label.pack(fill='x', padx=10, pady=6)

    def _bind_shortcuts(self):
        self.bind('<Control-n>', lambda _e: self.new_tab())
        self.bind('<Control-o>', lambda _e: self.open_file())
        self.bind('<Control-s>', lambda _e: self.save_file())
        self.bind('<Control-S>', lambda _e: self.save_file_as())
        self.bind('<Control-w>', lambda _e: self.close_current_tab())
        self.bind('<F5>', lambda _e: self.run_code())
        self.bind('<Shift-F5>', lambda _e: self.stop_code())
        self.bind('<F11>', lambda _e: self.toggle_fullscreen())
        self.bind('<Escape>', lambda _e: self.exit_fullscreen())

    def current_tab_id(self) -> str | None:
        current = self.notebook.select()
        return current if current else None

    def current_editor_tab(self) -> EditorTab | None:
        tab_id = self.current_tab_id()
        if tab_id is None:
            return None
        return self.tabs.get(tab_id)

    def new_tab(self, text: str = STARTER_TEXT, title: str | None = None):
        frame = ttk.Frame(self.notebook)
        editor = CodeEditor(frame, text=text)
        editor.pack(fill='both', expand=True)

        tab_title = title or f'Tab {self.tab_counter}'
        self.tab_counter += 1
        self.notebook.add(frame, text=tab_title)
        tab_id = self.notebook.tabs()[-1]
        self.tabs[tab_id] = EditorTab(frame=frame, editor=editor)
        self.notebook.select(frame)
        editor.focus_editor()
        self.update_status()

    def close_current_tab(self):
        tab_id = self.current_tab_id()
        if tab_id is None:
            return

        if len(self.notebook.tabs()) == 1:
            if not messagebox.askyesno('Close Tab', 'This is the last tab. Close it and create a blank one?'):
                return
            self.notebook.forget(tab_id)
            self.tabs.pop(tab_id, None)
            self.new_tab()
            return

        self.notebook.forget(tab_id)
        self.tabs.pop(tab_id, None)
        self.update_status()

    def open_file(self):
        path = filedialog.askopenfilename(
            title='Open File',
            filetypes=[
                ('Code files', '*.py *.lua *.js *.ts *.html *.css *.json *.txt'),
                ('All files', '*.*'),
            ],
        )
        if not path:
            return

        file_path = Path(path)
        try:
            content = file_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            content = file_path.read_text(encoding='latin-1')
        except OSError as exc:
            messagebox.showerror('Open File', f'Could not open file.\n\n{exc}')
            return

        self.new_tab(text=content, title=file_path.name)
        current = self.current_editor_tab()
        if current:
            current.path = file_path
        self.update_status(f'Opened {file_path.name}')

    def save_file(self):
        current = self.current_editor_tab()
        if current is None:
            return
        if current.path is None:
            self.save_file_as()
            return

        try:
            current.path.write_text(current.editor.get_text(), encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('Save File', f'Could not save file.\n\n{exc}')
            return

        self._rename_current_tab(current.path.name)
        self.update_status(f'Saved {current.path.name}')

    def save_file_as(self):
        current = self.current_editor_tab()
        if current is None:
            return

        path = filedialog.asksaveasfilename(
            title='Save File As',
            defaultextension='.txt',
            filetypes=[
                ('Python', '*.py'),
                ('Lua', '*.lua'),
                ('JavaScript', '*.js'),
                ('Text', '*.txt'),
                ('All files', '*.*'),
            ],
        )
        if not path:
            return

        current.path = Path(path)
        self.save_file()

    def _rename_current_tab(self, title: str):
        current_id = self.current_tab_id()
        if current_id:
            self.notebook.tab(current_id, text=title)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.attributes('-fullscreen', self.fullscreen)
        mode = 'Fullscreen' if self.fullscreen else 'Windowed'
        self.update_status(f'Switched to {mode} mode')

    def exit_fullscreen(self):
        if self.fullscreen:
            self.fullscreen = False
            self.attributes('-fullscreen', False)
            self.update_status('Exited fullscreen')

    def clear_output(self):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.configure(state='disabled')
        self.update_status('Cleared output')

    def append_output(self, text: str, tag: str = 'stdout'):
        self.output.configure(state='normal')
        self.output.insert('end', text, tag)
        self.output.see('end')
        self.output.configure(state='disabled')

    def detect_run_mode(self, path: Path | None) -> str:
        mode = self.run_mode_var.get()
        if mode != 'Auto':
            return mode
        suffix = (path.suffix.lower() if path else '')
        if suffix == '.py':
            return 'Python'
        if suffix == '.lua':
            return 'Lua'
        if suffix == '.js':
            return 'JavaScript'
        return 'Python'

    def interpreter_for_mode(self, mode: str) -> list[str] | None:
        if mode == 'Python':
            return [sys.executable]
        if mode == 'Lua':
            lua = shutil.which('lua') or shutil.which('luajit')
            return [lua] if lua else None
        if mode == 'JavaScript':
            node = shutil.which('node')
            return [node] if node else None
        return None

    def run_code(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Run Code', 'A program is already running. Stop it first.')
            return

        current = self.current_editor_tab()
        if current is None:
            return

        mode = self.detect_run_mode(current.path)
        interpreter = self.interpreter_for_mode(mode)
        if interpreter is None or not interpreter[0]:
            self.append_output(f'[{mode}] interpreter not found on this system.\n', 'system_err')
            self.update_status(f'{mode} interpreter not found')
            return

        self._cleanup_temp_run_file()
        path_to_run = current.path

        if path_to_run is None:
            suffix = RUN_SUFFIX.get(mode, '.txt')
            temp_dir = Path(tempfile.gettempdir())
            temp_path = temp_dir / f'simple_code_editor_temp{suffix}'
            try:
                temp_path.write_text(current.editor.get_text(), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Run Code', f'Could not create temp file.\n\n{exc}')
                return
            self.temp_run_file = temp_path
            path_to_run = temp_path
        else:
            try:
                path_to_run.write_text(current.editor.get_text(), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Run Code', f'Could not prepare file for run.\n\n{exc}')
                return

        self.append_output(f'\n>>> Running {path_to_run.name} as {mode}\n', 'system_ok')
        self.update_status(f'Running {path_to_run.name} as {mode}')

        try:
            self.process = subprocess.Popen(
                [*interpreter, str(path_to_run)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError as exc:
            self.append_output(f'Failed to start process: {exc}\n', 'system_err')
            self.update_status('Failed to start process')
            self.process = None
            return

        threading.Thread(target=self._reader_thread, args=(self.process.stdout, 'stdout'), daemon=True).start()
        threading.Thread(target=self._reader_thread, args=(self.process.stderr, 'stderr'), daemon=True).start()
        threading.Thread(target=self._wait_for_process, args=(self.process,), daemon=True).start()

    def stop_code(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.append_output('>>> Process stopped by user\n', 'system_err')
            self.update_status('Process stopped')
        else:
            self.update_status('No running process')

    def _reader_thread(self, stream, tag: str):
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                self.output_queue.put((tag, line))
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _wait_for_process(self, process: subprocess.Popen[str]):
        code = process.wait()
        tag = 'system_ok' if code == 0 else 'system_err'
        self.output_queue.put((tag, f'>>> Process exited with code {code}\n'))
        self.output_queue.put(('__done__', str(code)))

    def _poll_output_queue(self):
        while True:
            try:
                tag, text = self.output_queue.get_nowait()
            except queue.Empty:
                break

            if tag == '__done__':
                self.process = None
                self._cleanup_temp_run_file()
                code = int(text)
                status = 'Run finished successfully' if code == 0 else f'Run finished with code {code}'
                self.update_status(status)
            else:
                self.append_output(text, tag)

        self.after(100, self._poll_output_queue)

    def _cleanup_temp_run_file(self):
        if self.temp_run_file and self.temp_run_file.exists():
            try:
                self.temp_run_file.unlink()
            except OSError:
                pass
        self.temp_run_file = None

    def update_status(self, message: str | None = None):
        if message:
            self.status_var.set(message)
            return
        current = self.current_editor_tab()
        if current is None:
            self.status_var.set('No tab open')
            return
        title = self.notebook.tab(self.current_tab_id(), 'text')
        location = str(current.path) if current.path else 'Unsaved'
        self.status_var.set(f'Current tab: {title}    |    {location}    |    F5 run, Shift+F5 stop, F11 fullscreen')

    def on_close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno('Exit', 'A program is still running. Stop it and exit?'):
                return
            try:
                self.process.terminate()
            except Exception:
                pass
        self._cleanup_temp_run_file()
        self.destroy()


if __name__ == '__main__':
    app = CodeEditorApp()
    app.mainloop()
