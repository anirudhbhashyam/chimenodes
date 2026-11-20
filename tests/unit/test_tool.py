from tests.unit.conftest import load


def test_slider_mapping():
    tool, params = load("tool"), load("params")
    for name, _ in tool.SLIDERS:
        lo, hi = params.RANGES[name]
        assert tool.slider_to_value(name, 0) == lo
        assert abs(tool.slider_to_value(name, tool.STEPS) - hi) < 1e-9
        assert tool.value_to_slider(name, hi) == tool.STEPS
