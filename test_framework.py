import requests
import yaml
import sys
from concurrent.futures import ThreadPoolExecutor
from requests.exceptions import HTTPError, JSONDecodeError

def load_config():
    try:
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print("Error: config.yaml not found.")
        sys.exit(1)

def mock_ssh(host):
    print(f"   [MOCK_SSH] Connecting to host {host}...")

def mock_rdp(host):
    print(f"   [MOCK_RDP] Validating remote connection to {host}...")

class APIClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def _handle_request(self, method, endpoint, payload=None):
        url = f"{self.base_url}{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "PUT":
                response = requests.put(url, json=payload, headers=self.headers)
            
            response.raise_for_status()
            return response.json()
        
        except HTTPError as e:
            print(f"API Error [{method} {endpoint}]: {e}")
            print(f"   Response Body: {response.text}")
            raise
        except JSONDecodeError:
            print(f"JSON Error: Response was not valid JSON. Content: {response.text}")
            raise

    def get(self, endpoint):
        return self._handle_request("GET", endpoint)

    def put(self, endpoint, payload):
        return self._handle_request("PUT", endpoint, payload)

def pre_fetch(api):
    print("\n--- PHASE 1: Pre-Fetch ---")
    tenants = api.get("/api/tenant")
    vs_list = api.get("/api/virtualservice")
    engines = api.get("/api/serviceengine")

    print(f"   Tenants Count: {len(tenants)}")
    vs_names = [vs.get('name', 'UNKNOWN') for vs in vs_list]
    print(f"   Virtual Services: {vs_names}")
    print(f"   Service Engines Count: {len(engines)}")

    return vs_list

def pre_validation(vs_list, target_name):
    print("\n--- PHASE 2: Pre-Validation ---")
    for vs in vs_list:
        if vs["name"] == target_name:
            if not vs.get("enabled", False):
                print(f"Target {target_name} is already disabled. Attempting to enable first...")
                
            print(f"   Target found: {target_name} (UUID: {vs['uuid']})")
            return vs 
    
    raise Exception(f"Target Virtual Service '{target_name}' not found in fetched list.")

def task_trigger(api, vs_object, modification_payload):
    print("\n--- PHASE 3: Task Trigger (Modify State) ---")
    uuid = vs_object['uuid']
    updated_payload = vs_object.copy()
    updated_payload.update(modification_payload)
    
    response = api.put(f"/api/virtualservice/{uuid}", updated_payload)
    print(f"   [Task] Payload sent to disable Virtual Service: {uuid}")
    return response

def post_validation(api, uuid):
    print("\n--- PHASE 4: Post-Validation ---")
    vs = api.get(f"/api/virtualservice/{uuid}")
    
    if vs["enabled"] is not False:
        raise Exception(f"Post-validation failed. VS status is: {vs['enabled']}")
    
    print("   [Success] Virtual Service is confirmed disabled.")

def run_parallel(tasks, workers):
    print(f"\n--- Running {len(tasks)} Background Tasks (Workers: {workers}) ---")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        executor.map(lambda fn: fn(), tasks)

def authenticate(base_url, username, password):
    reg_resp = requests.post(f"{base_url}/register", json={"username": username, "password": password})
    if reg_resp.status_code == 201:
        print("User registered successfully.")
    elif reg_resp.status_code == 400 or reg_resp.status_code == 409:
        print("ℹUser likely already exists, proceeding to login.")
    else:
        print(f"Registration warning: {reg_resp.status_code} - {reg_resp.text}")

    login_url = f"{base_url}/login"
    
    try:
        resp = requests.post(login_url, json={"username": username, "password": password})
        resp.raise_for_status()
        return resp.json()["token"]
    except Exception:
        print("Login via JSON body failed, trying Basic Auth...")
        resp = requests.post(login_url, auth=(username, password))
        resp.raise_for_status()
        return resp.json()["token"]

def main():
    config = load_config()

    base_url = config["base_url"]
    username = config["auth"]["username"]
    password = config["auth"]["password"]
    target_vs_name = config["test_case"]["target_vs_name"]
    payload = config["test_case"]["disable_payload"]

    try:
        token = authenticate(base_url, username, password)
        api = APIClient(base_url, token)

        run_parallel(
            tasks=[
                lambda: mock_ssh("controller-node-01"),
                lambda: mock_rdp("controller-node-02"),
                lambda: mock_ssh("worker-node-01"),
                lambda: mock_rdp("worker-node-02")
            ],
            workers=config["execution"]["parallel_workers"]
        )

        vs_list = pre_fetch(api)
        
        target_vs_object = pre_validation(vs_list, target_vs_name)
        
        task_trigger(api, target_vs_object, payload)
        
        post_validation(api, target_vs_object['uuid'])

        print("\nTEST CASE EXECUTED SUCCESSFULLY")

    except Exception as e:
        print(f"\nFATAL ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
