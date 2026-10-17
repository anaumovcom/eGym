from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select

from app.api.routes.analytics import media_service
from app.models.analytics import ProgressPhoto
from app.services import photo_crop
from app.services.photo_crop import (
    PersonDetector,
    PhotoCropUnavailableError,
    crop_progress_photo,
    portrait_crop_box,
)


@pytest.mark.parametrize("size, person", [
    ((1280, 720), (530, 60, 750, 660)),
    ((1280, 720), (0, 0, 250, 720)),
    ((1280, 720), (1040, 10, 1280, 715)),
    ((720, 1280), (80, 20, 680, 1260)),
    ((1280, 720), (100, 210, 1180, 500)),  # wide stance / arms out
    ((100, 120), (0, 0, 100, 120)),
])
def test_portrait_crop_contains_entire_person_and_has_exact_aspect(size, person):
    left, top, right, bottom = portrait_crop_box(size, person)
    assert (right - left) * 4 == (bottom - top) * 3
    assert left <= person[0] and top <= person[1]
    assert right >= person[2] and bottom >= person[3]
    # No generated padding when an expanded portrait fits inside the source.
    if right - left <= size[0]:
        assert 0 <= left < right <= size[0]
    if bottom - top <= size[1]:
        assert 0 <= top < bottom <= size[1]


def test_portrait_crop_leaves_small_margin():
    box = portrait_crop_box((1600, 1200), (600, 200, 1000, 1000))
    assert box[1] <= 200 - 800 * 0.08
    assert box[3] >= 1000 + 800 * 0.08
    assert box[3] - box[1] <= 800 * 1.16 + 4


@pytest.mark.parametrize("person", [(0, 0, 0, 10), (0, 0, 10, -1), (0, 0, float('nan'), 10)])
def test_invalid_person_box_is_rejected(person):
    with pytest.raises(ValueError):
        portrait_crop_box((100, 100), person)


def test_crop_is_rgb_exact_portrait_capped_and_preserves_subject(monkeypatch):
    image = Image.new("RGBA", (3000, 2400), "white")
    # A solid subject lets us verify that no top/bottom pixels were lost.
    image.paste((220, 20, 30, 255), (1000, 200, 1700, 2200))
    monkeypatch.setattr(photo_crop, "detect_person", lambda *_: (1000, 200, 1700, 2200))
    result = crop_progress_photo(image, "unused")
    assert result.size == (900, 1200)
    assert result.mode == "RGB"
    red = (np.asarray(result)[:, :, 0] > 180) & (np.asarray(result)[:, :, 1] < 80)
    ys, xs = np.nonzero(red)
    assert xs.min() > 0 and xs.max() < 899
    assert 0 < ys.min() < 150 and 1050 < ys.max() < 1199


def test_exif_orientation_applied_before_detection(monkeypatch):
    image = Image.new("RGB", (160, 120), "white")
    image.getexif()[274] = 6
    seen = []

    def detect(oriented, _path):
        seen.append(oriented.size)
        return (20, 10, 100, 150)

    monkeypatch.setattr(photo_crop, "detect_person", detect)
    result = crop_progress_photo(image, "unused")
    assert seen == [(120, 160)]
    assert result.width * 4 == result.height * 3


def test_no_person_rejected_instead_of_arbitrary_center_crop(monkeypatch):
    monkeypatch.setattr(photo_crop, "detect_person", lambda *_: None)
    with pytest.raises(ValueError, match="Не удалось найти человека"):
        crop_progress_photo(Image.new("RGB", (1280, 720)), "unused")


@pytest.fixture()
def detector(tmp_path, monkeypatch):
    path = tmp_path / "test.onnx"
    path.touch()
    session = Mock()
    session.get_inputs.return_value = [SimpleNamespace(name="images")]
    constructor = Mock(return_value=session)
    monkeypatch.setattr(photo_crop.ort, "InferenceSession", constructor)
    detector = PersonDetector(str(path))
    return detector, session, constructor


def predictions_for(*boxes):
    predictions = np.zeros((8400, 85), dtype=np.float32)
    for index, (left, top, right, bottom, category) in enumerate(boxes):
        predictions[index, :4] = [
            (left + right) / 16 - index,
            (top + bottom) / 16,
            np.log((right - left) / 8),
            np.log((bottom - top) / 8),
        ]
        predictions[index, 4] = 0.95
        predictions[index, 5 + category] = 0.95
    return predictions


def test_inference_explicitly_uses_cpu_raw_rgb_and_letterbox(detector):
    instance, session, constructor = detector
    session.run.return_value = [np.zeros((1, 8400, 85), dtype=np.float32)]
    assert instance.detect(Image.new("RGB", (1280, 720), (10, 20, 30))) is None
    assert constructor.call_args.kwargs["providers"] == ["CPUExecutionProvider"]
    options = constructor.call_args.kwargs["sess_options"]
    assert options.intra_op_num_threads == 2
    tensor = session.run.call_args.args[1]["images"]
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32
    np.testing.assert_array_equal(tensor[0, :, 0, 0], [10, 20, 30])
    np.testing.assert_array_equal(tensor[0, :, 639, 639], [114, 114, 114])


def test_detector_chooses_foreground_person_not_bystander_or_other_object(detector):
    instance, _, _ = detector
    predictions = predictions_for(
        (200, 40, 400, 600, 0), (202, 41, 398, 599, 0),  # duplicate
        (10, 10, 80, 120, 0), (0, 0, 640, 640, 1),  # bystander, bicycle
    )
    predictions[0, 4] = 0.99
    box = instance._person_box(predictions, 0.5, (1280, 1280))
    assert box == pytest.approx((400, 80, 800, 1200), abs=0.01)


def test_missing_model_is_explicit_configuration_error(tmp_path):
    with pytest.raises(PhotoCropUnavailableError, match="не установлена"):
        PersonDetector(str(tmp_path / "missing.onnx"))


@pytest.fixture()
def photo_upload(tmp_path, monkeypatch):
    monkeypatch.setattr(media_service, "media_root", tmp_path)
    image = Image.new("RGB", (1280, 720), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return {
        "data": {"userId": "alexey", "mode": "manual", "view": "front"},
        "files": {"file": ("photo.png", buffer.getvalue(), "image/png")},
    }


def test_upload_persists_cropped_jpeg_thumbnail_and_matching_metadata(
    client, db_session, tmp_path, monkeypatch, photo_upload,
):
    monkeypatch.setattr(photo_crop, "detect_person", lambda *_: (530, 60, 750, 660))
    response = client.post("/api/photo-progress", **photo_upload)
    assert response.status_code == 200, response.text
    payload = response.json()
    record = db_session.get(ProgressPhoto, payload["id"])
    assert record.mime_type == "image/jpeg"
    path = tmp_path / record.storage_path
    thumb_path = tmp_path / record.thumbnail_path
    with Image.open(path) as saved, Image.open(thumb_path) as thumb:
        assert saved.format == thumb.format == "JPEG"
        assert saved.size == (record.width, record.height) == (payload["width"], payload["height"])
        assert saved.width * 4 == saved.height * 3
        assert thumb.size == (240, 320)
        assert not saved.getexif()
    assert record.file_size == path.stat().st_size


@pytest.mark.parametrize("failure, status, message", [
    (None, 400, "Не удалось найти человека"),
    (PhotoCropUnavailableError("Модель не установлена"), 503, "Модель не установлена"),
])
def test_detection_failure_does_not_store_uncropped_photo(
    client, db_session, tmp_path, monkeypatch, photo_upload, failure, status, message,
):
    def detect(*_):
        if failure:
            raise failure
        return None

    monkeypatch.setattr(photo_crop, "detect_person", detect)
    response = client.post("/api/photo-progress", **photo_upload)
    assert response.status_code == status
    assert message in response.json()["detail"]
    assert not list(tmp_path.rglob("*.jpg"))
    assert db_session.scalar(select(ProgressPhoto).where(ProgressPhoto.storage_path.like("%.jpg"))) is None


def test_corrupt_upload_returns_readable_error(client, photo_upload):
    photo_upload["files"] = {"file": ("photo.jpg", b"not an image", "image/jpeg")}
    response = client.post("/api/photo-progress", **photo_upload)
    assert response.status_code == 400
    assert "Не удалось прочитать" in response.json()["detail"]