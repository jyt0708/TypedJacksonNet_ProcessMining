from typing import Dict, Any
from typing import Set
from t_JN import TypedJacksonNet


def tjn_to_json(tjn: TypedJacksonNet) -> Dict[str, Any]:
    """
    Convert a TypedJacksonNet into a JSON-like structure with nodes and edges.
    This can be serialized with Flask's jsonify and visualized in the frontend.
    """ 
    nodes = []
    edges = []

    # Add places as nodes
    for place in tjn.places.values():
        types = []
        if hasattr(place, 'get_types') and place.get_types():
            types = [str(t) for t in place.get_types()]  # ensure string

        nodes.append({
            "id": place.name,
            "type": "place",
            "label": place.name,
            "types": types
        })

    # Add transitions as nodes
    for transition in tjn.transitions.values():
        node_data = {
            "id": transition.name,
            "type": "transition",
            "label": transition.name
        }
        
        # Add emit and collect attributes
        if hasattr(transition, 'emit') and transition.emit is not None:
            if isinstance(transition.emit, (set,list)):
                # If it's a set of Place objects, convert to list of names
                node_data["emit"] = sorted([str(e) for e in transition.emit])
            else:
                node_data["emit"] = str(transition.emit)

        if hasattr(transition, 'collect') and transition.collect is not None:
            if isinstance(transition.collect, (set, list)):
                # If it's a set of Place objects, convert to list of names
                node_data["collect"] = sorted([str(c) for c in transition.collect])
            else:
                node_data["collect"] = str(transition.collect)
        
        nodes.append(node_data)

    # Add arcs as edges
    for arc in tjn.arcs:
        # Safely get source and target names
        source_name = arc.source.name if hasattr(arc.source, 'name') else str(arc.source)
        target_name = arc.target.name if hasattr(arc.target, 'name') else str(arc.target)
        
        # Safely get variable label
        if hasattr(arc, 'variable'):
            if isinstance(arc.variable, set):
                label = ", ".join([str(v) for v in arc.variable])
            else:
                label = str(arc.variable)
        else:
            label = ""
        
        edges.append({
            "source": source_name,
            "target": target_name,
            "label": label
        })

    # Create a clean dictionary with only serializable data
    result = {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "num_places": len(tjn.places),
            "num_transitions": len(tjn.transitions),
            "num_arcs": len(tjn.arcs),
            "first_place": tjn.first_place.name if tjn.first_place and hasattr(tjn.first_place, 'name') else None,
            "last_place": tjn.last_place.name if tjn.last_place and hasattr(tjn.last_place, 'name') else None,
        }
    }

    return result