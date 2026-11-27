import ast
import inspect
import os
import re
import sys
import xml.etree.ElementTree as tree
from collections import Counter
from itertools import pairwise
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def on_state_border(point, center):
    distance_x = abs(point[0] - center[0])
    distance_y = abs(point[1] - center[1])
    return (
        distance_x <= 140.1
        and distance_y <= 56.1
        and (abs(distance_x - 140) < 0.1 or abs(distance_y - 56) < 0.1)
    )


def source_model(machine):
    module = ast.parse(Path(inspect.getfile(machine)).read_text(encoding="utf-8"))
    definition = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == machine.__name__
    )
    states = set()
    initials = set()
    transitions = Counter()
    callbacks = set()
    for member in definition.body:
        if isinstance(member, ast.FunctionDef):
            callbacks.add(member.name)
        if not isinstance(member, ast.Assign) or len(member.targets) != 1:
            continue
        attribute = member.targets[0]
        if not isinstance(attribute, ast.Name):
            continue
        value = member.value
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "State"
        ):
            states.add(attribute.id)
            if any(
                keyword.arg == "initial"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in value.keywords
            ):
                initials.add(attribute.id)
            continue
        event_id = attribute.id
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "Event"
        ):
            event_id = next(
                (
                    keyword.value.value
                    for keyword in value.keywords
                    if keyword.arg == "id"
                ),
                event_id,
            )
        for call in ast.walk(value):
            if (
                not isinstance(call, ast.Call)
                or not isinstance(call.func, ast.Attribute)
                or call.func.attr != "to"
            ):
                continue
            require(
                isinstance(call.func.value, ast.Name)
                and len(call.args) == 1
                and isinstance(call.args[0], ast.Name)
                and not call.keywords,
                "Neue Transitionssyntax muss im unabhängigen Abgleich ergänzt werden.",
            )
            transitions[(call.func.value.id, call.args[0].id, event_id)] += 1
    actions = {
        (state_id, keyword, f"{prefix}_{state_id}")
        for state_id in states
        for keyword, prefix in (("entry", "on_enter"), ("exit", "on_exit"))
        if f"{prefix}_{state_id}" in callbacks
    }
    return states, initials, transitions, actions


def check(machine, output_directory):
    from generate_state_graph import POSITIONS, ROUTES, STATE_DETAILS, create_graph
    from generate_uml_state_graph import create_source
    from statemachine.contrib.diagram import extract

    states, initials, expected, expected_actions = source_model(machine)
    live = Counter(
        (state.id, transition.target.id, event.id)
        for state in machine.states
        for transition in state.transitions
        for event in transition.events
    )
    require(
        live == expected, "Python-Quelltext und Framework-Übergänge unterscheiden sich."
    )
    require(
        states == {state.id for state in machine.states},
        "Zustandsmengen unterscheiden sich.",
    )
    require(
        initials == {state.id for state in machine.states if state.initial},
        "Initialzustand unterscheidet sich.",
    )
    require(
        not any(state.final for state in machine.states),
        "Neuer Endzustand muss in beiden Darstellungen berücksichtigt werden.",
    )
    require(
        not any(state.states for state in machine.states),
        "Neue zusammengesetzte Zustände müssen im Abgleich ergänzt werden.",
    )
    registered_actions = {
        (state.id, action.type.name.lower(), callback)
        for state in extract(machine).states
        for action in state.actions
        for callback in action.body.split(", ")
    }
    require(
        registered_actions == expected_actions,
        "Registrierte Callbacks unterscheiden sich von den dokumentierten Methoden.",
    )

    source = create_source(machine)
    stored_source = (output_directory / "state_machine_uml.puml").read_text(
        encoding="utf-8"
    )
    require(
        source == stored_source,
        "PlantUML-Quelle ist veraltet. UML-Generator erneut ausführen.",
    )
    uml_transitions = Counter(
        re.findall(r"^([a-z_]+) --> ([a-z_]+) : ([a-z_]+)$", source, re.MULTILINE)
    )
    require(
        uml_transitions == expected,
        "UML-Übergänge unterscheiden sich vom Python-Quelltext.",
    )
    require(
        set(re.findall(r"^\[\*\] --> ([a-z_]+)$", source, re.MULTILINE)) == initials,
        "UML-Initialübergang unterscheidet sich.",
    )
    require(
        "--> [*]" not in source, "UML enthält einen nicht implementierten Endzustand."
    )
    uml_actions = set(
        re.findall(r"^([a-z_]+) : (entry|exit) / ([a-z_]+)\(\)$", source, re.MULTILINE)
    )
    require(
        uml_actions == expected_actions,
        "UML-Aktionen unterscheiden sich von den registrierten Callbacks.",
    )

    graph = create_graph(machine)
    expected_ids = {
        f"transition_{source_id}_{event_id}_{target_id}": (
            source_id,
            target_id,
            event_id,
        )
        for source_id, target_id, event_id in expected
    }
    visual = Counter()
    for edge in graph.get_edges():
        source_id = edge.get_source().strip('"')
        target_id = edge.get_destination().strip('"')
        if source_id not in states:
            continue
        identifier = edge.get("id")
        require(
            identifier in expected_ids,
            f"Nicht zugeordneter visueller Übergang: {source_id} -> {target_id}",
        )
        triple = expected_ids[identifier]
        require(
            triple[:2] == (source_id, target_id), f"Falsche Endpunkte: {identifier}"
        )
        require(
            edge.get("tooltip") == f"{source_id} --{triple[2]}--> {target_id}",
            f"Falsche Ereigniszuordnung: {identifier}",
        )
        visual[triple] += 1
        positions = edge.get("pos").split()
        tip = None
        if positions[0].startswith("e,"):
            tip = tuple(map(float, positions.pop(0).split(",")[1:]))
        controls = [tuple(map(float, point.split(","))) for point in positions]
        require(
            on_state_border(controls[0], POSITIONS[source_id]),
            f"Pfeil beginnt am falschen Zustand: {identifier}",
        )
        if edge.get("arrowhead") == "none":
            endpoint = controls[-1]
            require(
                target_id == "standing_idle"
                and (
                    endpoint == (300, 930)
                    if source_id == "startup"
                    else endpoint[0] == 1680 and 65 <= endpoint[1] <= 930
                ),
                f"Sammelpfad führt nicht zur gemeinsamen Rückleitung: {identifier}",
            )
        else:
            require(
                tip is not None and on_state_border(tip, POSITIONS[target_id]),
                f"Pfeil zeigt auf den falschen Zustand: {identifier}",
            )
        points, label_position = ROUTES[source_id, target_id]
        if label_position is None:
            require(
                any(
                    other_source != source_id
                    and other_target == target_id
                    and other_event == triple[2]
                    and ROUTES[other_source, other_target][1] is not None
                    and ROUTES[other_source, other_target][0][-2:] == points[-2:]
                    for other_source, other_target, other_event in expected
                ),
                f"Unbeschrifteter Pfad ohne gleichwertigen beschrifteten Partner: {identifier}",
            )
        for start, end in pairwise(points):
            for state_id, (center_x, center_y) in POSITIONS.items():
                if state_id in (source_id, target_id):
                    continue
                horizontal = (
                    start[1] == end[1]
                    and center_y - 56 < start[1] < center_y + 56
                    and max(start[0], end[0]) > center_x - 140
                    and min(start[0], end[0]) < center_x + 140
                )
                vertical = (
                    start[0] == end[0]
                    and center_x - 140 < start[0] < center_x + 140
                    and max(start[1], end[1]) > center_y - 56
                    and min(start[1], end[1]) < center_y + 56
                )
                require(
                    not (horizontal or vertical),
                    f"Pfad {identifier} durchquert Zustand {state_id}.",
                )
    require(
        visual == expected,
        "Visuelle Übergänge unterscheiden sich vom Python-Quelltext.",
    )
    shared_return = next(
        edge for edge in graph.get_edges() if edge.get_source() == "junction_return_auf"
    )
    require(
        shared_return.get_destination() == "standing_idle"
        and shared_return.get("pos").startswith("e,300,836 "),
        "Die gemeinsame Rückleitung endet nicht bei Bereit · Stehen.",
    )

    svg_namespace = {"svg": "http://www.w3.org/2000/svg"}
    visual_svg = tree.parse(output_directory / "state_machine.svg").getroot()
    require(
        {
            element.get("id")
            for element in visual_svg.iter()
            if element.get("id", "").startswith("transition_")
        }
        == expected_ids.keys(),
        "Visuelles SVG ist veraltet oder enthält abweichende Übergänge.",
    )
    for state_id, (_, description) in STATE_DETAILS.items():
        node = visual_svg.find(f".//svg:g[@id='state_{state_id}']", svg_namespace)
        require(node is not None, f"Zustand fehlt im visuellen SVG: {state_id}")
        texts = [text.text for text in node.findall(".//svg:text", svg_namespace)]
        require(
            state_id in texts
            and all(line in texts for line in description.split("<BR/>")),
            f"Zustandsbeschreibung ist veraltet: {state_id}",
        )

    uml_svg = tree.parse(output_directory / "state_machine_uml.svg").getroot()
    entities = uml_svg.findall(".//svg:g[@class='entity']", svg_namespace)
    require(
        {entity.get("data-qualified-name") for entity in entities} == states,
        "UML-SVG enthält abweichende Zustände.",
    )
    labels = uml_svg.find("svg:g[@class='transition-labels']", svg_namespace)
    require(labels is not None, "UML-SVG enthält keine freigestellten Ereignisnamen.")
    require(
        Counter(text.text for text in labels.findall("svg:text", svg_namespace))
        == Counter(event_id for _, _, event_id in expected.elements()),
        "Ereignisnamen fehlen im UML-SVG.",
    )
    for entity in entities:
        state_id = entity.get("data-qualified-name")
        texts = [text.text for text in entity.findall("svg:text", svg_namespace)]
        require(
            all(
                f"{keyword} / {callback}()" in texts
                for source_id, keyword, callback in expected_actions
                if source_id == state_id
            ),
            f"UML-SVG enthält abweichende Zustandsaktionen: {state_id}",
        )
    print(
        f"Abgleich bestanden: {len(states)} Zustände, {sum(expected.values())} Übergänge, {len(expected_actions)} registrierte Callbacks."
    )
    print(
        "Python-AST, Framework, beide Generatoren und beide SVG-Exporte stimmen strukturell überein."
    )


def main():
    script_path = Path(__file__).resolve()
    robot_path = script_path.parents[3] / "apps/robot"
    robot_environment = robot_path / ".venv"
    robot_python = robot_environment / "bin/python"
    if robot_python.is_file() and Path(sys.prefix) != robot_environment:
        os.execv(
            str(robot_python), [str(robot_python), str(script_path), *sys.argv[1:]]
        )
    for package in ("dog-core", "dog-perception", "dog-recorder"):
        sys.path.insert(0, str(robot_path / package / "src"))

    from dog_core.machine import PrenMachine

    check(PrenMachine, script_path.parents[1] / "src/dog_core")


if __name__ == "__main__":
    main()
