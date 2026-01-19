import requests
import yaml
from concurrent.futures import ThreadPoolExecutor

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def mock_ssh(host):
    print(f"MOCK_SSH: Connecting to host {host}...")

def mock_rdp(host):
    print(f"MOCK_RDP: Validating remote connection to {host}...")

class APIClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get(self, endpoint):
        return requests.get(self.base_url + endpoint, headers=self.headers).json()

    def put(self, endpoint, payload):
        return requests.put(self.base_url + endpoint, json=payload, headers=self.headers).json()

def pre_fetch(api):
    tenants = api.get("/api/tenant")
    vs_list = api.get("/api/virtualservice")
    engines = api.get("/api/serviceengine")

    print(f"[Pre-Fetch] Tenants Count: {len(tenants)}")
    print(f"[Pre-Fetch] Virtual Services: {[vs['name'] for vs in vs_list]}")
    print(f"[Pre-Fetch] Service Engines Count: {len(engines)}")

    return vs_list

def pre_validation(vs_list, target_name):
    for vs in vs_list:
        if vs["name"] == target_name:
            if vs["enabled"] is not True:
                raise Exception("Virtual Service is not enabled")
            print(f"[Pre-Validation] {target_name} is enabled")
            return vs["uuid"]
    raise Exception("Target Virtual Service not found")

def task_trigger(api, uuid, payload):
    response = api.put(f"/api/virtualservice/{uuid}", payload)
    print("[Task] Virtual Service disabled")
    return response

def post_validation(api, uuid):
    vs = api.get(f"/api/virtualservice/{uuid}")
    if vs["enabled"] is not False:
        raise Exception("Post-validation failed")
    print("[Post-Validation] Virtual Service is disabled")

def run_parallel(tasks, workers):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        executor.map(lambda fn: fn(), tasks)

def main():
    config = load_config()

    base_url = config["base_url"]
    username = config["auth"]["username"]
    password = config["auth"]["password"]
    target_vs = config["test_case"]["target_vs_name"]
    payload = config["test_case"]["disable_payload"]

    requests.post(
        base_url + "/register",
        json={"username": username, "password": password}
    )

    login_resp = requests.post(
        base_url + "/login1",
        auth=(username, password)
    ).json()

    token = login_resp["token"]
    api = APIClient(base_url, token)

    run_parallel(
        tasks=[
            lambda: mock_ssh("controller-node"),
            lambda: mock_rdp("controller-node")
        ],
        workers=config["execution"]["parallel_workers"]
    )

    vs_list = pre_fetch(api)
    uuid = pre_validation(vs_list, target_vs)
    task_trigger(api, uuid, payload)
    post_validation(api, uuid)

    print("\nTEST CASE EXECUTED SUCCESSFULLY")

if __name__ == "__main__":
    main()
