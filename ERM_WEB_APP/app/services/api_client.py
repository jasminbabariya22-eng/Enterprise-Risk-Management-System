import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import base64
from flask import current_app, session

# High-performance persistent connection session
_http_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=25, pool_maxsize=100, max_retries=1)
_http_session.mount("http://", _adapter)
_http_session.mount("https://", _adapter)

class APIClient:

    @staticmethod
    def post(endpoint, data, headers=None ):
        try:
            base_url = current_app.config['BASE_API_URL'].rstrip('/')
            url = f"{base_url}/{endpoint.lstrip('/')}"
            response = _http_session.post(
                url,
                json=data,
                verify=False,
                timeout=5
            )
            return response
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API POST Error: {str(e)}")
            raise


    @staticmethod
    def postdata(endpoint, data, headers=None):
        try:
            token = session.get("token")
            default_headers = {
                "Content-Type": "application/json"
            }

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)

            base_url = current_app.config['BASE_API_URL'].rstrip('/')
            url = f"{base_url}/{endpoint.lstrip('/')}"
            response = _http_session.post(
                url,
                json=data,
                verify=False,
                headers=default_headers,
                timeout=5
            )
            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API POST Error: {str(e)}")
            raise


    @staticmethod
    def getbyid(endpoint, data, headers=None):
        try:
            token = session.get("token")
            current_app.logger.info(f"Token(getbyid): {token}")
            current_app.logger.info(f"{current_app.config['BASE_API_URL']}/{endpoint}/{data}")
            deptid=data
            current_app.logger.info(f"getbyid data Id {data}")
            default_headers = {
                "Content-Type": "application/json"
            }

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)
            response = requests.get(
                f"{current_app.config['BASE_API_URL']}/{endpoint}/{data}",
		verify=False,
                headers=default_headers,
                timeout=current_app.config["API_TIMEOUT"]
            )
            response.raise_for_status()
            current_app.logger.info(f"getbyid data responce {response}")
            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API GET Error: {str(e)}")
            raise

    @staticmethod
    def putdataold(endpoint, data, headers=None):
        try:
            token = session.get("token")
            current_app.logger.info(f"Token(putdataold): {token}")
            deptid=data
            current_app.logger.info(f"Put data by Id {data}")
            default_headers = {
                "Content-Type": "application/json"
            }

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)
            response = requests.put(
                f"{current_app.config['BASE_API_URL']}/{endpoint}/{data}",
                headers=default_headers,
		verify=False,
                timeout=current_app.config["API_TIMEOUT"]
            )
            response.raise_for_status()
            current_app.logger.info(f"Update Dept responce {response}")
            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API GET Error: {str(e)}")
            raise

    @staticmethod
    def putdata(endpoint, data, headers=None):
    
        try:
        
            token = session.get("token")
    
            default_headers = {
                "Content-Type": "application/json"
            }
    
            if token:
                default_headers["Authorization"] = f"Bearer {token}"
    
            if headers:
                default_headers.update(headers)
            current_app.logger.info(f" API URL For Get Call {current_app.config['BASE_API_URL']}/{endpoint}")
            response = requests.put(
                f"{current_app.config['BASE_API_URL']}/{endpoint}",
                json=data,
		verify=False,
                headers=default_headers,
                timeout=current_app.config["API_TIMEOUT"]
            )
    
            response.raise_for_status()
    
            return response
    
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API PUT Error: {str(e)}")
            raise

    @staticmethod
    def getdata(endpoint, headers=None):
        try:
            token = session.get("token")
            default_headers = {
                "Content-Type": "application/json"
            }
            if token:
                default_headers["Authorization"] = f"Bearer {token}"
            if headers:
                default_headers.update(headers)
            base_url = current_app.config['BASE_API_URL'].rstrip('/')
            url = f"{base_url}/{endpoint.lstrip('/')}"
            response = _http_session.get(
                url,
                headers=default_headers,
                verify=False,
                timeout=5
            )
            return response
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API GET Error: {str(e)}")
            raise

    @staticmethod
    def get(endpoint, headers=None):
        try:
            base_url = current_app.config['BASE_API_URL'].rstrip('/')
            url = f"{base_url}/{endpoint.lstrip('/')}"
            response = _http_session.get(
                url,
                headers=headers,
                verify=False,
                timeout=5
            )
            return response
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API GET Error: {str(e)}")
            raise

    @staticmethod
    def postdatafileold(endpoint, data, headers=None, files=None):
        try:
            token = session.get("token")
    
            default_headers = {}
    
            if token:
                default_headers["Authorization"] = f"Bearer {token}"
    
            if headers:
                default_headers.update(headers)
    
            url = f"{current_app.config['BASE_API_URL']}/{endpoint}"
    
            current_app.logger.info(f"URL: {url}")
            current_app.logger.info(f"Data: {data}")
            current_app.logger.info(f"Files: {files}")
            if files:
                response = requests.post(
                    url,
                    data=data,   
		    verify=False,  
                    files=files,   
                    headers=default_headers,
                    timeout=current_app.config["API_TIMEOUT"]
                )
            else:
                default_headers["Content-Type"] = "application/json"
                response = requests.post(
                    url,
                    json=data,
                    headers=default_headers,
                    timeout=current_app.config["API_TIMEOUT"]
                )
            return response
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API POST Error: {str(e)}")
            raise
    
    @staticmethod
    def postdatafile(endpoint, data, headers=None, files=None):
        try:
            token = session.get("token")

            default_headers = {}

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)

            url = f"{current_app.config['BASE_API_URL']}/{endpoint}"

            current_app.logger.info(f"URL: {url}")
            current_app.logger.info(f"Data: {data}")
            current_app.logger.info(f"Files: {files}")

            response = requests.post(
                url,
                data=data,   
	        verify=False,   
                files=files or {},  
                headers=default_headers,
                timeout=current_app.config["API_TIMEOUT"]
            )

            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API POST Error: {str(e)}")
            raise

    @staticmethod
    def deletebyid(endpoint, headers=None):
        try:
            token = session.get("token")
            current_app.logger.info(f"Token(deletebyid): {token}")
            default_headers = {
                "Content-Type": "application/json"
            }

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)
            response = requests.delete(
                f"{current_app.config['BASE_API_URL']}/{endpoint}",
                headers=default_headers,
		verify=False,
                timeout=current_app.config["API_TIMEOUT"]
            )
            response.raise_for_status()
            current_app.logger.info(f"deletebyid data responce {response}")
            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API GET Error: {str(e)}")
            raise

    @staticmethod
    def post_onelogin(endpoint, data, headers=None ):
        try:
            current_app.logger.info(f"onelogin post endpoint: {endpoint}")
            current_app.logger.info(f"Json data: {data}")
            client_id = "a09801d0-50fb-013f-19e4-736a9f4edb74220581"
            client_secret = "82bae605dfc9eb5f626d0f933cc7b243e9bd0ed66e8e2c79d4a2128d4ff879cd"
            credentials = f"{client_id}:{client_secret}"
            encoded = base64.b64encode(credentials.encode()).decode()

            default_headers = {"Authorization": f"Basic {encoded}","Content-Type": "application/x-www-form-urlencoded"}
            
            #current_app.logger.info(f"Json URL: {current_app.config['BASE_API_URL']}/{endpoint}")
            response = requests.post(
                f"{endpoint}",
                #auth=("a09801d0-50fb-013f-19e4-736a9f4edb74220581", "82bae605dfc9eb5f626d0f933cc7b243e9bd0ed66e8e2c79d4a2128d4ff879cd"),
                data=data,
                verify=False,
                headers=default_headers,
               # timeout=current_app.config["API_TIMEOUT"]
            )
            current_app.logger.info(f"Api Response(onelogin post) : {response.text}")
            current_app.logger.info(f"Api Response(onelogin post) : {response.status_code}")
            #response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API Onelogin POST Error: {str(e)}")
            raise  

    @staticmethod
    def postdatafile_excel(endpoint, headers=None, files=None):
        try:
            token = session.get("token")

            default_headers = {}

            if token:
                default_headers["Authorization"] = f"Bearer {token}"

            if headers:
                default_headers.update(headers)

            url = f"{current_app.config['BASE_API_URL']}/{endpoint}"

            current_app.logger.info(f"URL: {url}")
            #current_app.logger.info(f"Data: {data}")
            current_app.logger.info(f"Files: {files}")

            response = requests.post(
                url,
                #data=data,   
	        verify=False,   
                files=files or {},  
                headers=default_headers,
                timeout=current_app.config["API_TIMEOUT"]
            )

            return response

        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"API POST Error: {str(e)}")
            raise            
