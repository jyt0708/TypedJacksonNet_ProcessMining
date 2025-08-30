from flask import Flask, render_template, request, jsonify
import os
from t_JN import *
from visualizer import tjn_to_json  
from pm4py.objects.log.importer.xes import importer as xes_importer
from flask import send_from_directory

app = Flask(__name__)

# folder with your xes logs
LOG_DIR = "."
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route("/")
def index():
    # list all xes files
    logs = [f for f in os.listdir(LOG_DIR) if f.endswith(".xes")]
    return render_template("index.html", logs=logs)


@app.route("/download_pnml/<resource>/<log_name>")
def download_pnml(resource, log_name):
    # Construct the filename
    log_name = log_name.removesuffix(".xes")
    filename = f"{resource}_{log_name}.pnml"
    pnml_dir = os.path.join(PROJECT_DIR, "logs", "pnmls")
    pnml_path = os.path.join(pnml_dir, filename)
    print(f"PNML file path: {pnml_path}")  # Print out the PNML file path

    
    # Serve the file
    return send_from_directory(pnml_dir, filename, as_attachment=True)


@app.route("/get_resources", methods=["POST"])
def get_resources():
    data = request.json
    filename = data.get("filename")
    log = xes_importer.apply(os.path.join(PROJECT_DIR, "logs", filename))
    # Extract resources for the log (adjust to your backend logic)
    resources = get_all_resources(log)
    print(f"Extracted resources: {resources}")
    

    return jsonify({"resources": sorted(list(resources))})


@app.route("/load_log", methods=["POST"])
def load_log():
    filename = request.json.get("filename")
    log_name = filename.removesuffix(".xes")
    resource = request.json.get("resource") 
    result = None

    print(f"Loading log: {filename} for resource: {resource}")

    # convert to TypedJacksonNet
    tjn, pn, resources, logs_by_resource, tjns, pns = convert_to_tjn_by_resource(filename)

    path_pnml = os.path.join(PROJECT_DIR, "logs", "pnmls", f"{resource}_{log_name}.pnml")

    if resource == None or resource == "All":
        result = tjn_to_json(tjn)
        # save pnml
        if not os.path.exists(path_pnml):
            pnml_exporter.apply(pn["pn"], pn["initial_marking"], path_pnml, final_marking=pn["final_marking"])
    else:
        if resource not in tjns:
            return jsonify({"error": f"Resource {resource} not found"}), 400
        result = tjn_to_json(tjns[resource])
        # save pnml
        if not os.path.exists(path_pnml):
            pn, initial_marking, final_marking = pns[resource]
            pnml_exporter.apply(pn, initial_marking, path_pnml, final_marking=final_marking)


    resource_list = list(resources)
    # pprint.pprint(result)

    # return JSON graph
    return jsonify({
        "nodes": result["nodes"],
        "edges": result["edges"],
        "metadata": result["metadata"],
        "resources": resource_list
    })


@app.route("/calculate_metrics", methods=["POST"])
def calculate_metrics():
    filename = request.json.get("filename")
    resource = request.json.get("resource") 

    # convert to TypedJacksonNet
    tjn, pn, resources, logs_by_resource, tjns, pns = convert_to_tjn_by_resource(filename)

    if resource == None or resource == "All":
        metrics = precision_and_fitness("No resource", pn, logs_by_resource, filename)
        for res, mets in metrics.items():
            print(f"Metrics for resource {res}:")
            for key, value in mets.items():
                print(f"  {key}: {value}")
        return jsonify(metrics["No resource"])
    else:
        if resource not in tjns:
            return jsonify({"error": f"Resource {resource} not found"}), 400
        metrics = precision_and_fitness(resource, pns, logs_by_resource, filename)
        for res, mets in metrics.items():
            print(f"Metrics for resource {res}:")
            for key, value in mets.items():
                print(f"  {key}: {value}")
        return jsonify(metrics[resource])

if __name__ == "__main__":
    app.run(debug=True)
