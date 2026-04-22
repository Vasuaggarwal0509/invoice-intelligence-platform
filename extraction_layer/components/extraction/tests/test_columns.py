"""Tests for column detection (seller / client separation)."""

from extraction_layer.components.extraction.heuristic.columns import detect_columns

from ._fixtures import sample00_like_ocr, sample04_like_ocr


def test_detects_seller_anchor():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    assert cols.seller_anchor_y == 250


def test_detects_client_anchor():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    assert cols.client_anchor_y == 250


def test_detects_items_boundary():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    assert cols.items_start_y == 600


def test_split_x_between_seller_and_client_centers():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    # Seller center x = (100+200)/2 = 150; Client center x = (450+550)/2 = 500.
    # Split = (150 + 500) / 2 = 325.
    assert cols.split_x == 325.0


def test_left_column_contains_seller_block():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    left_texts = [ocr.lines[i].text for i in cols.left_indices]
    # Seller block: name + address lines + tax id + iban. Anchor "Seller:" is excluded.
    assert "Bradley-Andrade" in left_texts
    assert "9879 Elizabeth Common" in left_texts
    assert "Lake Jonathan, RI 12335" in left_texts
    assert "Taxld:985-73-8194" in left_texts
    assert "IBAN:GB81LZWO32519172531418" in left_texts


def test_right_column_contains_client_block():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    right_texts = [ocr.lines[i].text for i in cols.right_indices]
    assert "Castro PLC" in right_texts
    assert "Unit 9678 Box 9664" in right_texts
    assert "DPO AP 69387" in right_texts
    assert "Taxld:994-72-1270" in right_texts


def test_columns_do_not_overlap():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    assert set(cols.left_indices).isdisjoint(set(cols.right_indices))


def test_items_line_is_not_in_either_column():
    ocr = sample00_like_ocr()
    cols = detect_columns(ocr)
    items_idx = next(i for i, line in enumerate(ocr.lines) if line.text == "ITEMS")
    assert items_idx not in cols.left_indices
    assert items_idx not in cols.right_indices


def test_sample04_like_column_split():
    """Second layout must also detect its columns correctly."""
    ocr = sample04_like_ocr()
    cols = detect_columns(ocr)
    assert cols.seller_anchor_y == 250
    assert cols.client_anchor_y == 250
    assert cols.items_start_y == 600
    left_texts = [ocr.lines[i].text for i in cols.left_indices]
    right_texts = [ocr.lines[i].text for i in cols.right_indices]
    assert "Smith-Cook" in left_texts
    assert "Snyder-Johnson" in right_texts
