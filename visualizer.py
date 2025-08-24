from typing import Dict, Any
from typing import Set
from t_JN import TypedJacksonNet, Place, Transition, Arc


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
        
        # Safely add emit and collect attributes - they are Place objects
        if hasattr(transition, 'emit'):
            if isinstance(transition.emit, set):
                # If it's a set of Place objects, convert to list of names
                node_data["emit"] = [place.name for place in transition.emit if hasattr(place, 'name')]
            elif hasattr(transition.emit, 'name'):
                # If it's a single Place object, get its name
                node_data["emit"] = transition.emit.name
            else:
                # Fallback: convert to string
                node_data["emit"] = str(transition.emit)
        
        if hasattr(transition, 'collect'):
            if isinstance(transition.collect, set):
                # If it's a set of Place objects, convert to list of names
                node_data["collect"] = [place.name for place in transition.collect if hasattr(place, 'name')]
            elif hasattr(transition.collect, 'name'):
                # If it's a single Place object, get its name
                node_data["collect"] = transition.collect.name
            else:
                # Fallback: convert to string
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