from flask import Flask, render_template, request, jsonify
import os
import pprint
from t_JN import *
from visualizer import tjn_to_json  # reuse serializer from canvas code

app = Flask(__name__)

# folder with your xes logs
LOG_DIR = "."

@app.route("/")
def index():
    # list all xes files
    logs = [f for f in os.listdir(LOG_DIR) if f.endswith(".xes")]
    return render_template("index.html", logs=logs)

@app.route("/load_log", methods=["POST"])
def load_log():
    filename = request.json.get("filename")
    resource = request.json.get("resource") 
    print(f"Selected resource: {resource}")
    filepath = os.path.join(LOG_DIR, filename)
    result = None

    # convert to TypedJacksonNet
    tjn, resources, logs_by_resource, tjns, pns = convert_to_tjn_by_resource(filename)
 
    if resource == None or resource == "All":
        print("Loading all resources")
        result = tjn_to_json(tjn)
    else:
        print(f"Loading resource: {resource}")
        if resource not in tjns:
            return jsonify({"error": f"Resource {resource} not found"}), 400
        result = tjn_to_json(tjns[resource])
        
    resource_list = list(resources)
    # pprint.pprint(result)

    # return JSON graph
    return jsonify({
        "nodes": result["nodes"],
        "edges": result["edges"],
        "metadata": result["metadata"],
        "resources": resource_list
    })

if __name__ == "__main__":
    app.run(debug=True)
