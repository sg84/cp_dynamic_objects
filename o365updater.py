# Import HTTP handling module 'requests'
import requests
# Import JSON module
import json
# Import UUID module for generating random strings
import uuid
# This is only used to suppress warnings about us not checking for certs
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
#Used for the time delay in publish function
import time

# Store all API related info in a Class
class CPAPI:
    def __init__(self, api_params):
        # Convert the MGMT parameters into a full URL to use elsewhere
        self.url = api_params['scheme'] + '://' + api_params['ip'] + ':' + api_params['port'] + \
          '/' + api_params['api_path'] + '/v' + api_params['api_ver'] + '/'
        # Create login headers to specify that the content type will be JSON
        login_headers = {
            'Content-Type': 'application/json'
            }

        #Create the payload for the HTTP POST request
        req_data = {}
        req_data['user'] = api_params['username']
        req_data['password'] = api_params['password']

        #format data as JSON for the HTTP POST body
        req_data = json.dumps(req_data)
        # Prepare an HTTP request and add the command 'login' to the command section of the URL
        response = requests.request("POST", self.url + 'login', data=req_data, headers=login_headers, verify=False)

        #Check that the API replied with an HTTP 200 status code. If it did, we're good. Otherwise, we're not...
        if response.status_code == 200:
            sid = json.loads(response.text)['sid']
            self.auth_headers = {
                'Content-Type': 'application/json',
                'x-chkp-sid': sid
            }
        else:
            print("Error - could not connect to API. Non HTTP 200 status code received")
            exit()

    def send_command(self, command, data): # Generic wrapper for sending commands to the API
        response = requests.request("POST", self.url + command, data=json.dumps(data), headers=self.auth_headers,
                                    verify=False)
        return response.text

    def publish(self): # Publish action
        data = {}
        cmd = 'publish'
        response = requests.request("POST", self.url + cmd, data=json.dumps(data), headers=self.auth_headers,
                                    verify=False)
        task_id = json.loads(response.text)['task-id']
        while True:
            task_details = json.loads(self.send_command('show-task', data={'task-id': task_id}))
            if task_details['tasks'][0]['progress-percentage'] < 100:
                print("[INFO] Waiting for publish to complete (" + str(task_details['tasks'][0]['progress-percentage']) + "%) complete")
                time.sleep(3)
            else:
                print("[INFO] Publish completed")
                break
        return response.text

    def logout(self): # Logout action
        cmd = 'logout'
        data = {}
        response = requests.request("POST", self.url + cmd, data=json.dumps(data), headers=self.auth_headers,
                                    verify=False)
        return response.text

# Function to retrieve IP addresses from Microsoft API and strip out IPv6 addresses we don't need here
def get_ms_ips():
    # MS API requires a Client Identifier to be sent in the form of a GUID
    import uuid
    # Define where the Microsoft API lives
    ms_url = 'https://endpoints.office.com/endpoints/worldwide'

    params = {'ClientRequestId': uuid.uuid4()}
    response = requests.request('GET', ms_url, params=params)
    # Return the results from the API call in JSON format
    #return json.loads(response.text)

    # Run our function to get the IPs from Microsoft
    all_ms_ips = json.loads(response.text)

    # For this demo, we're only going to take one section - IPs for office.outlook.com
    # Loop over every item in the list returned
    for x in all_ms_ips:
        # x refers to each item in the list of IPs returned
        # Check if the item 'URLs' exists in the list and it contains the string 'outlook.office.com'
        if x['urls'] and 'outlook.office.com' in x['urls']:
            # If found, create a new list of just these IPs - we'll ignore the rest for now.
            office_outlook_dotcom_ips = x['ips']
            # Break stops us from searching through the rest of the list when we already have what we need
            break

        # Next, we're going to remove the IPv6 addresses
        # Create an empty list to hold
    outlook_office_dotcom_ipv4 = []

    # Loop over every IP address in the list we created earlier
    for ip in office_outlook_dotcom_ips:
        # If there's a colon in the address string - it's an IPv6 address
        # If not - it's IPv4 and we add it to our new list
        if ':' not in ip:
            outlook_office_dotcom_ipv4.append(ip)

    # Finally, construct a list of dictionaries with the IP and masklength stored separately
    ip_cidr_list = []
    for x in outlook_office_dotcom_ipv4:
        ip, mask = x.split('/')
        ip_cidr_list.append({'ip': ip, 'mask': mask})

    return ip_cidr_list

# Create dictionary to hold management parameters
mgmt_params = {}
mgmt_params['ip'] = '192.168.241.10'
mgmt_params['port'] = '443'
mgmt_params['scheme'] = 'https'
mgmt_params['api_ver'] = '1.3'
mgmt_params['api_path'] = 'web_api'
mgmt_params['username'] = 'admin'
mgmt_params['password'] = 'password'
o365_obj_group = 'demo_o365_ips'
o365_obj_prefix = 'o365_'
o365_obj_suffix = str(uuid.uuid4())[0:4]

# Setup new API object with session ID
print("[INFO] Setting up new CP API Session")
apiCall = CPAPI(mgmt_params)

# Get latest Microsoft IPs
print("[INFO] Getting IPs from Microsoft API")
microsoft_ips = get_ms_ips()
data = {'name': o365_obj_group}
print("[INFO] Checking existing CP group")
group_contents = json.loads(apiCall.send_command('show-group', data=data))

# We need to check if the group exists
try:
    if group_contents['code'] == 'generic_err_object_not_found':
        # Create the networks and specify the group inline
        print("[INFO] Group not found, creating and adding networks...")
        r = apiCall.send_command('add-group', data={'name': o365_obj_group})
        for item in microsoft_ips:
            print("[INFO] Adding network obj " + item['ip'] + "/" + item['mask'])
            r = apiCall.send_command('add-network', data={
             'name': o365_obj_prefix + item['ip'] + '_' + item['mask'] + '_' + o365_obj_suffix,
             'subnet4': item['ip'],
             'mask-length4': item['mask'],
             'groups' : [o365_obj_group]
             })




except:
    print("[INFO] Group already exists - removing members")
    # We're here because the group exists - so lets get the UIDs for the members of the group
    objs = json.loads(apiCall.send_command('show-group', data= {'name': o365_obj_group}))['members']
    # Check the group to see if it has any members
    if len(group_contents) > 0:
        # One-liner in place of for loop
        group_members_uids = list(map(lambda x: x['uid'], objs))
        # Delete each item by its UID
        for item in group_members_uids:
            print("[INFO] Deleting object " + item)
            r = apiCall.send_command('delete-network', data={'uid': item, 'ignore-warnings': True})
            # print(r)
    # now we can add the new network objects in
    for item in microsoft_ips:
        print("[INFO] Adding network obj " + item['ip'] + "/" + item['mask'] + " to group")
        r = apiCall.send_command('add-network', data={
         'name': o365_obj_prefix + item['ip'] + '_' + item['mask'] + '_' + o365_obj_suffix,
         'subnet4': item['ip'],
         'mask-length4': item['mask'],
         'groups' : [o365_obj_group]
         }
        )
        #print(r)
print("[INFO] Finished!")

apiCall.publish()
apiCall.logout()
