import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as tree
from pathlib import Path

from generate_state_graph import FONT_NAME, STATE_DETAILS


def plantuml_label(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def create_source(machine):
    from statemachine.contrib.diagram import extract

    states = list(machine.states)
    registered_actions = {state.id: state.actions for state in extract(machine).states}
    if {state.id for state in states} != STATE_DETAILS.keys():
        raise ValueError(
            "Die Zustände haben sich geändert. STATE_DETAILS aktualisieren."
        )

    lines = [
        "@startuml state_machine_uml",
        "left to right direction",
        f"skinparam defaultFontName {FONT_NAME}",
        "skinparam defaultFontSize 12",
        "skinparam backgroundColor white",
        "skinparam shadowing false",
        "skinparam ArrowColor #334155",
        "skinparam ArrowThickness 1.2",
        "skinparam nodesep 30",
        "skinparam ranksep 55",
        "skinparam Padding 12",
        "skinparam TitleFontSize 24",
        "skinparam CaptionFontSize 14",
        "skinparam defaultTextAlignment left",
        "skinparam state {",
        "  BackgroundColor #F8FAFC",
        "  BorderColor #334155",
        "  FontColor #172B45",
        "  FontSize 14",
        "  AttributeFontSize 11",
        "}",
        "title Zustandsdiagramm",
        "caption Alle Übergänge nur im Happy Path dargestellt",
        "",
    ]

    for state in states:
        title = STATE_DETAILS[state.id][0].replace("«", "").replace("»", "")
        label = (
            f"<size:14><b>{plantuml_label(title)}</b></size>\\n"
            f"<size:10><color:#64748B>{state.id}</color></size>"
        )
        lines.append(f'state "{label}" as {state.id}')
        for action in registered_actions[state.id]:
            keyword = action.type.name.lower()
            callbacks = action.body.split(", ")
            if keyword not in {"entry", "exit"} or not all(
                callback.isidentifier() for callback in callbacks
            ):
                raise ValueError(
                    "Neue Zustandsaktionen müssen im UML-Generator ergänzt werden."
                )
            calls = "; ".join(f"{callback}()" for callback in callbacks)
            lines.append(f"{state.id} : {keyword} / {calls}")
        lines.append("")

    for state in states:
        if state.initial:
            lines.append(f"[*] --> {state.id}")
        for transition in state.transitions:
            if list(transition.cond):
                raise ValueError(
                    "Neue Übergangsbedingungen müssen im UML-Generator ergänzt werden."
                )
            for event in transition.events:
                lines.append(f"{state.id} --> {transition.target.id} : {event.id}")

    lines.extend(
        [
            "",
            "legend bottom left",
            "  entry / Verhalten: beim Eintritt in den Zustand",
            "  exit / Verhalten: beim Verlassen des Zustands",
            "  Pfeilbeschriftung: auslösendes Ereignis (Name aus dem Code)",
            "  Auch intern ausgelöste Ereignisse sind explizite Trigger.",
            "  Keine zusätzlichen Bedingungen oder Übergangseffekte modelliert.",
            "  Kein Endzustand: Die Zustandsmaschine läuft im Dauerbetrieb.",
            "endlegend",
            "@enduml",
            "",
        ]
    )
    return "\n".join(lines)


def finish_svg(svg_path):
    namespace = "http://www.w3.org/2000/svg"
    tree.register_namespace("", namespace)
    document = tree.parse(svg_path)
    root = document.getroot()
    root.insert(
        0,
        tree.Element(
            f"{{{namespace}}}rect",
            {"width": "100%", "height": "100%", "fill": "#FFFFFF"},
        ),
    )
    labels = tree.Element(f"{{{namespace}}}g", {"class": "transition-labels"})
    for group in root.iter(f"{{{namespace}}}g"):
        if group.get("class") != "link":
            continue
        for text in list(group.findall(f"{{{namespace}}}text")):
            left = float(text.get("x"))
            baseline = float(text.get("y"))
            width = float(text.get("textLength"))
            size = float(text.get("font-size"))
            tree.SubElement(
                labels,
                f"{{{namespace}}}rect",
                {
                    "x": str(left - 3),
                    "y": str(baseline - size - 2),
                    "width": str(width + 6),
                    "height": str(size * 1.35 + 4),
                    "fill": "#FFFFFF",
                    "rx": "2",
                },
            )
            group.remove(text)
            labels.append(text)
    root.append(labels)
    document.write(svg_path, encoding="utf-8", xml_declaration=True)


def main():
    script_path = Path(__file__).resolve()
    robot_path = script_path.parents[3] / "apps/robot"
    robot_environment = robot_path / ".venv"
    robot_python = robot_environment / "bin/python"

    if robot_python.is_file() and Path(sys.prefix) != robot_environment:
        os.execv(
            str(robot_python), [str(robot_python), str(script_path), *sys.argv[1:]]
        )

    plantuml = shutil.which("plantuml")
    if plantuml is None:
        raise SystemExit(
            "PlantUML fehlt. Installation unter macOS: brew install plantuml"
        )

    for package in ("dog-core", "dog-perception", "dog-recorder"):
        sys.path.insert(0, str(robot_path / package / "src"))

    from dog_core.machine import PrenMachine

    source_path = script_path.parents[1] / "src/dog_core/state_machine_uml.puml"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(create_source(PrenMachine), encoding="utf-8")
    subprocess.run(
        [plantuml, "-charset", "UTF-8", "-tsvg", str(source_path)], check=True
    )
    finish_svg(source_path.with_suffix(".svg"))
    print(f"UML-Zustandsdiagramm erstellt: {source_path.with_suffix('.svg')}")
    print(f"Bearbeitbare PlantUML-Quelle: {source_path}")


if __name__ == "__main__":
    main()
