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

## 🔧 Installation

Clone the repository **with submodules** to include JBPT:

```bash
git clone --recurse-submodules https://github.com/jyt0708/TypedJacksonNet_ProcessMining.git 
cd <your-repo>

---

## ▶️ Usage
- Start the backend server:

```bash
python app.py


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

