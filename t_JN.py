from __future__ import annotations
import pm4py
import subprocess
import os
import copy
from enum import Enum
from collections import defaultdict, deque, OrderedDict
from pm4py.objects.petri_net.utils.petri_utils import add_arc_from_to
from pm4py.objects.petri_net.obj import PetriNet, Marking
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.objects.log.obj import Trace, EventLog
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.visualization.petri_net import visualizer as pn_visualizer
from pm4py.visualization.process_tree import visualizer as pt_visualizer
from typing import Dict, Set, Optional, Tuple
from collections import defaultdict
from pm4py.objects.process_tree.obj import ProcessTree
from pm4py.util import xes_constants as xes
from pm4py.objects.log.exporter.xes import exporter as xes_exporter
from pm4py.algo.analysis.workflow_net import algorithm as wfn_algorithm
from pm4py.objects.petri_net.exporter import exporter as pnml_exporter

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

class Operator(Enum):
    # sequence operator
    SEQUENCE = ';'
    # choice operator
    XOR = '+'
    # parallel operator
    PARALLEL = '||'
    # loop operator
    LOOP = '#'

class Node:
  def __init__(self, name: str):
    self.name = name

class Place(Node):
    def __init__(self, name: str, types: Set = None):
        super(Place, self).__init__(name)
        self.place_types = types if types is not None else set()
        self.start_place = None
        self.end_place = None
        self.in_arcs = set()
        self.out_arcs = set()

    def add_types(self, types):
        if isinstance(types, Set):
            self.place_types.update(types)
        else:
            self.place_types.add(types)

    def set_start_place(self, start_place):
        self.start_place = start_place

    def set_end_place(self, end_place):
        self.end_place = end_place

    def get_types(self) -> Set:
        return self.place_types

    def set_types(self, types: Set):
        self.place_types = types

    def set_in_arcs(self, in_arcs: Set):
        self.in_arcs = in_arcs

    def set_out_arcs(self, out_arcs: Set):
        self.out_arcs = out_arcs

    def add_in_arc(self, in_arc):
        self.in_arcs.add(in_arc)

    def add_out_arc(self, out_arc):
        self.out_arcs.add(out_arc)

class Transition(Node):
    def __init__(self, name: str, inscription: Dict[str, Dict[str, str]], emit: Optional[str] = None, collect: Optional[str] = None):
        super(Transition, self).__init__(name)
        self.in_arcs = set()
        self.out_arcs = set()
        self.inscription = inscription
        # Each transition can have multiple pre- & post- places
        self.pre = set()
        self.post = set()
        self.emit = emit
        self.collect = collect

    def set_emit(self, emit):
        self.emit = emit

    def set_collect(self, collect):
        self.collect = collect

    def add_pre_place(self, place):
        self.pre.add(place)

    def add_post_place(self, place):
        self.post.add(place)

    def update_pre_place(self, places):
        self.pre.update(places)

    def update_post_place(self, places):
        self.post.update(places)


class Arc:
    def __init__(self, variable: Set, source: Node, target: Node):
        self.variable = variable
        self.source = source
        self.target = target

    def set_variable(self, variable):
        self.variable = variable

    def set_source(self, source):
        self.source = source

    def set_target(self, target):
        self.target = target


class TypedJacksonNet:
    def __init__(self, operator: Optional[Operator] = None, parent: Optional[Operator] = None,
                 children: Optional[TypedJacksonNet] = None):
        self.operator = operator
        self.first_place = None
        self.last_place = None
        self.places = {}
        self.parent = self if parent is None else parent
        self.arcs = set()
        self.transitions = {}
        self.children = set() if children is None else children


    def add_place(self, place: Place, types=None):
        if types is None:
            types = set()
        place.set_types(types)
        if place.name not in self.places:
            self.places[place.name] = place


    def add_transition(self, name, inscription, pre: Optional[Set] = None, post: Optional[Set] = None):
        # Transition of the same name already exists, do nothing
        if self.transitions.get(name) is not None:
            return
        name = "tau" if name is None else name
        transition = Transition(name, inscription, pre, post)
        self.transitions[name] = transition
        in_arcs = set()
        out_arcs = set()
        for pre_place in pre:
            in_arc = Arc(inscription['input'], pre_place, transition)
            in_arcs.add(in_arc)
            if isinstance(pre_place, Place):
                pre_place.add_out_arc(in_arc)
        for post_place in post:
            out_arc = Arc(inscription['output'], transition, post_place)
            out_arcs.add(out_arc)
            if isinstance(post_place, Place):
                post_place.add_in_arc(out_arc)

        transition.update_pre_place(pre)
        transition.update_post_place(post)
        self.arcs.update(in_arcs)
        self.arcs.update(out_arcs)

    def get_first_place(self) -> Place:
        return self.first_place

    def get_last_place(self) -> Place:
        return self.last_place

    def remove_place(self, place_name):
        """
        Remove a place by place name and delete:
        ... its relation to its pre- and post-transition
        ... its connecting arcs
        """
        if place_name in self.places:
            place = self.places.get(place_name)
            pre_trans = {arc.source for arc in self.arcs if arc.target == place}
            post_trans = {arc.target for arc in self.arcs if arc.source == place}
            for t in pre_trans:
                self.transitions[t.name].post.discard(place)
            for t in post_trans:
                self.transitions[t.name].pre.discard(place)

            # Remove arcs to & from the place
            self.arcs = {arc for arc in self.arcs
                         if not (arc.target == place or arc.source == place)}
            self.places.pop(place_name)
        else:
            print(f"{place_name} does not exist in current net.")



    def print_net(self):
        for arc in self.arcs:
            source_name = arc.source.name if hasattr(arc.source, 'name') else str(arc.source)
            target_name = arc.target.name if hasattr(arc.target, 'name') else str(arc.target)
            print(f"{source_name} -> {target_name}")


    
    def sort_transitions_left_to_right(self):
        """
        Sort transitions in a left-to-right order according to arcs,
        and update self.transitions in-place.
        """
        # Build dependency graph between transitions
        dep_graph = defaultdict(set)     # t1 -> successors
        indegree = defaultdict(int)      # indegree count per transition

        # Initialize indegrees
        for t in self.transitions.values():
            indegree[t] = 0

        # For every place, connect its input transitions to its output transitions
        for p in self.places.values():
            incoming_trans = [arc.source for arc in p.in_arcs if isinstance(arc.source, Transition)]
            outgoing_trans = [arc.target for arc in p.out_arcs if isinstance(arc.target, Transition)]

            for t_in in incoming_trans:
                for t_out in outgoing_trans:
                    if t_out not in dep_graph[t_in]:
                        dep_graph[t_in].add(t_out)
                        indegree[t_out] += 1

        # --- Topological Sort (Kahn's Algorithm) ---
        queue = deque([t for t in indegree if indegree[t] == 0])
        sorted_transitions = []

        while queue:
            t = queue.popleft()
            sorted_transitions.append(t)
            for succ in dep_graph[t]:
                indegree[succ] -= 1
                if indegree[succ] == 0:
                    queue.append(succ)

        # Handle cycles (append remaining unsorted transitions)
        if len(sorted_transitions) < len(self.transitions):
            print("[Warning] Cycles detected in transition graph, ordering may be partial.")
            for t in self.transitions.values():
                if t not in sorted_transitions:
                    sorted_transitions.append(t)

        # --- Rebuild self.transitions in sorted order ---
        sorted_dict = OrderedDict()
        for t in sorted_transitions:
            sorted_dict[t.name] = t
        self.transitions = sorted_dict


    def populate_transition_places(self):
        """
        Sort the transitions in a left-to-right order and detects all pre- and post-places of each transition in the net
        and updates:
          - Transition.pre / Transition.post
          - Place.in_arcs / Place.out_arcs
          - Transition.emit / Transition.collect
        """
        self.sort_transitions_left_to_right()
        # Clear all sets before rebuilding (to avoid duplication on re-call)
        for t in self.transitions.values():
            t.pre = set()
            t.post = set()
            t.emit = set()     
            t.collect = set()
            t.in_arcs = set()
            t.out_arcs = set()
        for p in self.places.values():
            p.in_arcs = set()
            p.out_arcs = set()

        # Scan arcs and update both sides
        for arc in self.arcs:
            if isinstance(arc.source, Place) and isinstance(arc.target, Transition):
                # Place → Transition
                t = arc.target
                p = arc.source
                t.pre.add(p)
                t.in_arcs.add(arc)
                p.out_arcs.add(arc)

            elif isinstance(arc.source, Transition) and isinstance(arc.target, Place):
                # Transition → Place
                t = arc.source
                p = arc.target
                t.post.add(p)
                t.out_arcs.add(arc)
                p.in_arcs.add(arc)
        
        # Deduce emit and collect from incoming/outgoing arc variables
        for t in self.transitions.values():
            incoming_vars = set()
            outgoing_vars = set()
            for arc in self.arcs:
                if arc.target == t:
                    incoming_vars.update(arc.variable)
                if arc.source == t:
                    outgoing_vars.update(arc.variable)
            t.emit = outgoing_vars - incoming_vars
            t.collect = incoming_vars - outgoing_vars
        
        # Ensure unique transition names
        name_count = {}
        to_rename = []
        for t_name, t in self.transitions.items():
            if t_name not in name_count:
                name_count[t_name] = [t]
            else:
                name_count[t_name].append(t)

        # Handle duplicates
        for base_name, trans_list in name_count.items():
            if len(trans_list) > 1:
                print(f"\n[Duplicate transition name detected: '{base_name}']")
                for i, t in enumerate(trans_list, 1):
                    print(f"  - Transition {i}: id={id(t)}, name={t.name}, pre={[p.name for p in t.pre]}, post={[p.name for p in t.post]}")

                # Rename only the duplicates (keep the first one unchanged)
                for idx, t in enumerate(trans_list[1:], 1):
                    new_name = f"{base_name}_{idx}"
                    print(f"  -> Renaming transition '{t.name}' (id={id(t)}) to '{new_name}'")
                    t.name = new_name


    def annotate_arcs_with_messages(self, messages: dict):
        """
        Update TypedJacksonNet arcs by propagating message variables.
        If transition A sends message m1 and transition F receives message m1,
        then arcs leaving A will carry variable 'm1' until F is reached.
        """
        for msg, participants in messages.items():
            senders = participants.get("sent_by", [])
            receivers = set(participants.get("received_by", []))

            for sender in senders:
                if sender not in self.transitions.keys():
                    continue
                start_transition = self.transitions[sender]

                # DFS/BFS to propagate the message variable
                stack = []
                visited = set()

                # push arcs leaving this transition
                for arc in self.arcs:
                    if arc.source == start_transition:
                        stack.append(arc)

                while stack:
                    arc = stack.pop()
                    if arc in visited:
                        continue
                    visited.add(arc)

                    # mark arc with message
                    if not hasattr(arc, "variable") or arc.variable is None:
                        arc.variable = set()
                    elif not isinstance(arc.variable, set):
                        arc.variable = {arc.variable}
                    arc.variable.add(msg)

                    target = arc.target

                    # if target is a transition that receives this msg -> stop propagation
                    if hasattr(target, "name") and target.name in receivers:
                        continue

                    # otherwise propagate further along outgoing arcs
                    for next_arc in self.arcs:
                        if next_arc.source == target and next_arc not in visited:
                            stack.append(next_arc)
            print(f"Sender '{sender}' sends message '{msg}' to receiving transition '{target.name}'")
            

    def remove_arc_from_to(self, fro, to):
        """
        Removes all arcs from 'fro' to 'to' in the Petri net.
        Returns a list of variables of the removed arcs (if available).
        """

        if isinstance(fro, Transition) and isinstance(to, Place):
            for a in list(self.arcs):
                if a.source == fro and a.target == to:
                    removed_vars = a.variable
                    self.arcs.remove(a)

                    return removed_vars
        elif isinstance(fro, Place) and isinstance(to, Transition):
            for a in list(self.arcs):
                if a.source == fro and a.target == to:
                    removed_vars = a.variable
                    self.arcs.remove(a)

                    return removed_vars

        return set()


    def add_arc_from_to(self, fro, to, var):
        if to.name == "t12_tau_start_tau_end":
            print(f"Pre places of {to.name}:")
            for a in to.pre:
                print(f"- {a.name}")

        if isinstance(fro, Transition) and isinstance(to, Place):
            arc = Arc(var, fro, to)
            self.arcs.add(arc)
            fro.post.add(to)
            fro.out_arcs.add(arc)
            to.in_arcs.add(arc)
        elif isinstance(fro, Place) and isinstance(to, Transition):
            arc = Arc(var, fro, to)
            self.arcs.add(arc)
            to.pre.add(fro)
            to.in_arcs.add(arc)
            fro.out_arcs.add(arc)


    def append_sequence(self, *children):
        if not children:
            return
        # self.operator = Operator.SEQUENCE

        # Add all children to this net
        for child in children:
            self.children.add(child)

            for place_name, place in child.places.items():
                if place_name not in self.places:
                    self.places[place_name] = place
                else:
                    # Merge types if place exists
                    self.places[place_name].add_types(place.get_types())
            for trans_name, trans in child.transitions.items():
                if trans_name not in self.transitions:
                    self.transitions[trans_name] = trans

            self.arcs.update(child.arcs)

        # Connect the nets in sequence
        if len(children) > 1:
            for i in range(len(children) - 1):
                current_net = children[i]
                next_net = children[i + 1]
              
                # Get the last place of current net and first place of next net
                last_place_current = current_net.last_place
                first_place_current = current_net.first_place
                first_place_next = next_net.first_place


                if last_place_current and first_place_next:
                    # Find arcs whose target or source is last_place_current and extract arc variables
                    arcs_last_place_current = {arc for arc in self.arcs if arc.target == last_place_current or arc.source == last_place_current}
                    variable_in_arcs = {
                        variable
                        for arc in arcs_last_place_current
                        for variable in arc.variable
                    }
                    # Find arcs whose source is first_place_next and extract the variables
                    arcs_first_place_next = {arc for arc in self.arcs if arc.source == first_place_next}
                    variable_out_arcs = {
                        variable
                        for arc in arcs_first_place_next
                        for variable in arc.variable
                    }

                    pre_trans = set()
                    for arc in arcs_last_place_current:
                      for node in (arc.source, arc.target):
                          if isinstance(node, Transition):
                              pre_trans.add(node)
                    post_trans = {arc.target for arc in arcs_first_place_next}
                    # pretransitions and their input variables
                    pre_trans_mapping = {arc.source: arc.variable for arc in self.arcs
                                         if arc.target == last_place_current}
                    pre_trans_mapping_loop = {arc.target: arc.variable for arc in self.arcs
                                         if arc.source == last_place_current}

                    # Remove last place of the current child
                    self.remove_place(last_place_current.name)


                    # Combine arc variables and set emiting variables in case of difference
                    if variable_in_arcs != variable_out_arcs:
                        emit = variable_out_arcs - variable_in_arcs
                        collect = variable_in_arcs - variable_out_arcs

                        # Remove elements starting with "m_" from emit and collect
                        emit = {x for x in emit if not x.startswith("m_")}
                        collect = {x for x in collect if not x.startswith("m_")}
                        for t in pre_trans:
                            t.set_emit(emit)
                        for t in post_trans:
                            t.set_collect(collect)

                        combined_variable = variable_in_arcs.union(variable_out_arcs)
                        first_place_next.set_types(combined_variable)

                        # Message object "m_x" should not be emitted by the transition
                        for arc in arcs_first_place_next:
                            for var in variable_in_arcs:
                              if var.startswith("m_"):
                                arc.variable.add(var)
                                break

                        # Update arcs
                        new_arcs = set()
                        for t in pre_trans:
                            if t in pre_trans_mapping:
                                in_arc = Arc(pre_trans_mapping[t], t, first_place_next)
                                t.add_post_place(first_place_next)
                                first_place_next.add_in_arc(in_arc)
                                new_arcs.add(in_arc)
                            elif t in pre_trans_mapping_loop:
                                out_arc = Arc(pre_trans_mapping_loop[t], first_place_next, t)
                                t.add_pre_place(first_place_next)
                                first_place_next.add_out_arc(out_arc)
                        self.arcs.update(new_arcs)
                        for arc in self.arcs:
                            if arc.source == first_place_next:
                                arc.set_variable(combined_variable)

                    else:
                        # Connect two nets
                        new_arcs = set()
                        for t in pre_trans:
                            if t in pre_trans_mapping:
                                in_arc = Arc(pre_trans_mapping[t], t, first_place_next)
                                t.add_post_place(first_place_next)
                                first_place_next.add_in_arc(in_arc)
                                new_arcs.add(in_arc)
                            elif t in pre_trans_mapping_loop:
                                out_arc = Arc(pre_trans_mapping_loop[t], first_place_next, t)
                                t.add_post_place(first_place_next)
                                first_place_next.add_out_arc(out_arc)
                                new_arcs.add(out_arc)
                        self.arcs.update(new_arcs)

                    arcs_first_place_current = {arc for arc in self.arcs if arc.target == first_place_current or arc.source == first_place_current}
                    variable_first_place_current = {
                        variable
                        for arc in arcs_first_place_current
                        for variable in arc.variable
                    }
                    # Extract elements starting with "m_"
                    message_exchange = {elem for elem in variable_first_place_current if elem.startswith("m_")}

                    if message_exchange:
                      # Find all arcs reachable from first_place_next (BFS traversal)
                      visited = set()
                      queue = [first_place_next]
                      while queue:
                        current_place = queue.pop(0)
                        if current_place in visited:
                          continue
                        visited.add(current_place)
                        # Get all outgoing arcs from current node
                        outgoing_arcs = {arc for arc in self.arcs if arc.source == current_place}
                        for arc in outgoing_arcs:
                            # Add message variables to this arc
                            arc.variable.update(message_exchange)
                            transition = arc.target
                            # Find all outgoing arcs from this transition (must go to places)
                            for next_arc in (arc for arc in self.arcs if arc.source == transition):
                                next_arc.variable.update(message_exchange)

                                # Add the target place to queue
                                queue.append(next_arc.target)


                else:
                    raise ValueError(f"t-JN is not complete, failing end place.")


    def append_xor(self, name, *children):
        if not children:
            return
        # self.operator = Operator.XOR
        shared_start = Place(f"{name}_xor_start", None)  # tx_xor_start
        shared_end = Place(f"{name}_xor_end", None)
        self.first_place = shared_start
        self.last_place = shared_end
        self.places[f'{name}_xor_start'] = shared_start
        self.places[f'{name}_xor_end'] = shared_end

        for child in children:
            # print("Current Children:")
            # child.print_net()
            if len(child.transitions) == 1 and 'tau' in next(iter(child.transitions)):
                continue
            self.children.add(child)
            for place_name, place in child.places.items():
                if place_name not in self.places:
                    self.places[place_name] = place
                else:
                    # Merge types if place exists
                    self.places[place_name].add_types(place.get_types())
            for name, trans in child.transitions.items():
                # Add all transitions of the child to the net
                self.transitions[name] = trans

            # Add all arcs of the child to the net
            self.arcs.update(child.arcs)

            first_place = child.first_place
            last_place = child.last_place

            # Get first transitions and their input variables
            first_transitions = {arc.target: arc.variable for arc in child.arcs
                                 if arc.source == first_place
                                 and isinstance(arc.target, Transition)}

            # Get last transitions and their input variables
            last_transitions = {arc.source: arc.variable for arc in child.arcs
                                if arc.target == last_place
                                and isinstance(arc.source, Transition)}

            if first_place and last_place:
                if first_place.name != f'{name}_xor_start' and last_place.name != f'{name}_xor_end':
                    # Remove initial start & end places
                    self.remove_place(first_place.name)
                    self.remove_place(last_place.name)

                for t, var in first_transitions.items():
                    arc_out = Arc(var, shared_start, t)
                    self.arcs.add(arc_out)
                    shared_start.add_out_arc(arc_out)
                    shared_start.add_types(var)
                    t.add_pre_place(shared_start)

                for t, var in last_transitions.items():
                    arc_in = Arc(var, t, shared_end)
                    self.arcs.add(arc_in)
                    shared_end.add_in_arc(arc_in)
                    shared_end.add_types(var)
                    t.add_post_place(shared_end)
            else:

                raise ValueError(f"t-JN is not complete, failing start/end place. First Place: {first_place}, Last Place: {last_place}")
            

    def append_parallel(self, name, *children):
        if not children:
            return
        # self.operator = Operator.PARALLEL
        start_tau = create_tau(f"{name}_tau_start")
        end_tau = create_tau(f"{name}_tau_end")
        self.first_place = start_tau.first_place
        self.last_place = end_tau.last_place

        for place_name, place in start_tau.places.items():
            if place_name not in self.places:
                self.places[place_name] = place
        for place_name, place in end_tau.places.items():
            if place_name not in self.places:
                self.places[place_name] = place

        for name, trans in start_tau.transitions.items():
            self.transitions[name] = trans
        for name, trans in end_tau.transitions.items():
            self.transitions[name] = trans

        # Add all arcs of the child to the net
        self.arcs.update(start_tau.arcs)
        self.arcs.update(end_tau.arcs)

        first_places = set()
        last_places = set()
        combined_variable = set()

        for child in children:
            self.children.add(child)
            for place_name, place in child.places.items():
                combined_variable.update(place.get_types())
                if place_name not in self.places:
                    self.places[place_name] = place
                else:
                    # Merge types if place exists
                    self.places[place_name].add_types(place.get_types())
            for name, trans in child.transitions.items():
                # Add all transitions of the child to the net
                self.transitions[name] = trans

            # Add all arcs of the child to the net
            self.arcs.update(child.arcs)

            first_places.add(child.get_first_place())
            last_places.add(child.get_last_place())


        # Get the only transition of start_tau
        start_tau_trans = next(iter(start_tau.transitions.values()))
        end_tau_trans = next(iter(end_tau.transitions.values()))


        # Adjust arc types
        for arc in self.arcs:
            if arc.target == start_tau_trans or arc.source == end_tau_trans:
                arc.set_variable(combined_variable)

        # Connect start_tau to all first_places
        for place in first_places:
            arc = Arc(combined_variable, start_tau_trans, place)
            self.arcs.add(arc)
            place.add_in_arc(arc)

        # Connect end_tau to all last_places
        for place in last_places:
            arc = Arc(combined_variable, place, end_tau_trans)
            self.arcs.add(arc)
            place.add_out_arc(arc)

        # Remove arcs to last_place of start_tau and arcs from start_place of end_tau
        start_place_end_tau = end_tau.get_first_place()
        end_place_start_tau = start_tau.get_last_place()
        self.remove_place(start_place_end_tau.name)
        self.remove_place(end_place_start_tau.name)

        # print("All arcs after parallel append: ")
        # for arc in self.arcs:
        #     print(f"Arc: {arc.source.name} -> {arc.target.name}")
        #     print(f"Variable: {arc.variable}")


    def append_loop(self, *children):
        if not children:
            return
        # self.operator = Operator.LOOP
        for child in children:
            self.children.add(child)
            for place_name, place in child.places.items():
                if place_name not in self.places:
                    print(f"Add {place_name} to current net.")
                    self.places[place_name] = place
                else:
                    # Merge types if place exists
                    self.places[place_name].add_types(place.get_types())
            for name, trans in child.transitions.items():
                # Add all transitions of the child to the net
                self.transitions[name] = trans

            # Add all arcs of the child to the net
            self.arcs.update(child.arcs)

        if len(children) > 1:
            for i in range(len(children) - 1):
                current_net = children[i]
                print("Current net:")
                current_net.print_net()
                next_net = children[i + 1]
                print("Next_net: ")
                next_net.print_net()

                # Get the first & last place of current net and first place of next net
                first_place_current = current_net.first_place
                last_place_current = current_net.last_place
                first_place_next = next_net.first_place
                last_place_next = next_net.last_place

                # Set first & last place of the net
                self.first_place = first_place_current
                self.last_place = first_place_next

                if first_place_current and last_place_current and first_place_next and last_place_next:
                    # Find arcs whose target is last_place_current and extract arc variables
                    arcs_last_place_current = {arc for arc in self.arcs if arc.target == last_place_current}
                    variable_in_arcs = {
                        variable
                        for arc in arcs_last_place_current
                        for variable in arc.variable
                    }

                    # Find arcs whose source is first_place_next and extract the variables
                    arcs_first_place_next = {arc for arc in self.arcs if arc.source == first_place_next}
                    variable_loop_in = {
                        variable
                        for arc in arcs_first_place_next
                        for variable in arc.variable
                    }

                    # Find arcs whose target is last_place_next and extract the variables
                    arcs_last_place_next = {arc for arc in self.arcs if arc.target == last_place_next}
                    variable_loop_out = {
                        variable
                        for arc in arcs_last_place_next
                        for variable in arc.variable
                    }

                    pre_trans = {arc.source for arc in arcs_last_place_current}
                    post_trans = {arc.target for arc in arcs_first_place_next}
                    final_trans_of_next_net = {arc.source for arc in arcs_last_place_next}

                    # Remove last place of the current child
                    self.remove_place(last_place_current.name)

                    # Close the loop by connecting the last transition to the first place of current net
                    loop_arc = set()
                    for t in final_trans_of_next_net:
                        loop_arc.add(Arc(variable_loop_out, t, first_place_current))
                        t.add_post_place(first_place_current)
                    self.arcs.update(loop_arc)

                    # Remove last place of next child and its arcs
                    self.remove_place(last_place_next.name)

                    # update arcs
                    if variable_in_arcs != variable_loop_in:
                        emit = variable_loop_in - variable_in_arcs
                        collect = variable_in_arcs - variable_loop_in
                        for t in pre_trans:
                            t.set_emit(emit)
                        for t in post_trans:
                            t.set_collect(collect)

                        # Update arcs
                        combined_variable = variable_in_arcs.union(variable_loop_in)
                        new_arcs = set()
                        for t in pre_trans:
                            in_arc = Arc(combined_variable, t, first_place_next)
                            first_place_next.add_in_arc(in_arc)
                            new_arcs.add(in_arc)
                            t.add_post_place(first_place_next)

                        self.arcs.update(new_arcs)
                        for arc in self.arcs:
                            if arc.source == first_place_next:
                                arc.set_variable(combined_variable)

                    else:
                        # Connect two nets by creating new arcs
                        new_arcs = set()
                        for t in pre_trans:
                          new_arc = Arc(variable_in_arcs, t, first_place_next)
                          t.add_post_place(first_place_next)
                          first_place_next.add_in_arc(new_arc)
                          new_arcs.add(new_arc)
                        self.arcs.update(new_arcs)

                else:
                    raise ValueError(f"t-JN is not complete, failing start/end place.")

def create_tau(name: str) -> TypedJacksonNet:
    """
    Constructs a Typed Jackson Net (t-JN) containing a τ-transition
    """
    tjn = TypedJacksonNet()

    # Create places
    first_place = Place(f"{name}_pstart")
    last_place = Place(f"{name}_pend")
    tjn.add_place(first_place)
    tjn.add_place(last_place)
    tjn.first_place = first_place
    tjn.last_place = last_place

    # Define tau transition inscription (no variables)
    inscription = {
        "input": set(),  # No input variables
        "output": set()  # No output variables
    }

    tjn.add_transition(name, inscription, pre={first_place}, post={last_place})

    return tjn


def build_tjn_from_pm4py_tree(tree: ProcessTree, activity_specs, operator=None):
    tjn = TypedJacksonNet()
    if tree.operator is None:  # leaf node
        name = tree.label
        agents = activity_specs.get(name, set())
        pre_place = Place(f"{name}_pre", agents)
        post_place = Place(f"{name}_post", agents)
        inscription = {
            "input": agents,
            "output": agents
        }
        tjn.add_place(pre_place, agents)
        tjn.add_place(post_place, agents)
        tjn.first_place = pre_place
        tjn.last_place = post_place
        tjn.add_transition(name, inscription, {pre_place}, {post_place})
        # Add guard
        # guard = " and ".join([f"{agent.replace(' ', '_')}_available" for agent in agents])
        return tjn
    elif tree.operator.name == 'SEQUENCE':
        nets = [build_tjn_from_pm4py_tree(child, activity_specs) for child in tree.children]
        # print(f"{len(nets)} sequence nets:")
        # for net in nets:
        #     net.print_net()

        main = TypedJacksonNet()
        main.append_sequence(*nets)

        # Set first and last places correctly
        if nets:  # only if there are nets in the sequence
            main.first_place = nets[0].first_place
            main.last_place = nets[-1].last_place
            # print(f"Sequence append: set first place to {main.first_place.name}, last place to {main.last_place.name}")

        # print(f"Sequence append final result: ")
        # main.print_net()
        return main

    elif tree.operator.name == 'PARALLEL':
        nets = [build_tjn_from_pm4py_tree(child, activity_specs) for child in tree.children]
        name = ''
        # print("Parallel nets:")
        for net in nets:
            # Unique name for the tau transition
            name = next(iter(net.arcs)).source.name
            # net.print_net()
        main = TypedJacksonNet()
        main.append_parallel(name, *nets)
        return main
    elif tree.operator.name == 'XOR':
        nets = [build_tjn_from_pm4py_tree(child, activity_specs) for child in tree.children]
        name = ''
        # print("XOR nets:")
        for net in nets:
            # Unique name for the xor places
            name = next(iter(net.arcs)).source.name

        main = TypedJacksonNet()
        main.append_xor(name, *nets)
        return main

    elif tree.operator.name == 'LOOP':
        nets = [build_tjn_from_pm4py_tree(child, activity_specs) for child in tree.children]
        # print("LOOP nets:")
        # for net in nets:
        #     net.print_net()

        main = TypedJacksonNet()
        main.append_loop(*nets)
        return main
    else:
        for child in tree.children:
            build_tjn_from_pm4py_tree(child, tjn, activity_specs)


def build_tjn(tree: ProcessTree, activity_specs, operator=None):
    """
    Build the typed jackson net from a process tree and set first- and last places.
    """
    tjn = build_tjn_from_pm4py_tree(tree, activity_specs, operator)
    if tjn.get_first_place() is None:
        # Find place with no incoming arcs
        for _, place in tjn.places.items():
            if not place.in_arcs:
                tjn.first_place = place
                break

    if tjn.get_last_place() is None:
        # Find place with no incoming arcs
        for _, place in tjn.places.items():
            if not place.out_arcs:
                tjn.last_place = place
                break
    return tjn


def create_resource_mapping(log):
    """
    Creates a mapping from activity names to org:resource values.
    Additionally, for activities containing "!" or "?", adds a synthetic
    resource based on the message name:
        - "a!_1" or "a?_1" → resource "m_a1"
        - "a!" or "a?"     → resource "m_a"
    Sample output:
        {
            't1': ('Agent 1',),
            'e1': ('Agent 2',),
            'a!_1': ('Agent 1', 'm_a1'),
            'a?': ('Agent 2', 'm_a')
        }
    """
    resource_mapping = defaultdict(set)

    for trace in log:
        for event in trace:
            activity = event.get('concept:name')
            resource = event.get('org:resource') if event.get('org:resource') else event.get('org:group')
            if activity:
                if resource is not None:
                    resource_mapping[activity].add(resource)
                else:
                     resource_mapping[activity]

                # Add synthetic resource for message activities
                if '!' in activity or '?' in activity:
                    # Extract base name (before ! or ?)
                    base = activity.split('!')[0].split('?')[0]
                    # Extract suffix only if _ exists (e.g., "a!_1" → "1")
                    suffix = activity.split('_')[-1] if '_' in activity else ''
                    # Construct synthetic resource with "m_" prefix
                    synthetic_resource = f"m_{base}{suffix}" if suffix else f"m_{base}"
                    resource_mapping[activity].add(synthetic_resource)
                
    return dict(resource_mapping)


def send_receive_message(log):
    """
    Simulates the sending and receiving of messages between agents.
    """
    messages = {}
    for trace in log:
        for event in trace:
            activity = event.get('concept:name')
            sent = event.get('Message:Sent') if (event.get('Message:Sent') and event.get('Message:Sent') != "null") else None
            rec = event.get('Message:Rec') if (event.get('Message:Rec') and event.get('Message:Rec') != "null") else None
            if sent:
                # Simulate sending a message
                if sent not in messages:
                    messages[sent] = {'sent_by': [], 'received_by': []}
                messages[sent]['sent_by'].append(activity) 
            if rec:
                # Simulate receiving a message
                if rec not in messages:
                    messages[rec] = {'sent_by': [], 'received_by': []}
                messages[rec]['received_by'].append(activity)
    return messages


# Filtering the net by the value of the "Agent" attribute to get a sub-net.
def filter_net_by_resource(
        net: TypedJacksonNet,
        resource: str,
        resource_mapping: Dict[str, Set[str]]
) -> TypedJacksonNet:
    """
    Filters a TypedJacksonNet to create a subnet containing only elements
    relevant to the specified resource (arc type), considering the resource mapping.

    Args:
        net: The original TypedJacksonNet to filter
        resource: The resource/agent attribute to filter by (arc type)
        resource_mapping: Dictionary mapping transition names to sets of resources

    Returns:
        A new TypedJacksonNet containing only places, transitions, and arcs
        that involve the specified resource and are connected to transitions
        listed in the resource mapping for that resource
    """
    subnet = TypedJacksonNet()

    # Get transitions relevant for this resource
    relevant_transitions = {
        trans_name for trans_name, resources in resource_mapping.items()
        if resource in resources
    }

    # Find all arcs that:
    # 1. Involve the specified resource in their variable, AND
    # 2. Are connected to a transition in relevant_transitions
    relevant_arcs = set()
    for arc in net.arcs:
        if resource in arc.variable:
            # Check if arc is connected to a relevant transition
            if (isinstance(arc.source, Transition) and arc.source.name in relevant_transitions) or \
                    (isinstance(arc.target, Transition) and arc.target.name in relevant_transitions):
                relevant_arcs.add(arc)

    # Collect all nodes connected by these arcs
    relevant_nodes = set()
    for arc in relevant_arcs:
        relevant_nodes.add(arc.source)
        relevant_nodes.add(arc.target)

    # Also include transitions that are in relevant_transitions (they might not have arcs)
    for trans_name in relevant_transitions:
        if trans_name in net.transitions:
            relevant_nodes.add(net.transitions[trans_name])

    # Add relevant places to subnet
    for node in relevant_nodes:
        if isinstance(node, Place):
            subnet.add_place(node, node.get_types())
            # Update first/last place if needed
            if net.first_place and node.name == net.first_place.name:
                subnet.first_place = node
            if net.last_place and node.name == net.last_place.name:
                subnet.last_place = node

    # Add relevant transitions to subnet
    for node in relevant_nodes:
        if isinstance(node, Transition) and node.name in relevant_transitions:
            # Reconstruct pre and post sets for the transition in the subnet context
            pre_places = {p for p in node.pre if p in relevant_nodes}
            post_places = {p for p in node.post if p in relevant_nodes}

            subnet.add_transition(
                name=node.name,
                inscription=node.inscription,
                pre=pre_places,
                post=post_places
            )

    # Add the relevant arcs to subnet
    subnet.arcs.update(relevant_arcs)

    # Copy children if they're relevant to this resource
    for child in net.children:
        filtered_child = filter_net_by_resource(child, resource, resource_mapping)
        if filtered_child.places or filtered_child.transitions:
            subnet.children.add(filtered_child)

    return subnet


# Convert tjn to petri net for conformance checking
def convert_tjn_to_petri_ignore_types(tjn_model) -> Tuple[PetriNet, Marking, Marking]:
    net = PetriNet("TJN_Without_Types")
    place_map = {}
    transition_map = {}

    # Step 1: Create Places
    for place_name, place in tjn_model.places.items():
        pn_place = PetriNet.Place(place_name)
        net.places.add(pn_place)
        place_map[place_name] = pn_place

    # Step 2: Create Transitions and Arcs
    for trans_name, trans in tjn_model.transitions.items():
        # Tau transitions have label=None
        is_silent = (trans_name is None or
                     "tau" in trans_name.lower() or
                     "_tau_" in trans_name.lower())
        transition_label = None if is_silent else trans_name

        # Internal ID remains original
        pn_trans = PetriNet.Transition(name = trans_name, label = transition_label)
        net.transitions.add(pn_trans)
        transition_map[trans_name] = pn_trans


    # Step 3: Add Arcs (AFTER all places/transitions are created)
    for arc in tjn_model.arcs:
        # Get PM4Py objects from mappings
        source = place_map.get(arc.source.name) if isinstance(arc.source, Place) else transition_map.get(
            arc.source.name)
        target = place_map.get(arc.target.name) if isinstance(arc.target, Place) else transition_map.get(
            arc.target.name)
        if source and target:
            add_arc_from_to(source, target, net)  # Now uses PM4Py objects with out_arcs/in_arcs

    # Step 3: Define initial and final markings
    initial_marking = Marking()
    final_marking = Marking()

    print(f"First place of tjn model: {tjn_model.first_place.name}, last place of tjn model: {tjn_model.last_place.name}")

    if tjn_model.first_place:
        initial_marking[place_map[tjn_model.first_place.name]] = 1
    if tjn_model.last_place:
        final_marking[place_map[tjn_model.last_place.name]] = 1

    return net, initial_marking, final_marking


def get_all_resources(log):
    """
    Extracts all unique resources (values of 'org:resource') from the log.
    :param log: PM4Py event log (list of traces, each trace is a list of event dicts)
    :return: set of unique resources
    """
    resources = set()
    for trace in log:
        for event in trace:
            res = event.get("org:resource") if event.get("org:resource") else event.get("org:group")
            if res is not None:
                resources.add(res)
    return resources


def filter_log_by_resource(log, resource: str):
    """Safely filters a log by org:resource, checking if the attribute exists."""
    if not log or not log[0]:
        raise ValueError("Empty log or trace!")
    
    # Determine which resource key is present
    first_event = log[0][0]
    if "org:resource" in first_event:
        resource_key = "org:resource"
    elif "org:group" in first_event:
        resource_key = "org:group"
    else:
        raise ValueError("'org:resource' or 'org:group' not found in the log!")
        
    # Proceed with filtering
    filtered_log = pm4py.filter_event_attribute_values(
        log,
        xes.DEFAULT_RESOURCE_KEY,
        [resource],
        level="event"  # or "trace" for whole traces
    )
    return filtered_log


def remove_arc_from_to(net, a, b):
    """
    Remove a specific arc from 'a' to 'b' in the Petri net.
    'a' and 'b' must be Place/Transition objects already in the net.
    """
    for arc in list(net.arcs):  # make a copy to avoid modifying while iterating
        if arc.source == a and arc.target == b:
            net.arcs.remove(arc)
            # Also remove from source and target adjacency
            if arc in a.out_arcs:
                a.out_arcs.remove(arc)
            if arc in b.in_arcs:
                b.in_arcs.remove(arc)
            break  # stop after removing one


def remove_tau_splits_and_joins_tjn(tjn: TypedJacksonNet):
    """
    Removes silent transitions that have either:
    - 1 input place and multiple output places (split), or
    - Multiple input places and 1 output place (join)

    Rewires arcs accordingly:
    - For splits: predecessors of input place → all output places
    - For joins: all input places → successors of output place
    :param net:
    :return:
    """
    # tjn = copy.deepcopy(typed_JN)
    initial_place = tjn.get_first_place()
    final_place = tjn.get_last_place()
    to_remove = []

    for t_name, t in tjn.transitions.items():
        if t_name is None or "tau" in t_name.lower() or "_tau_" in t_name.lower():

            # Case 1: Split (1 input, multiple outputs)
            if len(t.pre) == 1 and len(t.post) > 1:
                input_place = next(iter(t.pre))

                if input_place is not initial_place:
                    predecessors = [a.source for a in input_place.in_arcs]

                    if len(predecessors) == 1:
                        # Whether input place has direct transition successors
                        # If not, remove all the incoming and outgoing arcs, and delete the input place afterward
                        
                        succ_transitions = [a.target for a in input_place.out_arcs
                                            if a.target.name != t_name]
                        remove_post = True

                        if len(succ_transitions) > 0:  # True if there is at least one other successor transition
                            remove_post = False
                            tjn.remove_arc_from_to(input_place, t)
                        else:
                            # Succ_transition only contains silent transition
                            for arc in list(input_place.in_arcs) + list(input_place.out_arcs):
                                if arc in tjn.arcs:
                                    tjn.arcs.remove(arc)
                                if input_place in tjn.places.values():
                                    tjn.places.pop(input_place.name)

                        # Remove transition t and its arcs
                        vars = set()
                        for p in list(t.post):
                            var = tjn.remove_arc_from_to(t, p)
                            vars.update(var)

                        # Connect predecessor transition to all output places
                        for p in list(t.post):
                            tjn.add_arc_from_to(predecessors[0], p, vars)
                            if remove_post:
                                predecessors[0].post.discard(p)
                        to_remove.append(t_name)
                        t.pre = set()
                        t.post = set()


            # Case 2: Join (multiple inputs, 1 output)
            elif len(t.pre) > 1 and len(t.post) == 1:
                output_place = next(iter(t.post))

                if output_place is not final_place:
                    successors = [a.target for a in output_place.out_arcs if isinstance(a.target, Transition)]
                    
                    if len(successors) == 1:
                        pred_transitions = [a.source for a in output_place.in_arcs
                                            if isinstance(a.source, Transition) and a.source.name != t_name]
                        discard_output = True

                        if len(pred_transitions) > 0:  # True if there is at least one other predecessor transition
                            discard_output = False
                            tjn.remove_arc_from_to(t, output_place)
                        else:
                            for arc in list(output_place.in_arcs) + list(output_place. out_arcs):
                                if arc in tjn.arcs:
                                    tjn.arcs.remove(arc)
                                if output_place in tjn.places.values():
                                    tjn.places.pop(output_place.name)

                        # Remove transition t and its arcs
                        vars = set()
                        for p in list(t.pre):
                            var = tjn.remove_arc_from_to(p, t)
                            vars.update(var)
                        for p in list(t.pre):
                            tjn.add_arc_from_to(p, successors[0], vars)
                            for pre in successors[0].pre:
                                print(f" - {pre.name}")
                            if discard_output:
                                successors[0].pre.discard(output_place)

                        to_remove.append(t_name)
                        t.pre = set()
                        t.post = set()

    for t_name in to_remove:
        tjn.transitions.pop(t_name)

    return tjn


def remove_tau_splits_and_joins_pn(net: PetriNet, initial_marking: Marking, final_marking: Marking):
    """
    Removes silent transitions that have either:
    - 1 input place and multiple output places (split), or
    - Multiple input places and 1 output place (join)

    Rewires arcs accordingly:
    - For splits: predecessors of input place → all output places
    - For joins: all input places → successors of output place
    :param net:
    :return:
    """
    to_remove = []
    initial_place = next(iter(initial_marking.keys()))
    final_place = next(iter(final_marking.keys()))

    for t in list(net.transitions):
        if t.label is None:
            in_places = [a.source for a in t.in_arcs if isinstance(a.source, PetriNet.Place)]
            out_places = [a.target for a in t.out_arcs if isinstance(a.target, PetriNet.Place)]

            # Case 1: Split (1 input, multiple outputs)
            if len(in_places) == 1 and len(out_places) > 1:
                input_place = in_places[0]

                if input_place is not initial_place:
                    predecessors = [a.source for a in input_place.in_arcs if isinstance(a.source, PetriNet.Transition)]
                    if len(predecessors) == 1:
                        # Whether input place has direct transition successors, if no, remove all the incoming and
                        # outgoing arcs, and delete the input place afterward
                        succ_transitions = [a.target for a in input_place.out_arcs
                                            if isinstance(a.target, PetriNet.Transition) and a.target != t]

                        if len(succ_transitions) > 0:  # True if there is at least one other successor transition
                            remove_arc_from_to(net, input_place, t)
                        else:
                            for arc in list(input_place.in_arcs) + list(input_place.out_arcs):
                                if arc in net.arcs:
                                    net.arcs.remove(arc)
                                if input_place in net.places:
                                    net.places.remove(input_place)

                        # Connect predecessor transition to all output places
                        for p in out_places:
                            add_arc_from_to(predecessors[0], p, net)
                        to_remove.append(t)

            # Case 2: Join (multiple inputs, 1 output)
            elif len(in_places) > 1 and len(out_places) == 1:
                output_place = out_places[0]

                if output_place is not final_place:
                    successors = [a.target for a in output_place.out_arcs if isinstance(a.target, PetriNet.Transition)]

                    if len(successors) == 1:
                        pred_transitions = [a.source for a in output_place.in_arcs
                                            if isinstance(a.source, PetriNet.Transition) and a.source != t]

                        if len(pred_transitions) > 0:  # True if there is at least one other predecessor transition
                            remove_arc_from_to(net, t, output_place)
                        else:
                            for arc in list(output_place.in_arcs) + list(output_place. out_arcs):
                                if arc in net.arcs:
                                    net.arcs.remove(arc)
                                if output_place in net.places:
                                    net.places.remove(output_place)
                        # Connect all input places to each successor transition
                        for p in in_places:
                            add_arc_from_to(p, successors[0], net)
                    to_remove.append(t)

    # Actually remove transitions and their arcs
    for t in to_remove:
        for arc in list(t.in_arcs) + list(t.out_arcs):
            if arc in net.arcs:
                net.arcs.remove(arc)
        if t in net.transitions:
            net.transitions.remove(t)


# Find all resources and convert to tjn by each of the resources
def convert_to_tjn_by_resource(log_path):
    log_name = log_path.removesuffix(".xes")
    log = xes_importer.apply(os.path.join(PROJECT_DIR, "logs", log_path))
    tjn_full = None
    pn_full = {}
    tjns = {}
    pns = {}
    all_resources = get_all_resources(log)
    print(f"All resources in the log: {all_resources}")
    logs_by_resource = {}
    tree_full = inductive_miner.apply(log)
    resource_mapping = create_resource_mapping(log)
    tjn_full = build_tjn(tree_full, activity_specs=resource_mapping)
    tjn_full.populate_transition_places()         
    tjn_full = remove_tau_splits_and_joins_tjn(tjn_full)
    tjn_full.populate_transition_places()
    messages = send_receive_message(log)
    tjn_full.annotate_arcs_with_messages(messages)

    # Remove transitions with no in_arcs and out_arcs
    to_remove = [t_name for t_name, t in tjn_full.transitions.items() if not t.in_arcs and not t.out_arcs]
    for t_name in to_remove:
        tjn_full.transitions.pop(t_name)

    pn, initial_marking, final_marking = convert_tjn_to_petri_ignore_types(tjn_full)
    pn_full["pn"] = pn
    pn_full["initial_marking"] = initial_marking
    pn_full["final_marking"] = final_marking

    # Visualize the full Petri net
    filename = os.path.join(PROJECT_DIR, "logs", "pngs", f"full_{log_name}.png")
    if not os.path.exists(filename):
        gviz = pn_visualizer.apply(pn, initial_marking, final_marking)
        pn_visualizer.save(gviz, filename)

    if len(all_resources) > 1:
        for res in all_resources:
            if "collective" in log_name:
                # For collective logs, use the existing sublog
                sublog_path = os.path.join(PROJECT_DIR, "logs", "sublog", f"sub_log_{res}_{log_name}.xes")
                logs_by_resource[res] = xes_importer.apply(sublog_path)
            else:
                logs_by_resource[res] = filter_log_by_resource(log, res)
                # Save the sublog
                sublog_path = os.path.join(PROJECT_DIR, "logs", "sublog", f"sub_log_{res}_{log_name}.xes")
            
            if not os.path.exists(sublog_path):
                xes_exporter.apply(logs_by_resource[res], sublog_path)
    else:
        logs_by_resource["No resource"] = log

    # Convert each sublog to tjn
    for resource, sub_log in logs_by_resource.items():
        resource_mapping = create_resource_mapping(sub_log)
        tree = inductive_miner.apply(sub_log)
        tjn = build_tjn(tree, activity_specs=resource_mapping)
        tjn.populate_transition_places()
        for place in tjn.places.values():
            place.add_types(resource)
        tjns[resource] = remove_tau_splits_and_joins_tjn(tjn)


    # Convert tjn to petri nets and remove unnecessary silent transitions
    for resource, tjn in tjns.items():
        converted_filterd_pn, initial_marking, final_marking = convert_tjn_to_petri_ignore_types(tjn)
        pns[resource] = (converted_filterd_pn, initial_marking, final_marking)
        print(f"Initial marking: {initial_marking}, Final marking: {final_marking}")
        # Visualize the Petri net
        filename = os.path.join(PROJECT_DIR, "logs", "pngs", f"{resource}_{log_name}.png")

        if not os.path.exists(filename):
            gviz = pn_visualizer.apply(converted_filterd_pn, initial_marking, final_marking)
            pn_visualizer.save(gviz, filename)

    return tjn_full, pn_full, all_resources, logs_by_resource, tjns, pns


def check_property(petri_nets):
    for pn, initial_marking, final_marking in petri_nets.values():
        # 1. First check if it's a workflow net
        is_wfn = wfn_algorithm.apply(pn)

        if is_wfn:
            print("The net is a workflow net")
            # Workflow-specific analysis
            from pm4py.algo.analysis.woflan import algorithm as woflan

            is_sound = woflan.apply(pn, initial_marking, final_marking)
            print(f"Soundness: {is_sound}")
        else:
            print("The net is a general Petri net (not a workflow net)")
            # Perform general Petri net analysis instead
            from pm4py.algo.analysis.extended_marking_equation import algorithm as extended_marking

            diagnostics = extended_marking.apply(pn, initial_marking, final_marking)
            if diagnostics["is_sound"]:
                print("The net is sound (despite not being a workflow net)")
            else:
                print("Potential issues detected:")
                print(f"Dead transitions: {diagnostics['dead_transitions']}")
                print(f"Unreachable final markings: {diagnostics['unreachable_markings']}")


def precision_and_fitness(resource, petri_nets, logs, log_path):
    results = {}
    log_name = log_path
    if ".xes" in log_path:
        log_name = log_path.replace(".xes", "")

    if resource == "No resource":
        pn, initial_marking, final_marking = petri_nets["pn"], petri_nets["initial_marking"], petri_nets["final_marking"]
        log = xes_importer.apply(os.path.join(PROJECT_DIR, "logs", log_path))
    else:
        pn, initial_marking, final_marking = petri_nets[resource]
        log = logs[resource]
    
    path_pnml = os.path.join(PROJECT_DIR, "logs", "pnmls", f"{resource}_{log_name}.pnml")
    if not os.path.exists(path_pnml):
        pnml_exporter.apply(pn, initial_marking, path_pnml, final_marking=final_marking)
    # Convert back to petri net, pm4py ensures the Petri net is in a “sound” format suitable for alignments.
    pn = pm4py.read_pnml(path_pnml)
    # Alignment based fitness and precision
    alignment_fitness, alignment_precision = 0.0, 0.0
    try:
        alignment_fitness = pm4py.fitness_alignments(log, *pn)['averageFitness']
        alignment_precision = pm4py.precision_alignments(log, *pn)
    except Exception as e:
        print(f"Error computing alignment metrics for {resource}: {e}")
    print(f"Alignment-based Fitness for resource {resource}: {alignment_fitness}, and precision {alignment_precision}")

    # Entropy based fitness and precision
    jar_path = "lib/jbpt/jbpt-pm/entropia/jbpt-pm-entropia-1.7.jar"

    if resource == "No resource":
        sublog_path = os.path.join(PROJECT_DIR, "logs", f"{log_name}.xes")
    else:
        sublog_path = os.path.join(PROJECT_DIR, "logs", "sublog", f"sub_log_{resource}_{log_name}.xes")

    entropy_fitness, entropy_precision = 0.0, 0.0
    print(f"Does sublog path and pnml path exists? -> {os.path.exists(sublog_path)}, {os.path.exists(path_pnml)}")
    print(f"Log path and pmnl for entropy fitness and precision: {sublog_path}, {path_pnml}")
    command = [
        "java", "-jar", jar_path,
        "-rel", sublog_path,
        "-ret", path_pnml,
        "-empr"  # Compute precision
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            print("Error running Entropia:\n", result.stderr)
        else:
            output = result.stdout
            precision = recall = None

            # Extract values
            for line in output.splitlines():
                if line.strip().startswith("Precision:"):
                    precision = float(line.split(":")[1].strip().rstrip('.'))
                elif line.strip().startswith("Recall:"):
                    recall = float(line.split(":")[1].strip().rstrip('.'))

            entropy_fitness = recall if recall is not None else 0.0
            entropy_precision = precision if precision is not None else 0.0
            print(f"Entropy-based fitness: {entropy_fitness}")
            print(f"Entropy-based recall: {entropy_precision}")
    except Exception as e:
        print(f"Error computing entropy metrics for {resource}: {e}")
        
    # Store metrics per resource
    results[resource] = {
        "alignment_fitness": alignment_fitness,
        "alignment_precision": alignment_precision,
        "entropy_fitness": entropy_fitness,
        "entropy_precision": entropy_precision
    }
    
    return results




