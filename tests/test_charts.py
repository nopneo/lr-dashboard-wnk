import charts


def test_stacked_bar_has_one_group_per_month_and_labels():
    months = [{"ym": "2026-10", "normal": 5, "complicated": 2, "referred": 1},
              {"ym": "2026-11", "normal": 0, "complicated": 0, "referred": 0}]
    svg = str(charts.stacked_bar(months))
    assert svg.startswith("<svg") and svg.count('class="bar-col"') == 2
    assert ">7<" in svg                         # ยอดรวมคลอด = ปกติ + แทรกซ้อน (ส่งต่อไม่รวม)
    assert "NaN" not in svg and "None" not in svg


def test_stacked_bar_all_zero_shows_dash_not_crash():
    svg = str(charts.stacked_bar([{"ym": "2026-10", "normal": 0, "complicated": 0, "referred": 0}]))
    assert "ไม่มีข้อมูล" in svg


def test_donut_percentages_and_empty():
    svg = str(charts.donut([("ปกติ", 3, "#1e88e5"), ("แทรกซ้อน", 1, "#f06292")]))
    assert "75%" in svg and "25%" in svg
    empty = str(charts.donut([("ปกติ", 0, "#1e88e5")]))
    assert "ไม่มีข้อมูล" in empty and "NaN" not in empty


def test_axis_ticks_are_whole_numbers():
    import re
    for peak in (1, 5, 12, 13, 37, 130):
        svg = str(charts.stacked_bar([{"ym": "2026-10", "normal": peak, "complicated": 0, "referred": 0}]))
        ticks = re.findall(r'class="axis">([\d.]+)<', svg)
        assert ticks and all(float(t) == int(float(t)) for t in ticks), (peak, ticks)
