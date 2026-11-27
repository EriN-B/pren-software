import os
import sys
from html import escape
from pathlib import Path

FONT_NAME = "Inter"

STATE_DETAILS = {
    "startup": (
        "Initialisierung",
        "Kamera, Mikrofon und Modelle laden.<BR/>Verbindung und Startposition einrichten.",
    ),
    "standing_idle": (
        "Bereit · Stehen",
        "Auf einen Sprach- oder<BR/>Gestenbefehl warten.",
    ),
    "sitz": ("Sitzen", "Sitzposition anfordern.<BR/>Auf den nächsten Befehl warten."),
    "platz": ("Liegen", "Liegeposition anfordern.<BR/>Auf den nächsten Befehl warten."),
    "auf_before_such": (
        "Aufstehen vor der Suche",
        "Aufstehbefehl einreihen,<BR/>anschließend Suche starten.",
    ),
    "auf_before_hier": (
        "Aufstehen vor «Hier»",
        "Aufstehbefehl einreihen,<BR/>anschließend «Hier» starten.",
    ),
    "auf_before_brav": (
        "Aufstehen vor «Brav»",
        "Aufstehbefehl einreihen,<BR/>anschließend «Brav» starten.",
    ),
    "perform_auf": (
        "Aufstehen",
        "Aufstehbefehl zur Übertragung<BR/>an die Steuerung einreihen.",
    ),
    "searching": (
        "Knochen suchen",
        "180°-Drehung anfordern,<BR/>Knochen suchen und anfahren.",
    ),
    "found": (
        "Fund signalisieren",
        "Fundsignal zur Übertragung<BR/>an die Steuerung einreihen.",
    ),
    "returning": (
        "Zum Start zurückkehren",
        "Aufgezeichneten Weg zurückfahren.<BR/>Startposition und Ausrichtung erreichen.",
    ),
    "perform_hier": (
        "Herankommen · «Hier»",
        "Langsam vorwärtsfahren.<BR/>Bei erkannten Schuhen anhalten.",
    ),
    "perform_brav": (
        "«Brav» ausführen",
        "Brav-Befehl zur Übertragung<BR/>an die Steuerung einreihen.",
    ),
}

GROUPS = {
    "waiting": {
        "title": "BEFEHLE ENTGEGENNEHMEN",
        "color": "#2563A6",
        "fill": "#EDF5FC",
        "states": ("standing_idle", "sitz", "platz"),
        "bounds": (20, 180, 340, 910),
    },
    "standing_up": {
        "title": "AUFSTEHEN",
        "color": "#9A6418",
        "fill": "#FFF8E9",
        "states": ("perform_auf",),
        "bounds": (490, -30, 810, 175),
    },
    "search": {
        "title": "KNOCHENSUCHE · «SUCH»",
        "color": "#167060",
        "fill": "#EDF8F4",
        "states": ("auf_before_such", "searching", "found"),
        "bounds": (490, 685, 1610, 890),
    },
    "approach": {
        "title": "HERANKOMMEN · «HIER»",
        "color": "#70558E",
        "fill": "#F6F1FA",
        "states": ("auf_before_hier", "perform_hier"),
        "bounds": (490, 435, 1230, 640),
    },
    "praise": {
        "title": "«BRAV» AUSFÜHREN",
        "color": "#88602F",
        "fill": "#FBF5EC",
        "states": ("auf_before_brav", "perform_brav"),
        "bounds": (490, 185, 1230, 390),
    },
    "return": {
        "title": "RÜCKKEHR ZUM START",
        "color": "#167060",
        "fill": "#EDF8F4",
        "states": ("returning",),
        "bounds": (1290, 435, 1610, 640),
    },
}

POSITIONS = {
    "startup": (180, 1000),
    "standing_idle": (180, 780),
    "sitz": (180, 530),
    "platz": (180, 280),
    "auf_before_such": (650, 780),
    "auf_before_hier": (650, 530),
    "auf_before_brav": (650, 280),
    "perform_auf": (650, 65),
    "searching": (1070, 780),
    "found": (1450, 780),
    "returning": (1450, 530),
    "perform_hier": (1070, 530),
    "perform_brav": (1070, 280),
}

ROUTES = {
    ("startup", "standing_idle"): ([(180, 944), (180, 836)], (255, 865)),
    ("standing_idle", "sitz"): ([(180, 724), (180, 586)], (215, 655)),
    ("standing_idle", "platz"): (
        [(40, 780), (-20, 780), (-20, 280), (40, 280)],
        (-58, 650),
    ),
    ("sitz", "platz"): ([(125, 474), (125, 336)], (88, 405)),
    ("platz", "sitz"): ([(235, 336), (235, 474)], (270, 405)),
    ("standing_idle", "searching"): (
        [(320, 800), (365, 800), (365, 900), (1070, 900), (1070, 836)],
        (850, 915),
    ),
    ("standing_idle", "perform_hier"): (
        [(320, 780), (350, 780), (350, 665), (1070, 665), (1070, 586)],
        (850, 680),
    ),
    ("standing_idle", "perform_brav"): (
        [(320, 760), (335, 760), (335, 415), (1070, 415), (1070, 336)],
        (850, 430),
    ),
    ("sitz", "auf_before_such"): (
        [(320, 555), (390, 555), (390, 780), (510, 780)],
        (450, 795),
    ),
    ("platz", "auf_before_such"): (
        [(320, 305), (390, 305), (390, 780), (510, 780)],
        None,
    ),
    ("sitz", "auf_before_hier"): ([(320, 530), (430, 530), (510, 530)], (470, 545)),
    ("platz", "auf_before_hier"): (
        [(320, 280), (430, 280), (430, 530), (510, 530)],
        None,
    ),
    ("sitz", "auf_before_brav"): (
        [(320, 505), (470, 505), (470, 280), (510, 280)],
        (442, 267),
    ),
    ("platz", "auf_before_brav"): (
        [(320, 255), (470, 255), (470, 280), (510, 280)],
        None,
    ),
    ("sitz", "perform_auf"): (
        [(320, 480), (490, 480), (490, 65), (510, 65)],
        (455, 135),
    ),
    ("platz", "perform_auf"): ([(320, 235), (490, 235), (490, 65), (510, 65)], None),
    ("auf_before_such", "searching"): ([(790, 780), (930, 780)], (860, 795)),
    ("auf_before_hier", "perform_hier"): ([(790, 530), (930, 530)], (860, 545)),
    ("auf_before_brav", "perform_brav"): ([(790, 280), (930, 280)], (860, 295)),
    ("searching", "found"): ([(1210, 780), (1310, 780)], (1260, 795)),
    ("found", "returning"): (
        [(1450, 724), (1450, 660), (1550, 660), (1550, 586)],
        (1515, 680),
    ),
    ("returning", "standing_idle"): (
        [(1590, 530), (1680, 530), (1680, 930), (180, 930), (180, 836)],
        (1635, 555),
    ),
    ("perform_hier", "standing_idle"): (
        [(1070, 586), (1070, 635), (1680, 635), (1680, 930), (180, 930), (180, 836)],
        (1165, 650),
    ),
    ("perform_brav", "standing_idle"): (
        [(1070, 336), (1070, 385), (1680, 385), (1680, 930), (180, 930), (180, 836)],
        (1170, 400),
    ),
    ("perform_auf", "standing_idle"): (
        [(790, 65), (1680, 65), (1680, 930), (180, 930), (180, 836)],
        (1060, 80),
    ),
}

COMMANDS = {"Such", "Hier", "Sitz", "Platz", "Auf", "Brav"}
AUTOMATIC_LABELS = {
    "Signal": "Knochen erreicht",
    "Return back": "Fundsignal eingereiht",
    "Returned": "Startposition\\nerreicht",
    "Go to searching": "weiter zur Suche",
    "Go to perform hier": "weiter zu «Hier»",
    "Go to perform brav": "weiter zu «Brav»",
}
READY_LABELS = {
    "startup": "initialisiert",
    "perform_auf": "Auf-Befehl eingereiht",
    "perform_hier": "Annäherung beendet",
    "perform_brav": "Brav-Befehl eingereiht",
}


def state_label(state_id, color):
    title, description = STATE_DETAILS[state_id]
    description_rows = "".join(
        '<TR><TD ALIGN="LEFT" VALIGN="MIDDLE" HEIGHT="17">'
        '<FONT COLOR="#334155" POINT-SIZE="12">'
        f"{escape(line)}</FONT></TD></TR>"
        for line in description.split("<BR/>")
    )
    return (
        '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="16" '
        'WIDTH="280" HEIGHT="112" FIXEDSIZE="TRUE">'
        '<TR><TD ALIGN="LEFT" VALIGN="TOP">'
        '<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0" WIDTH="248">'
        '<TR><TD ALIGN="LEFT" VALIGN="TOP" HEIGHT="22">'
        f'<FONT COLOR="{color}" POINT-SIZE="16">'
        f"<B>{escape(title)}</B></FONT></TD></TR>"
        f'<TR><TD ALIGN="LEFT" VALIGN="TOP" HEIGHT="16"><FONT FACE="{FONT_NAME}" COLOR="#64748B" '
        f'POINT-SIZE="10">{escape(state_id)}</FONT></TD></TR>'
        '<TR><TD HEIGHT="8"></TD></TR>'
        f"{description_rows}</TABLE></TD></TR></TABLE>>"
    )


def spline_position(points, arrow=True):
    tip_x, tip_y = points[-1]
    previous_x, previous_y = points[-2]
    distance = ((tip_x - previous_x) ** 2 + (tip_y - previous_y) ** 2) ** 0.5
    arrow_length = 9 if arrow else 0
    end = (
        tip_x - arrow_length * (tip_x - previous_x) / distance,
        tip_y - arrow_length * (tip_y - previous_y) / distance,
    )
    controls = [points[0]]
    current = points[0]
    for index, corner in enumerate(points[1:-1], start=1):
        following = points[index + 1]
        incoming = (
            (corner[0] - current[0]) ** 2 + (corner[1] - current[1]) ** 2
        ) ** 0.5
        outgoing = (
            (following[0] - corner[0]) ** 2 + (following[1] - corner[1]) ** 2
        ) ** 0.5
        radius = min(10, incoming / 3, outgoing / 3)
        before = tuple(
            corner[axis] + radius * (current[axis] - corner[axis]) / incoming
            for axis in (0, 1)
        )
        after = tuple(
            corner[axis] + radius * (following[axis] - corner[axis]) / outgoing
            for axis in (0, 1)
        )
        controls.extend((current, before, before, corner, corner, after))
        current = after
    controls.extend((current, end, end))
    prefix = f"e,{tip_x},{tip_y} " if arrow else ""
    return prefix + " ".join(f"{point[0]:.2f},{point[1]:.2f}" for point in controls)


def create_graph(machine):
    import pydot
    from statemachine.contrib.diagram import DotGraphMachine

    source_graph = DotGraphMachine(machine)()
    transition_names = {
        (state.id, transition.target.id): str(event.name)
        for state in machine.states
        for transition in state.transitions
        for event in transition.events
    }
    transition_ids = {
        (state.id, transition.target.id): event.id
        for state in machine.states
        for transition in state.transitions
        for event in transition.events
    }
    state_ids = {state.id for state in machine.states}
    grouped_ids = [
        state_id for group in GROUPS.values() for state_id in group["states"]
    ]
    if (
        state_ids != STATE_DETAILS.keys()
        or state_ids != POSITIONS.keys()
        or transition_names.keys() != ROUTES.keys()
        or set(grouped_ids) != state_ids - {"startup"}
        or len(grouped_ids) != len(set(grouped_ids))
    ):
        raise ValueError(
            "Die Zustandsmaschine hat sich geändert. Beschreibungen und Layout aktualisieren."
        )

    graph = pydot.Dot(
        "pren_state_machine",
        graph_type="digraph",
        bgcolor="white",
        fontname=FONT_NAME,
        fontcolor="#172B45",
        fontsize="14",
        dpi="240",
        pad="0.35",
        notranslate="true",
        outputorder="edgesfirst",
        labelloc="t",
        labeljust="l",
        label=(
            '<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4">'
            '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="28"><B>Zustandsdiagramm</B></FONT></TD></TR>'
            '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="14" COLOR="#64748B">'
            "Alle Übergänge nur im Happy Path dargestellt"
            '</FONT></TD></TR><TR><TD HEIGHT="8"></TD></TR>'
            '<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="12">'
            '<FONT COLOR="#2563A6">━━▶  Farbiger Pfeil: Befehl «…»</FONT>'
            '     ·     <FONT COLOR="#64748B">┄┄▶  Automatischer Übergang</FONT>'
            f'     ·     <FONT FACE="{FONT_NAME}" COLOR="#64748B">Zustandsname im Code</FONT>'
            '</FONT></TD></TR><TR><TD ALIGN="LEFT"><FONT POINT-SIZE="11" COLOR="#64748B">'
            "Punkt: zusammengeführte Pfade · Kreuzung ohne Punkt: keine Verbindung · Rückwege am rechten Rand"
            '</FONT></TD></TR><TR><TD HEIGHT="16"></TD></TR></TABLE>>'
        ),
    )
    graph.set_node_defaults(
        shape="box",
        style="rounded,filled",
        fontname=FONT_NAME,
        color="#CBD5E1",
        fillcolor="white",
        penwidth="1.4",
        margin="0",
        width=str(280 / 72),
        height=str(112 / 72),
        fixedsize="true",
    )
    graph.set_edge_defaults(
        fontname=FONT_NAME,
        fontsize="11",
        arrowsize="0.8",
        penwidth="1.5",
    )

    graph.add_node(
        pydot.Node(
            "start",
            shape="point",
            pos="180,1105!",
            width="0.12",
            height="0.12",
            color="#334155",
            fillcolor="#334155",
        )
    )
    graph.add_node(
        pydot.Node(
            "startup",
            id="state_startup",
            label=state_label("startup", "#475569"),
            fillcolor="#F8FAFC",
            pos="180,1000!",
        )
    )
    graph.add_edge(
        pydot.Edge(
            "start",
            "startup",
            color="#64748B",
            style="dashed",
            label="Start",
            pos=spline_position([(180, 1100), (180, 1056)]),
            lp="210,1080",
        )
    )

    for group_id, group in GROUPS.items():
        left, bottom, right, top = group["bounds"]
        cluster = pydot.Cluster(
            group_id,
            label=group["title"],
            fontname=f"{FONT_NAME} Bold",
            fontsize="13",
            fontcolor=group["color"],
            color=group["fill"],
            fillcolor=group["fill"],
            style="rounded,filled",
            penwidth="1",
            bb=f"{left},{bottom},{right},{top}",
            lp=f"{650 if group_id == 'search' else (left + right) / 2},{top - 17}",
        )
        for state_id in group["states"]:
            center_x, center_y = POSITIONS[state_id]
            cluster.add_node(
                pydot.Node(
                    state_id,
                    id=f"state_{state_id}",
                    label=state_label(state_id, group["color"]),
                    color=group["color"],
                    pos=f"{center_x},{center_y}!",
                )
            )
        graph.add_subgraph(cluster)

    junctions = {
        "such": ((390, 555), GROUPS["search"]["color"]),
        "hier": ((430, 530), GROUPS["approach"]["color"]),
        "brav": ((470, 280), GROUPS["praise"]["color"]),
        "auf": ((490, 235), GROUPS["standing_up"]["color"]),
        "return_home": ((1680, 530), "#64748B"),
        "return_hier": ((1680, 635), "#64748B"),
        "return_brav": ((1680, 385), "#64748B"),
        "return_auf": ((1680, 65), "#64748B"),
        "initialized": ((300, 930), "#64748B"),
    }
    for junction_id, ((center_x, center_y), color) in junctions.items():
        graph.add_node(
            pydot.Node(
                f"junction_{junction_id}",
                shape="point",
                label="",
                pos=f"{center_x},{center_y}!",
                width="0.055",
                height="0.055",
                color=color,
                fillcolor=color,
            )
        )
    graph.add_edge(
        pydot.Edge(
            "junction_return_auf",
            "standing_idle",
            color="#64748B",
            style="dashed",
            label="zurück zu Bereit · Stehen",
            fontcolor="#64748B",
            lp="1170,945",
            pos=spline_position([(1680, 65), (1680, 930), (300, 930), (300, 836)]),
        )
    )

    for edge in source_graph.get_edges():
        source = edge.get_source().strip('"')
        target = edge.get_destination().strip('"')
        if source not in state_ids:
            continue
        event = transition_names[source, target]
        is_command = event in COMMANDS
        if is_command:
            label = f"«{event}»"
        elif event == "Go to standing idle":
            label = READY_LABELS[source]
        else:
            label = AUTOMATIC_LABELS[event]
        points, label_position = ROUTES[source, target]
        arrow = target != "standing_idle"
        if target == "standing_idle":
            if source == "startup":
                points = [(180, 944), (300, 944), (300, 930)]
            else:
                join_index = next(
                    index for index, point in enumerate(points) if point[0] == 1680
                )
                points = points[: join_index + 1]
        color = (
            next(
                group["color"] for group in GROUPS.values() if target in group["states"]
            )
            if is_command
            else "#64748B"
        )
        if label_position is None:
            label = ""
        graph.add_edge(
            pydot.Edge(
                source,
                target,
                id=f"transition_{source}_{transition_ids[source, target]}_{target}",
                tooltip=f"{source} --{transition_ids[source, target]}--> {target}",
                label=label,
                color=color,
                fontcolor=color,
                style="solid" if is_command else "dashed",
                arrowhead="normal" if arrow else "none",
                pos=spline_position(points, arrow=arrow),
                lp=f"{label_position[0]},{label_position[1]}"
                if label_position
                else "0,0",
            )
        )
    return graph


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

    output_path = script_path.parents[1] / "src/dog_core/state_machine.svg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph = create_graph(PrenMachine)
    graph.write_svg(str(output_path), prog=["neato", "-n2"])
    print(f"Zustandsdiagramm erstellt: {output_path}")


if __name__ == "__main__":
    main()
