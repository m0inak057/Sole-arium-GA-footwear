"""Face blurring for DPDP Act 2023 compliance.

Detects faces in each video frame using OpenCV's Haar cascade classifier
and applies Gaussian blur over each bounding box before writing the output
video.  No heavyweight model dependencies — uses the cascade XML bundled
with OpenCV.

Usage::

    from src.gait.privacy.face_blur import blur_all_session_videos

    results = blur_all_session_videos(
        {"anterior": "/tmp/ant.avi", "sagittal": "/tmp/sag.avi", "posterior": "/tmp/pos.avi"},
        output_dir="/tmp/blurred",
    )
    # results = {"anterior": True, "sagittal": False, "posterior": False}
    face_blur_applied = any(results.values())
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import cv2

from src.gait.common.logging_utils import get_logger

logger = get_logger(__name__)

# Cascade XML is installed alongside OpenCV; cv2.data.haarcascades gives the directory.
_CASCADE_PATH = os.path.join(
    cv2.data.haarcascades, "haarcascade_frontalface_default.xml"
)


def _load_cascade() -> cv2.CascadeClassifier:
    cascade = cv2.CascadeClassifier(_CASCADE_PATH)
    if cascade.empty():
        raise RuntimeError(
            f"Failed to load face cascade from {_CASCADE_PATH}. "
            "Ensure opencv-python (or opencv-contrib-python) is installed."
        )
    return cascade


def blur_faces_in_video(input_path: str, output_path: str) -> bool:
    """Detect and blur all faces in a video file.

    Opens the input video, runs Haar face detection on every frame, applies
    Gaussian blur (kernel 99×99, σ=30) over each detected bounding box, and
    writes the result to *output_path* at the same fps and resolution.

    Args:
        input_path:  Path to the source video (any format OpenCV can decode).
        output_path: Destination path for the blurred video (.avi, XVID codec).

    Returns:
        True  — at least one face was detected and blurred across the whole video.
        False — no faces were found in any frame (not an error; posterior/sagittal
                views typically do not show the face).

    Raises:
        FileNotFoundError: If *input_path* does not exist.
        RuntimeError:      If the video cannot be opened or the cascade is missing.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")

    cascade = _load_cascade()

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
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

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
            )

            if len(faces) > 0:
                any_face_found = True
                for x, y, w, h in faces:
                    roi = frame[y : y + h, x : x + w]
                    blurred_roi = cv2.GaussianBlur(roi, (99, 99), 30)
                    frame[y : y + h, x : x + w] = blurred_roi

            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()

    logger.info(
        "face_blur.complete",
        extra={
            "input_path": input_path,
            "output_path": output_path,
            "frames_processed": frame_idx,
            "face_detected": any_face_found,
        },
    )
    return any_face_found


def blur_all_session_videos(
    session_video_paths: Dict[str, str],
    output_dir: str,
) -> Dict[str, bool]:
    """Blur faces in all camera videos for one session.

    Args:
        session_video_paths: Mapping of camera name → input path.
                             Expected keys: "anterior", "sagittal", "posterior".
        output_dir:          Directory where blurred videos are written.
                             Each output is named ``<camera>_blurred.<ext>``.

    Returns:
        Dict mapping each camera name to whether at least one face was blurred.
        Cameras whose input file raises an error are logged and mapped to False.
    """
    results: Dict[str, bool] = {}
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    for camera, src_path in session_video_paths.items():
        suffix = Path(src_path).suffix or ".avi"
        dst_path = str(output_dir_path / f"{camera}_blurred{suffix}")
        try:
            face_found = blur_faces_in_video(src_path, dst_path)
            results[camera] = face_found
        except Exception as exc:
            logger.warning(
                "face_blur.camera_failed",
                extra={"camera": camera, "error": str(exc)},
            )
            results[camera] = False

    logger.info(
        "face_blur.session_complete",
        extra={"cameras": list(results.keys()), "any_blurred": any(results.values())},
    )
    return results
