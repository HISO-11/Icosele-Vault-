"""Task 4 — VM session recording and playback."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

import app.audit_log as audit
from app.ui.theme import (
    ACCENT, BG_CARD, BG_DEEP, BG_PANEL, BORDER, FONT_FAMILY,
    SECTION_LABEL_STYLE, STOP_RED, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, save_btn_style, subtle_btn_style,
)

log = logging.getLogger(__name__)

_REC_BASE = Path(__file__).resolve().parent.parent.parent / "data" / "recordings"
_FRAME_INTERVAL_MS = 500


def _rec_dir(vm_id: str, session_id: str) -> Path:
    return _REC_BASE / vm_id / session_id


class RecordingSession:
    def __init__(self, vm_id: str, vm_name: str):
        self.vm_id = vm_id
        self.vm_name = vm_name
        self.session_id = uuid.uuid4().hex[:10]
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.frame_count = 0
        self._frames_dir = _rec_dir(vm_id, self.session_id) / "frames"
        self._frames_dir.mkdir(parents=True, exist_ok=True)

    def save_frame(self, ppm_data: bytes) -> None:
        path = self._frames_dir / f"frame_{self.frame_count:06d}.ppm"
        path.write_bytes(ppm_data)
        self.frame_count += 1

    def finish(self) -> None:
        meta = {
            "vm_id": self.vm_id,
            "vm_name": self.vm_name,
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": datetime.now(timezone.utc).isoformat(),
            "frame_count": self.frame_count,
            "frame_interval_ms": _FRAME_INTERVAL_MS,
            "annotations": [],
        }
        meta_path = _rec_dir(self.vm_id, self.session_id) / "metadata.json"
        meta_path.write_text(json.dumps(meta, indent=2))


def list_recordings(vm_id: str) -> list[dict]:
    base = _REC_BASE / vm_id
    if not base.exists():
        return []
    recs = []
    for d in sorted(base.iterdir()):
        mp = d / "metadata.json"
        if mp.exists():
            try:
                recs.append(json.loads(mp.read_text()))
            except (json.JSONDecodeError, OSError):
                pass
    return recs


class RecordingPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_id = ""
        self._vm_name = ""
        self._session: RecordingSession | None = None
        self._qmp_fn = None
        self._rec_timer: QTimer | None = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"background-color: {BG_PANEL}; border: none;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 24, 0, 0)
        lay.setSpacing(12)

        lay.addWidget(QLabel("SESSION RECORDING", styleSheet=SECTION_LABEL_STYLE))
        desc = QLabel(
            "Record VM screen as a sequence of frames for playback and export.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        lay.addWidget(desc)

        # Record controls
        br = QHBoxLayout()
        br.setSpacing(8)
        self._btn_record = QPushButton("Start Recording")
        self._btn_record.setStyleSheet(save_btn_style())
        self._btn_record.setFixedHeight(32)
        self._btn_record.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_record.clicked.connect(self._toggle_record)
        br.addWidget(self._btn_record)
        br.addStretch()
        lay.addLayout(br)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        lay.addWidget(self._status)

        # Recordings list
        lay.addWidget(QLabel("RECORDINGS", styleSheet=SECTION_LABEL_STYLE))
        self._rec_list = QVBoxLayout()
        self._rec_list.setSpacing(4)
        lay.addLayout(self._rec_list)
        lay.addStretch()

    def set_vm(self, vm_id: str, vm_name: str):
        self._vm_id = vm_id
        self._vm_name = vm_name
        self._refresh_list()

    def set_qmp_provider(self, fn):
        self._qmp_fn = fn

    def _toggle_record(self):
        if self._session:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self._vm_id:
            return
        self._session = RecordingSession(self._vm_id, self._vm_name)
        self._btn_record.setText("Stop Recording")
        self._btn_record.setStyleSheet(
            f"QPushButton {{ background-color: {STOP_RED}; color: #fff;"
            f" border: none; border-radius: 6px; padding: 8px 16px;"
            f" font-size: 12px; font-weight: 600; font-family: {FONT_FAMILY}; }}")
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._capture_frame)
        self._rec_timer.start(_FRAME_INTERVAL_MS)
        self._status.setText("Recording...")
        audit.record("recording_started", self._vm_id, self._vm_name)

    def _stop_recording(self):
        if self._rec_timer:
            self._rec_timer.stop()
        if self._session:
            self._session.finish()
            self._status.setText(
                f"Saved: {self._session.frame_count} frames, session {self._session.session_id}")
            audit.record("recording_stopped", self._vm_id, self._vm_name,
                         {"frames": self._session.frame_count,
                          "session_id": self._session.session_id})
            self._session = None
        self._btn_record.setText("Start Recording")
        self._btn_record.setStyleSheet(save_btn_style())
        self._refresh_list()

    def _capture_frame(self):
        if not self._session or not self._qmp_fn:
            return
        qmp = self._qmp_fn(self._vm_id)
        if not qmp or not qmp.connected:
            return
        frame_path = f"/tmp/icosele-vm/{self._vm_id}/rec_frame.ppm"
        try:
            qmp.execute("screendump", {"filename": frame_path})
            data = Path(frame_path).read_bytes()
            self._session.save_frame(data)
            self._status.setText(f"Recording: frame {self._session.frame_count}")
        except Exception:
            pass

    def _refresh_list(self):
        while self._rec_list.count():
            w = self._rec_list.takeAt(0).widget()
            if w: w.deleteLater()
        recs = list_recordings(self._vm_id)
        if not recs:
            lbl = QLabel("No recordings yet.")
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")
            self._rec_list.addWidget(lbl)
            return
        for rec in reversed(recs[-10:]):
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 4px;")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(6)
            start = (rec.get("start_time") or "")[:19].replace("T", " ")
            frames = rec.get("frame_count", 0)
            sid = rec.get("session_id", "?")
            cl.addWidget(QLabel(f"{start}  |  {frames} frames  |  {sid}",
                                 styleSheet=f"color: {TEXT_PRIMARY}; font-size: 10px; background: transparent;"), 1)
            pb = QPushButton("Play")
            pb.setStyleSheet(subtle_btn_style())
            pb.setFixedSize(50, 22)
            pb.setCursor(Qt.CursorShape.PointingHandCursor)
            pb.clicked.connect(lambda ch, r=rec: self._play(r))
            cl.addWidget(pb)
            eb = QPushButton("Export")
            eb.setStyleSheet(subtle_btn_style())
            eb.setFixedSize(50, 22)
            eb.setCursor(Qt.CursorShape.PointingHandCursor)
            eb.clicked.connect(lambda ch, r=rec: self._export(r))
            cl.addWidget(eb)
            self._rec_list.addWidget(card)

    def _play(self, rec: dict):
        dlg = PlaybackDialog(rec, self._vm_id, self)
        dlg.exec()

    def _export(self, rec: dict):
        sid = rec.get("session_id", "")
        frames_dir = _rec_dir(self._vm_id, sid) / "frames"
        has_ffmpeg = shutil.which("ffmpeg") is not None
        if has_ffmpeg:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Video", f"recording_{sid}.mp4", "MP4 (*.mp4)")
            if not path:
                return
            try:
                subprocess.run([
                    "ffmpeg", "-y", "-framerate", "2",
                    "-pattern_type", "glob", "-i", str(frames_dir / "*.ppm"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
                ], check=True, capture_output=True, timeout=120)
                self._status.setText(f"Exported: {path}")
            except Exception as exc:
                self._status.setText(f"Export failed: {exc}")
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export Frames (ZIP)", f"recording_{sid}.zip", "ZIP (*.zip)")
            if not path:
                return
            import zipfile
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(frames_dir.iterdir()):
                    zf.write(f, f.name)
            self._status.setText(f"Exported frames ZIP: {path}")


class PlaybackDialog(QDialog):
    def __init__(self, rec: dict, vm_id: str, parent=None):
        super().__init__(parent)
        self._rec = rec
        self._vm_id = vm_id
        self._sid = rec.get("session_id", "")
        self._frames_dir = _rec_dir(vm_id, self._sid) / "frames"
        self._frame_files = sorted(self._frames_dir.iterdir()) if self._frames_dir.exists() else []
        self._total = len(self._frame_files)
        self._current = 0
        self._playing = False
        self._speed = 1.0
        self._interval = rec.get("frame_interval_ms", 500)
        self._meta_path = _rec_dir(vm_id, self._sid) / "metadata.json"
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle(f"Playback — {self._sid}")
        self.setFixedSize(640, 520)
        self.setStyleSheet(f"background-color: {BG_PANEL}; color: {TEXT_PRIMARY};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(8)

        # Frame display
        self._frame_label = QLabel()
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setStyleSheet(f"background: {BG_DEEP}; border-radius: 6px;")
        self._frame_label.setMinimumSize(600, 340)
        lay.addWidget(self._frame_label)

        # Frame counter
        self._counter = QLabel(f"Frame 0 / {self._total}")
        self._counter.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; background: transparent;")
        lay.addWidget(self._counter)

        # Scrubber
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, max(self._total - 1, 0))
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_scrub)
        lay.addWidget(self._slider)

        # Controls
        cr = QHBoxLayout()
        self._btn_play = QPushButton("Play")
        self._btn_play.setStyleSheet(save_btn_style())
        self._btn_play.setFixedHeight(28)
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.clicked.connect(self._toggle_play)
        cr.addWidget(self._btn_play)
        for sp, label in [(0.5, "0.5x"), (1.0, "1x"), (2.0, "2x"), (4.0, "4x")]:
            b = QPushButton(label)
            b.setStyleSheet(subtle_btn_style())
            b.setFixedSize(40, 24)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda ch, s=sp: self._set_speed(s))
            cr.addWidget(b)
        self._btn_annotate = QPushButton("Add Note")
        self._btn_annotate.setStyleSheet(subtle_btn_style())
        self._btn_annotate.setFixedHeight(24)
        self._btn_annotate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_annotate.clicked.connect(self._add_annotation)
        cr.addWidget(self._btn_annotate)
        cr.addStretch()
        lay.addLayout(cr)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        if self._total > 0:
            self._show_frame(0)

    def _show_frame(self, idx: int):
        if 0 <= idx < self._total:
            pix = QPixmap(str(self._frame_files[idx]))
            if not pix.isNull():
                self._frame_label.setPixmap(pix.scaled(
                    600, 340, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            self._counter.setText(f"Frame {idx + 1} / {self._total}")
            self._current = idx

    def _on_scrub(self, val):
        self._show_frame(val)

    def _toggle_play(self):
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._btn_play.setText("Play")
        else:
            interval = int(self._interval / self._speed)
            self._timer.start(max(interval, 16))
            self._playing = True
            self._btn_play.setText("Pause")

    def _next_frame(self):
        nxt = self._current + 1
        if nxt >= self._total:
            self._timer.stop()
            self._playing = False
            self._btn_play.setText("Play")
            return
        self._slider.setValue(nxt)

    def _set_speed(self, speed: float):
        self._speed = speed
        if self._playing:
            self._timer.setInterval(max(int(self._interval / speed), 16))

    def _add_annotation(self):
        text, ok = QInputDialog.getText(self, "Add Annotation", "Note:")
        if ok and text:
            try:
                meta = json.loads(self._meta_path.read_text())
                annotations = meta.get("annotations", [])
                annotations.append({"frame": self._current, "text": text.strip()})
                meta["annotations"] = annotations
                self._meta_path.write_text(json.dumps(meta, indent=2))
            except (json.JSONDecodeError, OSError):
                pass
