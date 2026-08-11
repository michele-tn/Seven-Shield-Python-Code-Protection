"""Polished Tkinter desktop interface for Seven Shield."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from seven_shield.obfuscator import ObfuscationOptions, Obfuscator


class SevenShieldApp:
    """Accessible desktop workspace exposing all seven protection layers."""

    C = {
        "bg": "#070b14", "surface": "#0e1626", "raised": "#141f33", "editor": "#0a101c",
        "border": "#24334d", "text": "#f4f7fb", "muted": "#91a0ba", "accent": "#6d5dfc",
        "accent2": "#18c8a0", "danger": "#ff6b7a", "line": "#111a2b",
    }
    EXAMPLE_SOURCE = 'print("Ciao Mondo!")\n'
    LAYERS = (
        ("Rename", "Identificatori irriconoscibili"),
        ("Encrypt", "Payload compilato e mascherato"),
        ("Flatten", "Flusso a macchina di stati"),
        ("Hide Builtins", "Builtin risolti indirettamente"),
        ("Hide Imports", "Import caricati dinamicamente"),
        ("Hide Attrs", "Attributi nascosti con getattr"),
        ("Junk Code", "Rami opachi e codice morto"),
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Seven Shield — Python Code Protection")
        self.root.geometry("1280x800")
        self.root.minsize(1000, 660)
        self.root.configure(bg=self.C["bg"])
        self.flags = {name: tk.BooleanVar(value=True) for name, _ in self.LAYERS}
        self.status = tk.StringVar(value="Pronto · Elaborazione locale")
        self._configure_style()
        self._build()
        self._bind_shortcuts()

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Layer.TCheckbutton", background=self.C["surface"], foreground=self.C["text"], font=("Segoe UI Semibold", 10))
        style.map("Layer.TCheckbutton", background=[("active", self.C["surface"])], foreground=[("disabled", self.C["muted"])])
        style.configure("Ghost.TButton", background=self.C["raised"], foreground=self.C["text"], bordercolor=self.C["border"], padding=(14, 9), font=("Segoe UI Semibold", 9))
        style.map("Ghost.TButton", background=[("active", self.C["border"])])
        style.configure("Primary.TButton", background=self.C["accent"], foreground="white", borderwidth=0, padding=(22, 11), font=("Segoe UI Semibold", 10))
        style.map("Primary.TButton", background=[("active", "#8174ff")])

    def _build(self) -> None:
        self._build_header()
        body = tk.Frame(self.root, bg=self.C["bg"])
        body.pack(fill="both", expand=True, padx=22, pady=(0, 12))
        self._build_sidebar(body)
        self._build_workspace(body)
        self._build_footer()
        self._load_example()

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=self.C["bg"], padx=24, pady=17)
        header.pack(fill="x")
        mark = tk.Canvas(header, width=40, height=40, bg=self.C["bg"], highlightthickness=0)
        mark.create_polygon(20, 2, 36, 8, 33, 29, 20, 38, 7, 29, 4, 8, fill=self.C["accent"], outline="#9e94ff", width=2)
        mark.create_text(20, 20, text="7", fill="white", font=("Segoe UI Semibold", 14))
        mark.pack(side="left")
        title = tk.Frame(header, bg=self.C["bg"])
        title.pack(side="left", padx=12)
        tk.Label(title, text="SEVEN SHIELD", bg=self.C["bg"], fg=self.C["text"], font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(title, text="Python Code Protection Studio", bg=self.C["bg"], fg=self.C["muted"], font=("Segoe UI", 9)).pack(anchor="w")
        badge = tk.Label(header, text="●  LOCAL ONLY", bg="#102a28", fg=self.C["accent2"], font=("Segoe UI Semibold", 9), padx=12, pady=6)
        badge.pack(side="right")

    def _build_sidebar(self, parent: tk.Frame) -> None:
        sidebar = tk.Frame(parent, width=260, bg=self.C["surface"], highlightthickness=1, highlightbackground=self.C["border"], padx=16, pady=16)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="PROTEZIONE", bg=self.C["surface"], fg=self.C["muted"], font=("Segoe UI Semibold", 9)).pack(anchor="w")
        tk.Label(sidebar, text="7 livelli attivi", bg=self.C["surface"], fg=self.C["text"], font=("Segoe UI Semibold", 15)).pack(anchor="w", pady=(3, 14))
        for name, description in self.LAYERS:
            row = tk.Frame(sidebar, bg=self.C["surface"], pady=5)
            row.pack(fill="x")
            ttk.Checkbutton(row, text=name, variable=self.flags[name], style="Layer.TCheckbutton", command=self._update_layer_count).pack(anchor="w")
            tk.Label(row, text=description, bg=self.C["surface"], fg=self.C["muted"], font=("Segoe UI", 8), wraplength=210, justify="left").pack(anchor="w", padx=(24, 0))
        controls = tk.Frame(sidebar, bg=self.C["surface"])
        controls.pack(fill="x", pady=(14, 0))
        ttk.Button(controls, text="Tutti", style="Ghost.TButton", command=lambda: self._set_layers(True)).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(controls, text="Nessuno", style="Ghost.TButton", command=lambda: self._set_layers(False)).pack(side="left", expand=True, fill="x", padx=(4, 0))

    def _build_workspace(self, parent: tk.Frame) -> None:
        workspace = tk.Frame(parent, bg=self.C["bg"])
        workspace.pack(side="left", fill="both", expand=True)
        toolbar = tk.Frame(workspace, bg=self.C["raised"], highlightthickness=1, highlightbackground=self.C["border"], padx=10, pady=9)
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Button(toolbar, text="Apri  Ctrl+O", style="Ghost.TButton", command=self._open).pack(side="left")
        ttk.Button(toolbar, text="Salva  Ctrl+S", style="Ghost.TButton", command=self._save).pack(side="left", padx=7)
        ttk.Button(toolbar, text="Pulisci", style="Ghost.TButton", command=self._clear).pack(side="left")
        ttk.Button(toolbar, text="PROTEGGI  Ctrl+Enter", style="Primary.TButton", command=self._obfuscate).pack(side="right")
        editors = tk.PanedWindow(workspace, orient="horizontal", bg=self.C["bg"], sashwidth=10, bd=0)
        editors.pack(fill="both", expand=True)
        self.source = self._editor_panel(editors, "01  SORGENTE", "Modifica qui il tuo Python")
        self.output = self._editor_panel(editors, "02  OUTPUT PROTETTO", "Artefatto pronto da distribuire")

    def _editor_panel(self, parent: tk.PanedWindow, title: str, subtitle: str) -> tk.Text:
        panel = tk.Frame(parent, bg=self.C["surface"], highlightthickness=1, highlightbackground=self.C["border"])
        heading = tk.Frame(panel, bg=self.C["surface"], padx=14, pady=10)
        heading.pack(fill="x")
        tk.Label(heading, text=title, bg=self.C["surface"], fg=self.C["text"], font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(heading, text=subtitle, bg=self.C["surface"], fg=self.C["muted"], font=("Segoe UI", 8)).pack(anchor="w")
        editor = tk.Text(panel, wrap="none", undo=True, bg=self.C["editor"], fg="#dce6f7", insertbackground=self.C["accent2"], selectbackground=self.C["accent"], font=("Cascadia Code", 10), padx=16, pady=14, relief="flat", spacing1=2)
        yscroll = ttk.Scrollbar(panel, orient="vertical", command=editor.yview)
        yscroll.pack(side="right", fill="y")
        editor.configure(yscrollcommand=yscroll.set)
        editor.pack(fill="both", expand=True)
        parent.add(panel, stretch="always", minsize=320)
        return editor

    def _build_footer(self) -> None:
        footer = tk.Frame(self.root, bg=self.C["surface"], padx=24, pady=8)
        footer.pack(fill="x")
        tk.Label(footer, textvariable=self.status, bg=self.C["surface"], fg=self.C["muted"], font=("Segoe UI", 9)).pack(side="left")
        self.layer_count = tk.Label(footer, text="7/7 livelli", bg=self.C["surface"], fg=self.C["accent2"], font=("Segoe UI Semibold", 9))
        self.layer_count.pack(side="right")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _event: self._open())
        self.root.bind("<Control-s>", lambda _event: self._save())
        self.root.bind("<Control-Return>", lambda _event: self._obfuscate())

    def _options(self) -> ObfuscationOptions:
        return ObfuscationOptions(*(self.flags[name].get() for name, _ in self.LAYERS))

    def _load_example(self) -> None:
        self.source.insert("1.0", self.EXAMPLE_SOURCE)
        self.output.insert("1.0", Obfuscator().obfuscate(self.EXAMPLE_SOURCE, ObfuscationOptions(seed=7)))

    def _set_layers(self, enabled: bool) -> None:
        for flag in self.flags.values():
            flag.set(enabled)
        self._update_layer_count()

    def _update_layer_count(self) -> None:
        count = sum(flag.get() for flag in self.flags.values())
        self.layer_count.configure(text=f"{count}/7 livelli", fg=self.C["accent2"] if count else self.C["danger"])

    def _clear(self) -> None:
        self.source.delete("1.0", "end")
        self.output.delete("1.0", "end")
        self.status.set("Editor puliti")
        self.source.focus_set()

    def _obfuscate(self) -> None:
        source = self.source.get("1.0", "end-1c")
        if not source.strip():
            self.status.set("Inserisci del codice Python")
            self.source.focus_set()
            return
        try:
            result = Obfuscator().obfuscate(source, self._options())
        except (SyntaxError, ValueError) as error:
            messagebox.showerror("Codice non valido", str(error), parent=self.root)
            self.status.set("Errore di sintassi nel sorgente")
            return
        self.output.delete("1.0", "end")
        self.output.insert("1.0", result)
        self.status.set(f"Protezione completata · {len(source):,} → {len(result):,} caratteri")

    def _open(self) -> None:
        selected = filedialog.askopenfilename(parent=self.root, filetypes=[("Python", "*.py"), ("Tutti i file", "*.*")])
        if not selected:
            return
        try:
            content = Path(selected).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            messagebox.showerror("Impossibile aprire", str(error), parent=self.root)
            return
        self.source.delete("1.0", "end")
        self.source.insert("1.0", content)
        self.status.set(f"Aperto · {Path(selected).name}")

    def _save(self) -> None:
        if not self.output.get("1.0", "end-1c").strip():
            self.status.set("Nessun output da salvare")
            return
        selected = filedialog.asksaveasfilename(parent=self.root, defaultextension=".py", initialfile="protected.py", filetypes=[("Python", "*.py")])
        if not selected:
            return
        try:
            Path(selected).write_text(self.output.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Impossibile salvare", str(error), parent=self.root)
            return
        self.status.set(f"Salvato · {Path(selected).name}")


def main() -> None:
    """Start the desktop application."""
    root = tk.Tk()
    SevenShieldApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
