from macq.extract import *
from tests.utils.test_model import test_model as TestModel


def test_model():
    model = TestModel()
    s = model.serialize("test_model.json")
    assert s
    d = Model.deserialize(s)
    assert d == model
    assert model != "model"

    with open("test_model.json", "r") as f:
        d = f.read()
        assert d == s
