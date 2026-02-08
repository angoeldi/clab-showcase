from haiku_example.domain import load_domain
from haiku_example.tutorial import load_tutorial


def test_load_domain():
    d = load_domain("configs/domain.yaml")
    assert d.model
    assert len(d.stages) >= 1


def test_load_tutorial():
    t = load_tutorial("configs/tutorial.yaml")
    assert t.enabled is True
    assert len(t.steps) >= 1
