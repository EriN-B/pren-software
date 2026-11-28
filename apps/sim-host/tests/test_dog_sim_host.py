import dog_sim_host


def test_import():
    assert dog_sim_host.__doc__


def test_voice_command_reaches_the_core_only_when_its_state_allows_it(tmp_path):
    import threading
    from types import SimpleNamespace

    import pytest
    from dog_sim_host.core_runner import CoreRunner

    sent = threading.Event()
    machine = SimpleNamespace(
        allowed_events=[SimpleNamespace(id="such")],
        command_recognition=SimpleNamespace(stop_event=threading.Event()),
        shared=SimpleNamespace(logger=SimpleNamespace(info=lambda *args: None)),
        send=lambda word: sent.set() if word == "such" else None,
    )
    core = CoreRunner(tmp_path / "port", webcam=None)
    core._machine = machine

    core.say("sitz")  # not allowed in this state: ignored, listening goes on
    assert not machine.command_recognition.stop_event.is_set()
    core.say("such")
    assert sent.wait(1) and machine.command_recognition.stop_event.is_set()
    with pytest.raises(ValueError):
        core.say("rm -rf")
