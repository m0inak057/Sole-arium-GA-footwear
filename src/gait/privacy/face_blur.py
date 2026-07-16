"""Face blurring for DPDP Act 2023 compliance.

Detects faces in each video frame and applies Gaussian blur over each
bounding box before writing the output video.

Primary detector: OpenCV's Haar cascade classifier (no heavyweight model
dependency). Some OpenCV wheels (notably opencv-python-headless, commonly
used in server/Docker builds) ship `cv2.data.haarcascades` as an existing
but *empty* directory â€” the XML files are simply not bundled. When the
cascade genuinely cannot be loaded from any known location, this module
falls back to MediaPipe's Tasks API face detector (BlazeFace short-range),
whose model file is auto-downloaded the same way the pose landmarker model
is.

Usage::

    from gait.privacy.face_blur import blur_all_session_videos

    results = blur_all_session_videos(
        {"anterior": "/tmp/ant.avi", "sagittal": "/tmp/sag.avi", "posterior": "/tmp/pos.avi"},
        output_dir="/tmp/blurred",
    )
    # results = {"anterior": True, "sagittal": False, "posterior": False}
    face_blur_applied = any(results.values())
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

from gait.common.logging_utils import get_logger

logger = get_logger(__name__)

# â”€â”€ Haar cascade location â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_CASCADE_FILENAME = "haarcascade_frontalface_default.xml"

# Fallback search directories, tried in order, for OpenCV builds/installs
# where cv2.data.haarcascades doesn't resolve or is empty (e.g. some
# opencv-python-headless wheels, or system packages installed separately).
_CASCADE_FALLBACK_DIRS = [
    "/usr/share/opencv4/haarcascades/",
    "/usr/local/share/opencv4/haarcascades/",
    "/usr/share/opencv/haarcascades/",
]

# â”€â”€ MediaPipe face-detector fallback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_MEDIAPIPE_FACE_MODEL_PATH = "data/models/face_detection_short_range.tflite"
_MEDIAPIPE_FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)


def _find_cascade_path() -> Optional[str]:
    """Search all known locations for the Haar cascade XML, in priority order.

    Returns the first existing path, or None if it isn't found anywhere.
    """
    candidates: List[str] = []
    try:
        candidates.append(os.path.join(cv2.data.haarcascades, _CASCADE_FILENAME))
    except AttributeError:
        pass  # older/unusual OpenCV builds may not expose cv2.data at all
    candidates.extend(os.path.join(d, _CASCADE_FILENAME) for d in _CASCADE_FALLBACK_DIRS)

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_cascade() -> cv2.CascadeClassifier:
    """Load the Haar cascade classifier, searching all known locations.

    Raises RuntimeError if the cascade cannot be found/loaded anywhere.
    """
    path = _find_cascade_path()
    if path is None:
        raise RuntimeError(
            f"Haar cascade '{_CASCADE_FILENAME}' not found in cv2.data.haarcascades "
            f"or any fallback directory ({_CASCADE_FALLBACK_DIRS}). "
            "Install the 'opencv-data' system package, or a MediaPipe-based "
            "fallback will be used instead if available."
        )
    cascade = cv2.CascadeClassifier(path)
    if cascade.empty():
        raise RuntimeError(f"Failed to load face cascade from {path} (file present but invalid).")
    return cascade


def _download_mediapipe_face_model(model_path: Path) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "face_blur.mediapipe_model_downloading",
        extra={"model_url": _MEDIAPIPE_FACE_MODEL_URL, "destination": str(model_path)},
    )
    try:
        urllib.request.urlretrieve(_MEDIAPIPE_FACE_MODEL_URL, model_path)
        logger.info(
            "face_blur.mediapipe_model_downloaded",
            extra={"path": str(model_path), "size_bytes": model_path.stat().st_size},
        )
    except Exception as exc:
        logger.error("face_blur.mediapipe_model_download_failed", extra={"error": str(exc)})
        raise


def _create_mediapipe_face_detector() -> Any:
    """Build a MediaPipe Tasks FaceDetector (BlazeFace short-range), downloading
    the model file first if it isn't already present on disk.
    """
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision

    model_path = Path(_MEDIAPIPE_FACE_MODEL_PATH)
    if not model_path.exists():
        _download_mediapipe_face_model(model_path)

    options = mp_vision.FaceDetectorOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=str(model_path)),
        running_mode=mp_vision.RunningMode.IMAGE,
    )
    return mp_vision.FaceDetector.create_from_options(options)


class _FaceDetectorBackend:
    """Detects face bounding boxes using whichever backend is actually available.

    Tries the Haar cascade first (cheap, no model download); falls back to
    MediaPipe's Tasks API face detector if the cascade can't be loaded for
    any reason. `self.method` is one of "haar_cascade", "mediapipe", or None
    (no working detector at all â€” callers should treat this as a hard failure,
    same as the previous behaviour when the cascade was missing).
    """

    def __init__(self) -> None:
        self.method: Optional[str] = None
        self._cascade: Optional[cv2.CascadeClassifier] = None
        self._mp_detector: Any = None
        self._mp_image_cls: Any = None
        self._mp_image_format: Any = None

        try:
            self._cascade = _load_cascade()
            self.method = "haar_cascade"
            return
        except Exception as exc:
            logger.warning("face_blur.cascade_unavailable", extra={"error": str(exc)})

        try:
            import mediapipe as mp

            self._mp_detector = _create_mediapipe_face_detector()
            self._mp_image_cls = mp.Image
            self._mp_image_format = mp.ImageFormat
            self.method = "mediapipe"
        except Exception as exc:
            logger.error("face_blur.mediapipe_fallback_failed", extra={"error": str(exc)})

    def detect(self, frame_bgr) -> List[Tuple[int, int, int, int]]:
        """Return a list of (x, y, w, h) face bounding boxes in pixel space."""
        if self.method == "haar_cascade":
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            faces = self._cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
            )
            return [(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]

        if self.method == "mediapipe":
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = self._mp_image_cls(image_format=self._mp_image_format.SRGB, data=rgb)
            result = self._mp_detector.detect(mp_image)
            boxes = []
            for detection in result.detections:
                bb = detection.bounding_box
                boxes.append((bb.origin_x, bb.origin_y, bb.width, bb.height))
            return boxes

        return []


def blur_faces_in_video(input_path: str, output_path: str) -> bool:
    """Detect and blur all faces in a video file.

    Opens the input video, runs face detection on every frame (Haar cascade,
    falling back to MediaPipe if the cascade is unavailable), applies
    Gaussian blur (kernel 99x99, sigma=30) over each detected bounding box,
    and writes the result to *output_path* at the same fps and resolution.
    Frames with no detected face pass through unmodified (still written).

    Args:
        input_path:  Path to the source video (any format OpenCV can decode).
        output_path: Destination path for the blurred video (.avi, XVID codec).

    Returns:
        True  - at least one face was detected and blurred across the whole video.
        False - no faces were found in any frame (not an error; posterior/sagittal
                views typically do not show the face).

    Raises:
        FileNotFoundError: If *input_path* does not exist.
        RuntimeError:      If the video cannot be opened or no face detector
                            (neither Haar cascade nor MediaPipe) is available.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    backend = _FaceDetectorBackend()
    if backend.method is None:
        raise RuntimeError(
            "No face detector available: Haar cascade could not be loaded and "
            "the MediaPipe fallback also failed. See preceding log entries."
        )

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    # Round to a whole number: some source videos report a high-precision fps
    # (e.g. 119.9410609...) whose derived FFmpeg timebase denominator can
    # exceed mpeg4/XVID's 65535 limit ("timebase not supported by MPEG 4
    # standard"), silently failing VideoWriter.isOpened(). A whole-number fps
    # keeps the timebase small and has no perceptible effect on playback speed.
    raw_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    fps = round(raw_fps) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot open output writer for: {output_path}")

    any_face_found = False
    frame_idx = 0
    frames_with_faces = 0
    total_faces_detected = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            faces = backend.detect(frame)

            if len(faces) > 0:
                any_face_found = True
                frames_with_faces += 1
                total_faces_detected += len(faces)
                for x, y, w, h in faces:
                    roi = frame[y : y + h, x : x + w]
                    if roi.size == 0:
                        continue
                    blurred_roi = cv2.GaussianBlur(roi, (99, 99), 30)
                    frame[y : y + h, x : x + w] = blurred_roi

            # Frame is always written, whether or not a face was found â€”
            # face-blurring must never drop frames from the output video.
            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()

    logger.info(
        "face_blur_applied",
        extra={
            "input_path": input_path,
            "output_path": output_path,
            "detector_method": backend.method,
            "frames_processed": frame_idx,
            "frames_with_faces": frames_with_faces,
            "total_faces_detected": total_faces_detected,
            "face_detected": any_face_found,
        },
    )
    return any_face_found


def _blur_one_camera(
    camera: str, src_path: str, output_dir_path: Path
) -> Tuple[bool, bool, Optional[str]]:
    """Run blur_faces_in_video for one camera.

    Returns (success, face_found, error_message). success=False only when
    processing itself raised (missing file, unreadable video, no detector
    available at all) â€” independent of whether a face happened to be found.
    """
    # blur_faces_in_video always writes with the XVID fourcc, which requires
    # an .avi container â€” OpenCV's mp4 muxer rejects XVID and VideoWriter
    # silently fails to open, which previously went unnoticed because every
    # camera failed earlier at cascade-loading regardless of output suffix.
    # Always write .avi here to match the codec actually used, irrespective
    # of the source video's container.
    dst_path = str(output_dir_path / f"{camera}_blurred.avi")
    try:
        face_found = blur_faces_in_video(src_path, dst_path)
        return True, face_found, None
    except Exception as exc:
        logger.warning("face_blur.camera_failed", extra={"camera": camera, "error": str(exc)})
        return False, False, str(exc)


def blur_all_session_videos(
    session_video_paths: Dict[str, str],
    output_dir: str,
) -> Dict[str, bool]:
    """Blur faces in all camera videos for one session.

    Args:
        session_video_paths: Mapping of camera name -> input path.
                             Expected keys: "anterior", "sagittal", "posterior".
        output_dir:          Directory where blurred videos are written.
                             Each output is named ``<camera>_blurred.<ext>``.

    Returns:
        Dict mapping each camera name to whether at least one face was blurred.
        Cameras whose input file raises an error are logged and mapped to False.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    results: Dict[str, bool] = {}
    for camera, src_path in session_video_paths.items():
        _, face_found, _ = _blur_one_camera(camera, src_path, output_dir_path)
        results[camera] = face_found

    logger.info(
        "face_blur.session_complete",
        extra={"cameras": list(results.keys()), "any_blurred": any(results.values())},
    )
    return results


def blur_all_session_videos_detailed(
    session_video_paths: Dict[str, str],
    output_dir: str,
) -> Dict[str, Dict[str, Any]]:
    """Like blur_all_session_videos, but separates "processing succeeded" from
    "a face happened to be found" â€” a camera that ran cleanly but simply
    didn't show a face (e.g. sagittal/posterior views) is not the same as a
    camera whose processing crashed, and callers that need to distinguish a
    genuinely broken pipeline from "no face in this angle" should use this.

    Returns:
        {camera: {"success": bool, "face_found": bool, "error": Optional[str]}}
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Dict[str, Any]] = {}
    for camera, src_path in session_video_paths.items():
        success, face_found, error = _blur_one_camera(camera, src_path, output_dir_path)
        results[camera] = {"success": success, "face_found": face_found, "error": error}

    logger.info(
        "face_blur.session_complete",
        extra={
            "cameras": list(results.keys()),
            "any_succeeded": any(r["success"] for r in results.values()),
            "any_blurred": any(r["face_found"] for r in results.values()),
        },
    )
    return results
