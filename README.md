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

