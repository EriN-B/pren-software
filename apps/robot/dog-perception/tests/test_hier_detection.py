"""Verify the shared model is reused and mode-specific classes stay isolated."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

NAMES = {
    0: "bone",
    1: "dog bone",
    2: "dog chew bone",
    3: "chew toy",
    4: "person",
    5: "shoe",
}


class Boxes(list):
    def __getitem__(self, index):
        if isinstance(index, list):
            return Boxes(super(Boxes, self).__getitem__(i) for i in index)
        return super().__getitem__(index)


def box(class_id, confidence):
    return SimpleNamespace(
        cls=SimpleNamespace(item=lambda: class_id),
        conf=SimpleNamespace(item=lambda: confidence),
    )


@pytest.fixture
def object_model_module():
    source = Path(__file__).resolve().parents[1] / "src/dog_perception/object_model.py"
    spec = importlib.util.spec_from_file_location("_shared_object_model_test", source)
    module = importlib.util.module_from_spec(spec)
    factory = Mock()
    factory.return_value.names = dict(NAMES)
    factory.return_value.predict.side_effect = lambda **kwargs: [
        SimpleNamespace(names=dict(NAMES), boxes=None)
    ]
    with patch.dict(
        "sys.modules",
        {
            "numpy": SimpleNamespace(ndarray=object),
            "ultralytics": SimpleNamespace(YOLO=factory),
        },
    ):
        spec.loader.exec_module(module)
    return module, factory


def test_one_detection_model_is_reused_when_switching_between_modes(
    object_model_module,
):
    module, factory = object_model_module
    model = module.ObjectModel()
    frame = object()
    model.get_objects(frame)
    result = model.get_people_and_shoes(frame)
    model.get_objects(frame)
    factory.assert_called_once()
    assert factory.call_args.kwargs == {"task": "detect"}
    assert factory.call_args.args[0].endswith("dog-yoloe26n-detect-384x512_ncnn_model")
    assert [
        call.kwargs["classes"] for call in factory.return_value.predict.call_args_list
    ] == [
        [0, 1, 2, 3],
        [4, 5],
        [0, 1, 2, 3],
    ]
    assert all(
        call.kwargs["source"] is frame
        for call in factory.return_value.predict.call_args_list
    )
    assert result.names == {4: "person", 5: "shoe"}
    assert factory.return_value.names == NAMES


def test_search_returns_only_confident_bones_even_if_backend_returns_other_classes(
    object_model_module,
):
    module, factory = object_model_module
    accepted = box(0, 0.30)
    result = SimpleNamespace(
        names=dict(NAMES),
        boxes=Boxes(
            [
                accepted,
                box(3, 0.29),
                box(4, 0.99),
                box(5, 0.99),
            ]
        ),
    )
    factory.return_value.predict.side_effect = None
    factory.return_value.predict.return_value = [result]
    model = module.ObjectModel()
    assert model.get_objects(object()).boxes == [accepted]
    assert factory.return_value.predict.call_args.kwargs["classes"] == [0, 1, 2, 3]


def test_hier_returns_people_and_shoes_with_separate_confidence_thresholds(
    object_model_module,
):
    module, factory = object_model_module
    person, shoe = box(4, 0.40), box(5, 0.20)
    result = SimpleNamespace(
        names=dict(NAMES),
        boxes=Boxes(
            [
                person,
                box(4, 0.39),
                shoe,
                box(5, 0.19),
                box(0, 0.99),
            ]
        ),
    )
    factory.return_value.predict.side_effect = None
    factory.return_value.predict.return_value = [result]
    model = module.ObjectModel()
    assert model.get_people_and_shoes(object()).boxes == [person, shoe]
    assert factory.return_value.predict.call_args.kwargs["classes"] == [4, 5]
    assert result.names == {4: "person", 5: "shoe"}


@pytest.mark.parametrize(
    "names",
    [
        {0: "bone"},
        {0: "person", 1: "shoe"},
        {0: "bone", 1: "person"},
        {0: "bone", 1: "shoe"},
    ],
)
def test_incomplete_exports_are_rejected_before_robot_moves(object_model_module, names):
    module, factory = object_model_module
    factory.return_value.names = names
    with pytest.raises(ValueError, match="bone, person and shoe"):
        module.ObjectModel()
    factory.return_value.predict.assert_not_called()


def test_custom_export_class_ids_are_resolved_from_labels(
    object_model_module, tmp_path
):
    module, factory = object_model_module
    factory.return_value.names = {8: "shoe", 22: "bone", 41: "person"}
    export = tmp_path / "shared_ncnn_model"
    model = module.ObjectModel(model_path=export)
    model.get_objects(object())
    model.get_people_and_shoes(object())
    factory.assert_called_once_with(str(export), task="detect")
    assert [
        call.kwargs["classes"] for call in factory.return_value.predict.call_args_list
    ] == [[22], [8, 41]]
