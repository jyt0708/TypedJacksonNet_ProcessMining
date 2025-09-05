# TypedJacksonNet_ProcessMining

A web-based visualizer for **Typed Jackson Nets (TJNs)**.
It loads event logs (`.xes`), constructs Petri nets, and provides interactive visualization with **fitness & precision metrics**.

---

## ✨ Features
- Load `.xes` event logs and generate corresponding Petri Nets.
- Filter transitions by resource.
- Visualize Petri Net structure interactively (pan & zoom).
- Inspect places, transitions, and arcs by clicking on them.
- Export the current net as:
  - **SVG** (graph snapshot)
  - **PNML** (Petri Net Markup Language)
- Compute **fitness & precision** metrics (alignment-based and entropy-based).

---

## 📦 Requirements
- **Python/Flask backend** (serving logs, metrics, and net generation).
- Modern browser (Chrome/Firefox/Edge).

---

## 🔧 Installation and downloading Event Logs

Clone the repository **with submodules** to include JBPT:

```bash
git clone --recurse-submodules https://github.com/jyt0708/TypedJacksonNet_ProcessMining.git 
cd <your-repo>
```

The `.xes` logs are **not included in the repository** (due to GitHub’s file size limits).  
Instead, they are available for download from GitHub Releases.

👉 [Download Logs from Releases](https://github.com/jyt0708/TypedJacksonNet_ProcessMining/releases/latest)

### Folder Structure

After downloading, place the logs into the following structure:

```csharp

logs/
  ├── EM_Log.xes
  ├── SD_Log.xes
  ├── FP_Log.xes
  ├── ID_Log.xes
  ├── ... (other .xes log files)
  ├── pngs/           # empty
  ├── pnmls/          # empty
  └── sublog/
      ├── sub_log_PartyA_collectivelog_1.xes
      └── sub_log_PartyA_collectivelog_2.xes
      └── ... (other .xes log files)
```
---

## ▶️ Usage
- Start the backend server:

```bash
python app.py
```


## 📂Repository Structure
```csharp
.
├── app.py                # Flask backend
├── logs/                 # Sample XES logs
    └── pngs/
    └── pnmls/
    └── sublog/             
├── static/               # Frontend assets
├── templates/            # HTML visualizer
├── lib/
│   └── jbpt/             # JBPT submodule
└── README.md
```

# 🔧 TJN Creation Description

## 1. Leaf Nodes → Single Activity Nets
If a node in the process tree has **no operator** (`tree.operator is None`):

- It is a single activity.  
- The code creates:  
  - A **pre-place**  
  - A **post-place**  
  - A **transition** with the activity name  
- The result is a small fragment:  

```
Activity_pre --Activity--> Activity_post
```

---

## 2. Sequence Operator (SEQUENCE)
If the node has operator **SEQUENCE**:

- Recursively build nets for each child.  
- Append them in order using `append_sequence`.  
- Behavior:  
  - Merges the last place of one child with the first place of the next child.  
  - Handles variables/messages between them (emit/collect annotations).  
- The first place = first place of the first child.  
- The last place = last place of the last child.  

---

## 3. Parallel Operator (PARALLEL)
If the node has operator **PARALLEL**:

- Recursively build child nets.  
- Wrap them with `append_parallel`.  
- Behavior:  
  - Creates τ-start and τ-end transitions (invisible control-flow connectors).  
  - Connects τ-start to all children’s first places.  
  - Connects all children’s last places to τ-end.  
- Effect: Children execute in parallel, then join.  

```
        ┌─ Child1 ─┐
Start τ─┤          ├─ End τ
        └─ Child2 ─┘
```

---

## 4. Exclusive Choice Operator (XOR)
If the node has operator **XOR**:

- Recursively build child nets.  
- Wrap them with `append_xor`.  
- Behavior:  
  - Creates a shared XOR start place and XOR end place.  
  - Connects the shared start to the first transitions of each branch.  
  - Connects the last transitions of each branch to the shared end.  
- Effect: Exactly one branch is taken.  

---

## 5. Loop Operator (LOOP)
If the node has operator **LOOP**:

- Recursively build nets for children.  
- Wrap them with `append_loop`.  
- Behavior:  
  - Connects the loop body and “redo” structure.  
  - Ensures the last transitions of one iteration connect back to the first place of the body.  
  - Removes redundant start/end places of child nets to close the cycle.  

```
Body → Redo → back to Body → Exit
```

---

## 7. Finalization (build_tjn)
After recursion:

- If no `first_place` is explicitly set → pick a place without incoming arcs.  
- If no `last_place` is explicitly set → pick a place without outgoing arcs.  

This guarantees the net has a **clear entry and exit point**.

---

## 🔹 Summary
The TypedJacksonNet is built by:

1. **Recursively traversing** the process tree.  
2. **Leaf = activity net** (`Place → Transition → Place`).  
3. **Operators**:  
   - SEQUENCE → connect children in order.  
   - PARALLEL → add τ-split/τ-join.  
   - XOR → add shared XOR start/end places.  
   - LOOP → connect last transitions back to first places.  
4. **Typing and variables** are propagated via places, arcs, and emit/collect annotations.  
5. The result is a **Petri net-like structure** that is both *typed* and *Jackson structured*.  
