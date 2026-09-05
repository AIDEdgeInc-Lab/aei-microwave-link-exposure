"""The ArcGIS servers behind both real infrastructure sources report when
they've truncated results (``exceededTransferLimit``). Losing that signal
would let a partial result set look complete -- this is the regression
test for the fix. Uses a mocked ``requests.get``; no live network."""

from unittest.mock import MagicMock, patch

from aei_mw_exposure.infrastructure._arcgis import query_arcgis_layer
from aei_mw_exposure.infrastructure.ised import load_sites_in_bbox
from aei_mw_exposure.infrastructure.ontario_geohub import load_towers_in_bbox


def _fake_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_query_arcgis_layer_propagates_truncation_flag():
    payload = {"features": [{"attributes": {"OBJECTID": 1}, "geometry": {"x": 0, "y": 0}}], "exceededTransferLimit": True}
    with patch("requests.get", return_value=_fake_response(payload)) as mock_get:
        result = query_arcgis_layer("https://example.invalid/query", bbox=(-1, -1, 1, 1))
    assert result.exceeded_transfer_limit is True
    assert len(result.features) == 1
    mock_get.assert_called_once()


def test_query_arcgis_layer_defaults_to_false_when_absent():
    payload = {"features": []}  # some layers omit the key entirely when not truncated
    with patch("requests.get", return_value=_fake_response(payload)):
        result = query_arcgis_layer("https://example.invalid/query", bbox=(-1, -1, 1, 1))
    assert result.exceeded_transfer_limit is False


def test_query_arcgis_layer_raises_on_server_error_payload():
    payload = {"error": {"code": 400, "message": "bad request"}}
    with patch("requests.get", return_value=_fake_response(payload)):
        try:
            query_arcgis_layer("https://example.invalid/query", bbox=(-1, -1, 1, 1))
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "bad request" in str(exc)


def test_geohub_load_in_bbox_surfaces_truncation_flag_to_caller():
    payload = {
        "features": [{"attributes": {"CLASS_SUBTYPE": "Communication Tower", "OBJECTID": 1}, "geometry": {"x": -79.0, "y": 44.0}}],
        "exceededTransferLimit": True,
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        sites, skipped, exceeded = load_towers_in_bbox(bbox=(-80, 43, -79, 44))
    assert len(sites) == 1
    assert exceeded is True


def test_ised_load_in_bbox_surfaces_truncation_flag_to_caller():
    payload = {
        "features": [{"attributes": {"LICENSEE": "X", "OBJECTID": 1}, "geometry": {"x": -79.0, "y": 44.0}}],
        "exceededTransferLimit": True,
    }
    with patch("requests.get", return_value=_fake_response(payload)):
        sites, skipped, exceeded = load_sites_in_bbox(bbox=(-80, 43, -79, 44))
    assert len(sites) == 1
    assert exceeded is True
