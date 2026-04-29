"""Unit tests for KatanamlInvoicesDataset helpers that do not require the
HuggingFace dataset to be downloaded.

The full end-to-end download-and-iterate tests are in `test_katanaml.py`
and marked ``dataset_heavy``.
"""

import numpy as np
import pytest
from PIL import Image

from extraction_layer.data_sources.katanaml_invoices.loader import KatanamlInvoicesDataset
from extraction_layer.data_sources.types import Sample

# ----- _image_to_rgb_ndarray -----------------------------------------------


class TestImageToRGBNdarray:
    def test_pil_rgb(self):
        img = Image.new("RGB", (10, 5), color="red")
        arr = KatanamlInvoicesDataset._image_to_rgb_ndarray(img)
        assert arr.shape == (5, 10, 3)
        assert arr.dtype == np.uint8
        # red channel is 255, others 0
        assert arr[0, 0, 0] == 255

    def test_pil_rgba_converted_to_rgb(self):
        img = Image.new("RGBA", (4, 4), color=(10, 20, 30, 128))
        arr = KatanamlInvoicesDataset._image_to_rgb_ndarray(img)
        assert arr.shape == (4, 4, 3)
        assert arr.dtype == np.uint8

    def test_pil_grayscale_converted_to_rgb(self):
        img = Image.new("L", (4, 4), color=128)
        arr = KatanamlInvoicesDataset._image_to_rgb_ndarray(img)
        assert arr.shape == (4, 4, 3)
        assert arr.dtype == np.uint8

    def test_ndarray_rgb_passthrough(self):
        arr_in = np.full((8, 8, 3), 200, dtype=np.uint8)
        arr_out = KatanamlInvoicesDataset._image_to_rgb_ndarray(arr_in)
        assert arr_out.shape == (8, 8, 3)
        assert arr_out.dtype == np.uint8

    def test_ndarray_grayscale_stacked_to_rgb(self):
        arr_in = np.full((8, 8), 128, dtype=np.uint8)
        arr_out = KatanamlInvoicesDataset._image_to_rgb_ndarray(arr_in)
        assert arr_out.shape == (8, 8, 3)
        assert arr_out.dtype == np.uint8

    def test_ndarray_rgba_dropped_to_rgb(self):
        arr_in = np.full((8, 8, 4), 50, dtype=np.uint8)
        arr_out = KatanamlInvoicesDataset._image_to_rgb_ndarray(arr_in)
        assert arr_out.shape == (8, 8, 3)

    def test_rejects_unknown_type(self):
        with pytest.raises(TypeError):
            KatanamlInvoicesDataset._image_to_rgb_ndarray(object())


# ----- _parse_ground_truth -------------------------------------------------


class TestParseGroundTruth:
    def test_none_becomes_empty_dict(self):
        assert KatanamlInvoicesDataset._parse_ground_truth(None) == {}

    def test_dict_passthrough(self):
        raw = {"gt_parse": {"header": {"invoice_no": "123"}}}
        assert KatanamlInvoicesDataset._parse_ground_truth(raw) == raw

    def test_json_string_parsed(self):
        raw_str = '{"gt_parse": {"header": {"invoice_no": "INV-1"}, "items": []}}'
        parsed = KatanamlInvoicesDataset._parse_ground_truth(raw_str)
        assert parsed["gt_parse"]["header"]["invoice_no"] == "INV-1"

    def test_invalid_json_wrapped_in_raw(self):
        raw_str = "not-json"
        parsed = KatanamlInvoicesDataset._parse_ground_truth(raw_str)
        assert parsed == {"_raw": "not-json"}

    def test_bytes_decoded_and_parsed(self):
        raw_bytes = b'{"k": 1}'
        parsed = KatanamlInvoicesDataset._parse_ground_truth(raw_bytes)
        assert parsed == {"k": 1}

    def test_non_dict_json_wrapped(self):
        parsed = KatanamlInvoicesDataset._parse_ground_truth("[1, 2, 3]")
        assert parsed == {"_raw": [1, 2, 3]}


# ----- header_of / items_of accessors --------------------------------------


def _sample_with_gt(gt: dict) -> Sample:
    return Sample(
        id="test",
        image=np.full((4, 4, 3), 0, dtype=np.uint8),
        ground_truth=gt,
        split="test",
        source_dataset="katanaml-invoices-donut-v1",
    )


class TestAccessors:
    def test_header_from_gt_parse_wrapper(self):
        s = _sample_with_gt({"gt_parse": {"header": {"invoice_no": "X"}, "items": []}})
        assert KatanamlInvoicesDataset.header_of(s) == {"invoice_no": "X"}

    def test_header_from_bare_structure(self):
        s = _sample_with_gt({"header": {"invoice_no": "Y"}})
        assert KatanamlInvoicesDataset.header_of(s) == {"invoice_no": "Y"}

    def test_header_missing_returns_empty(self):
        s = _sample_with_gt({})
        assert KatanamlInvoicesDataset.header_of(s) == {}

    def test_items_from_gt_parse_wrapper(self):
        items = [{"desc": "Widget"}]
        s = _sample_with_gt({"gt_parse": {"header": {}, "items": items}})
        assert KatanamlInvoicesDataset.items_of(s) == items

    def test_items_from_bare_structure(self):
        items = [{"desc": "Gadget"}]
        s = _sample_with_gt({"items": items})
        assert KatanamlInvoicesDataset.items_of(s) == items

    def test_items_missing_returns_empty(self):
        s = _sample_with_gt({})
        assert KatanamlInvoicesDataset.items_of(s) == []
