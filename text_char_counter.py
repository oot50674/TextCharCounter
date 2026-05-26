# -*- coding: utf-8 -*-
from __future__ import annotations

import traceback
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    DND_FILES = None
    TkBase = tk.Tk
else:
    TkBase = TkinterDnD.Tk


APP_TITLE = "텍스트 글자수 계산기"
COLUMN_LABELS = {
    "name": "파일명",
    "chars": "글자수",
    "encoding": "인코딩",
    "status": "상태",
    "path": "경로",
}
SUPPORTED_TEXT_HINTS = (
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".log",
    ".json",
    ".xml",
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
    ".conf",
    ".properties",
    ".sql",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".java",
    ".jsp",
)


@dataclass(frozen=True)
class FileResult:
    path: Path
    char_count: Optional[int]
    encoding: str
    status: str

    @property
    def is_success(self) -> bool:
        return self.char_count is not None


def format_number(value: Optional[int]) -> str:
    return "" if value is None else f"{value:,}"


def is_probably_text(text: str) -> bool:
    if not text:
        return True

    control_count = 0
    for char in text:
        if char in "\r\n\t":
            continue
        if unicodedata.category(char).startswith("C"):
            control_count += 1

    return control_count / max(len(text), 1) < 0.05


def decode_text_bytes(data: bytes) -> Tuple[str, str]:
    if not data:
        return "", "empty"

    bom_encodings = [
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ]
    for bom, encoding in bom_encodings:
        if data.startswith(bom):
            text = data.decode(encoding)
            return text, encoding

    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr", "utf-16", "utf-16-le", "utf-16-be"]
    last_error: Optional[Exception] = None
    for encoding in encodings:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

        if is_probably_text(text):
            return text, encoding

    if last_error:
        raise ValueError(f"텍스트 인코딩을 확인할 수 없습니다: {last_error}")
    raise ValueError("텍스트 파일로 보기 어려운 내용입니다.")


def analyze_file(path: Path) -> FileResult:
    try:
        data = path.read_bytes()
        text, encoding = decode_text_bytes(data)
        return FileResult(path=path, char_count=len(text), encoding=encoding, status="완료")
    except Exception as exc:
        return FileResult(path=path, char_count=None, encoding="", status=f"실패: {exc}")


def iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        path = Path(path)
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file():
                    yield child


class TextCharCounterApp(TkBase):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x620")
        self.minsize(820, 520)

        self.results: Dict[str, FileResult] = {}
        self.sort_column = "name"
        self.sort_reverse = False
        self.total_var = tk.StringVar(value="파일 0개 / 총 0자")
        self.status_var = tk.StringVar(value="파일을 추가하거나 창 안으로 드래그앤드롭하세요.")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        title = ttk.Label(root, text=APP_TITLE, font=("맑은 고딕", 17, "bold"))
        title.grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(root)
        table_frame.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("name", "chars", "encoding", "status", "path")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        for column in columns:
            self.tree.heading(
                column,
                text=COLUMN_LABELS[column],
                command=lambda selected_column=column: self.sort_by_column(selected_column),
            )
        self.tree.column("name", width=230, minwidth=160)
        self.tree.column("chars", width=110, minwidth=90, anchor="e")
        self.tree.column("encoding", width=110, minwidth=80)
        self.tree.column("status", width=230, minwidth=150)
        self.tree.column("path", width=360, minwidth=220)
        self.tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        toolbar = ttk.Frame(root)
        toolbar.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        toolbar.columnconfigure(6, weight=1)

        ttk.Button(toolbar, text="파일 추가", command=self.add_files_dialog).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="폴더 추가", command=self.add_folder_dialog).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Button(toolbar, text="선택 삭제", command=self.remove_selected).grid(row=0, column=2, sticky="w", padx=(16, 0))
        ttk.Button(toolbar, text="전체 삭제", command=self.clear_all).grid(row=0, column=3, sticky="w", padx=(8, 0))
        ttk.Button(toolbar, text="결과 복사", command=self.copy_summary).grid(row=0, column=4, sticky="w", padx=(16, 0))
        ttk.Label(toolbar, textvariable=self.total_var, font=("맑은 고딕", 10, "bold")).grid(row=0, column=6, sticky="e")

        status = ttk.Label(root, textvariable=self.status_var)
        status.grid(row=4, column=0, sticky="ew", pady=(10, 0))

        self.register_drop_target(self)
        self.register_drop_target(root)
        self.register_drop_target(table_frame)
        self.register_drop_target(self.tree)
        self.refresh_sort_headings()

    def register_drop_target(self, widget: tk.Widget) -> None:
        if DND_FILES is None:
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.handle_drop)
        except Exception:
            self.write_error_log(traceback.format_exc())
            self.status_var.set("드래그앤드롭 초기화에 실패했습니다. 파일 추가 버튼을 사용하세요.")

    def handle_drop(self, event: object) -> None:
        try:
            raw_data = getattr(event, "data", "")
            paths = [Path(item) for item in self.tk.splitlist(raw_data)]
            self.add_paths(paths)
        except Exception:
            self.write_error_log(traceback.format_exc())
            self.status_var.set("드래그앤드롭 처리 중 오류가 발생했습니다. 파일 추가 버튼으로 다시 시도하세요.")

    def write_error_log(self, detail: str) -> None:
        try:
            log_path = Path.home() / "TextCharCounter_drop_error.log"
            log_path.write_text(detail, encoding="utf-8")
        except Exception:
            pass

    def add_files_dialog(self) -> None:
        selected = filedialog.askopenfilenames(
            title="텍스트 파일 선택",
            filetypes=[
                ("텍스트/문서 파일", "*.txt *.md *.markdown *.csv *.log *.json *.xml *.yml *.yaml *.ini *.cfg *.conf *.properties *.sql *.py *.js *.ts *.html *.css *.java *.jsp"),
                ("모든 파일", "*.*"),
            ],
        )
        self.add_paths(Path(path) for path in selected)

    def add_folder_dialog(self) -> None:
        selected = filedialog.askdirectory(title="폴더 선택")
        if selected:
            self.add_paths([Path(selected)])

    def add_paths(self, paths: Iterable[Path]) -> None:
        files = list(iter_files(paths))
        added = 0
        skipped = 0

        for path in files:
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path.absolute())

            if key in self.results:
                skipped += 1
                continue

            result = analyze_file(path)
            self.results[key] = result
            self.tree.insert(
                "",
                tk.END,
                iid=key,
                values=(
                    result.path.name,
                    format_number(result.char_count),
                    result.encoding,
                    result.status,
                    str(result.path),
                ),
            )
            added += 1

        self.update_total()
        self.apply_sort()
        self.status_var.set(f"{added}개 추가, {skipped}개 중복 제외")

    def remove_selected(self) -> None:
        selected = self.tree.selection()
        for item_id in selected:
            self.results.pop(item_id, None)
            self.tree.delete(item_id)
        self.update_total()
        self.apply_sort()
        self.status_var.set(f"{len(selected)}개 항목 삭제")

    def clear_all(self) -> None:
        self.results.clear()
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        self.update_total()
        self.apply_sort()
        self.status_var.set("목록을 비웠습니다.")

    def copy_summary(self) -> None:
        lines = ["파일명\t글자수\t인코딩\t상태\t경로"]
        for item_id in self.tree.get_children():
            result = self.results[item_id]
            lines.append(
                "\t".join(
                    [
                        result.path.name,
                        format_number(result.char_count),
                        result.encoding,
                        result.status,
                        str(result.path),
                    ]
                )
            )
        success_count, total_chars = self.total_counts()
        lines.append(f"총계\t{total_chars:,}\t\t성공 파일 {success_count}개\t")

        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status_var.set("결과를 클립보드에 복사했습니다.")

    def total_counts(self) -> Tuple[int, int]:
        success_results = [result for result in self.results.values() if result.is_success]
        total_chars = sum(result.char_count or 0 for result in success_results)
        return len(success_results), total_chars

    def update_total(self) -> None:
        success_count, total_chars = self.total_counts()
        failed_count = len(self.results) - success_count
        failed_text = f" / 실패 {failed_count}개" if failed_count else ""
        self.total_var.set(f"파일 {success_count}개{failed_text} / 총 {total_chars:,}자")

    def sort_by_column(self, column: str) -> None:
        if column == self.sort_column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self.apply_sort()

    def sort_key(self, item_id: str, column: str) -> object:
        result = self.results[item_id]
        if column == "chars":
            return result.char_count or 0
        if column == "name":
            return result.path.name.casefold()
        if column == "encoding":
            return result.encoding.casefold()
        if column == "status":
            return result.status.casefold()
        if column == "path":
            return str(result.path).casefold()
        return result.path.name.casefold()

    def apply_sort(self) -> None:
        item_ids = list(self.tree.get_children())
        if self.sort_column == "chars":
            successful = [item_id for item_id in item_ids if self.results[item_id].char_count is not None]
            failed = [item_id for item_id in item_ids if self.results[item_id].char_count is None]
            successful.sort(key=lambda item_id: self.sort_key(item_id, "chars"), reverse=self.sort_reverse)
            ordered = successful + failed
        else:
            ordered = sorted(
                item_ids,
                key=lambda item_id: self.sort_key(item_id, self.sort_column),
                reverse=self.sort_reverse,
            )

        for index, item_id in enumerate(ordered):
            self.tree.move(item_id, "", index)
        self.refresh_sort_headings()

    def refresh_sort_headings(self) -> None:
        for column, label in COLUMN_LABELS.items():
            if column == self.sort_column:
                arrow = " ▼" if self.sort_reverse else " ▲"
                text = label + arrow
            else:
                text = label
            self.tree.heading(
                column,
                text=text,
                command=lambda selected_column=column: self.sort_by_column(selected_column),
            )

    def on_close(self) -> None:
        self.destroy()


def main() -> None:
    app = TextCharCounterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
