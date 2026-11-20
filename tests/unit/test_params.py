import pytest
from tests.unit.conftest import load


def test_clamp_and_update():
    P = load("params").Params
    p = P().update(glow=99, exposure=-99, ao_radius=0.0)
    assert p.glow == 5.0 and p.exposure == -5.0 and p.ao_radius == 0.01


def test_bad_enums():
    P = load("params").Params
    with pytest.raises(ValueError):
        P().update(tonemap="reinhard")
    with pytest.raises(ValueError):
        P().update(quality="ultra")
    with pytest.raises(KeyError):
        P().update(nope=1)


def test_roundtrip_and_unknown_keys():
    P = load("params").Params
    p = P(enabled=True, glow=2.0, tonemap="agx")
    q = P.from_dict(dict(p.to_dict(), bogus=3))
    assert q == p


def test_post_effect():
    P = load("params").Params
    assert not P().any_post_effect()
    assert not P(glow=1.0).any_post_effect()  # disabled
    assert P(enabled=True, glow=1.0).any_post_effect()
    assert not P(enabled=True).any_post_effect()
