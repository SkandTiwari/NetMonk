import requests
from requests.auth import HTTPBasicAuth
import env_lab
from flask import Flask, redirect, url_for, request, render_template
import datetime
import json
import logging

requests.packages.urllib3.disable_warnings()

app = Flask(__name__)

@app.route("/")
def login_initiator():
    return render_template("login.html")

@app.route('/login',methods = ['POST', 'GET'])
def get_auth_token():
    endpoint = '/dna/system/api/v1/auth/token'
    global username
    global token
    username = request.form.get("username")
    password = request.form.get("password")
    url = 'https://' + env_lab.DNA_CENTER['host'] + endpoint
    try:
        resp = requests.post(url, auth=HTTPBasicAuth(username, password), verify=False)
        token = resp.json()['Token']
        [devicecount, avguptime, totalos, timefromupdt]= get_network_overview()
        return render_template("dashboard.html", uname = username, dcount = devicecount, avgup = avguptime//3600,
        tos = totalos, tupdt = timefromupdt)
    except Exception as e:

        return render_template("login_invalid.html", error = e)
 

def get_network_overview():
    url = "https://sandboxdnac.cisco.com/api/v1/network-device"
    hdr = {'x-auth-token': token, 'content-type' : 'application/json'}
    resp = requests.get(url, headers=hdr, verify=False)  # Make the Get Request
    device_json = resp.json()
    print(device_json)
    device_count = len(device_json['response'])
    sum = 0
    os_set = set()
    max = 0
    for item in device_json['response']:

        os_set.add(item['softwareType'])
        sum = item['uptimeSeconds'] + sum
        if max < item['lastUpdateTime']:
            max = item['lastUpdateTime']
    timestamp = max / 1000 
    datetime_object = datetime.datetime.fromtimestamp(timestamp)
    formatted_datetime = datetime_object.strftime("%Y-%m-%d %H:%M:%S")
    avg_uptime = sum/device_count
    total_os = len(os_set)
    return [device_count, avg_uptime, total_os, formatted_datetime]



@app.route("/devices")
def get_device_list():
    url = "https://sandboxdnac.cisco.com/api/v1/network-device"
    hdr = {'x-auth-token': token, 'content-type' : 'application/json'}
    try:
        response = requests.get(url, headers=hdr, verify=False)
        response.raise_for_status() 
        device_json = response.json()

        devices = []

        for item in device_json['response']:
            device = {
                'hostname': item['hostname'],
                'mgmt_ip': item['managementIpAddress'],
                'serial': item['serialNumber'],
                'platform_id': item['platformId'],
                'sw_version': item['softwareVersion'],
                'role': item['role'],
                'uptime': item['upTime']
            }
            devices.append(device)


    except requests.exceptions.RequestException as e:
        print(f"Error occurred during API request: {e}")
    return render_template("devices.html", name = username, dvs = devices)


@app.route('/interface_data', methods = ['POST'])
def interface_data():
    url = "https://sandboxdnac.cisco.com/api/v1/interface"
    hdr = {'x-auth-token': token, 'content-type' : 'application/json'}
    device_id = request.form.get("deviceId")
    print(device_id)
    try:
        querystring = {"macAddress": device_id} 
        resp = requests.get(url, headers=hdr, params=querystring, verify=False) 
        interface_info = resp.json()
    #print("------------------------------", interface_info['response'])
        interface_json = []
        for int in interface_info['response']:
            int_json = {
                'portName': int['portName'],
                'vlanId': int['portMode'],
                'portMode': int['portMode'],
                'portType': int['portType'],
                'duplex': int['duplex'],
                'status': int['status'],
                'lastUpdated': int['lastUpdated']
            }
            interface_json.append(int_json)
        return render_template('interface_data.html', name = username, interfaces = interface_json)

    except Exception as e:
        return render_template("interface_invalid.html", name = username)
    #print(interface_json)

@app.route("/interfaces")
def get_device_int():
    return render_template('interface.html', name = username)


@app.route("/command_runner")
def get_cmd_runner():
    return render_template('cmd_runner.html', name = username)


@app.route("/cmd_console", methods=['POST', 'GET'])
def get_output_console():
    name = request.form.get("name")
    global ios_cmd
    ios_cmd = request.form.get("command")
    device_id = request.form.get("uuid")

    if not name or not ios_cmd or not device_id:
        return "Missing parameters. Please provide 'name', 'command', and 'uuid' in the request form.", 400

    print("executing ios command -->", ios_cmd)
    param = {
        "name": name,
        "commands": [ios_cmd],
        "deviceUuids": [device_id]
    }

    url = "https://sandboxdnac.cisco.com/api/v1/network-device-poller/cli/read-request"
    header = {'content-type': 'application/json', 'x-auth-token': token}
    logging.captureWarnings(True)

    try:
        response = requests.post(url, data=json.dumps(param), headers=header, verify=False)
        response.raise_for_status()  # Check if the API call was successful
        task_id = response.json()['response']['taskId']
        print("Command runner Initiated! Task ID --> ", task_id)
        print("Retrieving Path Trace Results.... ")
        return get_task_info(task_id)
    except requests.exceptions.RequestException as e:
        return f"Error making API call: {e}", 500

def get_task_info(task_id):
    url = "https://sandboxdnac.cisco.com/api/v1/task/{}".format(task_id)
    hdr = {'x-auth-token': token, 'content-type': 'application/json'}
    logging.captureWarnings(True)

    try:
        task_result = requests.get(url, headers=hdr, verify=False)
        task_result.raise_for_status()  # Check if the API call was successful
        file_id = task_result.json()['response']['progress']

        if "fileId" in file_id:
            unwanted_chars = '{"}'
            for char in unwanted_chars:
                file_id = file_id.replace(char, '')
            file_id = file_id.split(':')[1]
            print("File ID --> ", file_id)
            return get_cmd_output(file_id)
        else:  # keep checking for task completion
            return get_task_info(task_id)
    except requests.exceptions.RequestException as e:
        return f"Error making API call: {e}", 500

def get_cmd_output(file_id):
    url = "https://sandboxdnac.cisco.com/api/v1/file/{}".format(file_id)
    hdr = {'x-auth-token': token, 'content-type': 'application/json'}
    logging.captureWarnings(True)

    try:
        cmd_result = requests.get(url, headers=hdr, verify=False)
        cmd_result.raise_for_status()  # Check if the API call was successful
        result = cmd_result.json()#json.dumps(cmd_result.json(), indent=4, sort_keys=True)
        return render_template("cmd_console.html", res_json = result, ios_cmd = ios_cmd)
    except requests.exceptions.RequestException as e:
        return f"Error making API call: {e}", 500

if __name__ == "__main__":
    app.run(debug=True)

if __name__ == '__main__':
   app.run(debug = True)





