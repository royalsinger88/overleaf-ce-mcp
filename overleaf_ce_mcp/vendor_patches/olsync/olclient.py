"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
##################################################

import requests as reqs
from bs4 import BeautifulSoup
import json
import uuid
from socketIO_client import SocketIO
import time
import re

PATH_SEP = "/"  # Use hardcoded path separator for both windows and posix system


class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """

    @staticmethod
    def filter_projects(json_content, more_attrs=None):
        more_attrs = more_attrs or {}
        for p in json_content:
            if not p.get("archived") and not p.get("trashed"):
                if all(p.get(k) == v for k, v in more_attrs.items()):
                    yield p

    def __init__(self, cookie=None, csrf=None, ce_url=None):
        self._cookie = cookie  # Store the cookie for authenticated requests
        self._csrf = csrf  # Store the CSRF token since it is needed for some requests
        # Where to get the CSRF Token and where to send the login request to
        if ce_url is not None:
            self._ce = True
            self._BASE_URL = ce_url
        else:
            self._BASE_URL = "https://www.overleaf.com"  # The Overleaf Base URL
            self._ce = True

        self._LOGIN_URL = self._BASE_URL + "/login"
        self._PROJECT_URL = self._BASE_URL + "/project"  # The dashboard URL
        # The URL to download all the files in zip format
        self._DOWNLOAD_URL = self._BASE_URL + "/project/{}/download/zip"
        self._UPLOAD_URL = self._BASE_URL + "/project/{}/upload"  # The URL to upload files
        self._FOLDER_URL = self._BASE_URL + "/project/{}/folder"  # The URL to create folders
        self._COMPILE_URL = self._BASE_URL + "/project/{}/compile?enable_pdf_caching=true"  # The URL to compile the project
        self._DELETE_URL = self._BASE_URL + "/project/{}/{}/{}"  # The URL to delete files

    def login(self, username, password):
        """
        WARNING - DEPRECATED - Not working as Overleaf introduced captchas
        Login to the Overleaf Service with a username and a password
        Params: username, password
        Returns: Dict of cookie and CSRF
        """

        get_login = reqs.get(self._LOGIN_URL)
        self._csrf = BeautifulSoup(get_login.content, 'html.parser').find(
            'input', {'name': '_csrf'}).get('value')
        login_json = {
            "_csrf": self._csrf,
            "email": username,
            "password": password
        }
        post_login = reqs.post(self._LOGIN_URL, json=login_json,
                               cookies=get_login.cookies)

        # On a successful authentication the Overleaf API returns a new authenticated cookie.
        # If the cookie is different than the cookie of the GET request the authentication was successful
        if post_login.status_code == 200 and ((self._ce and get_login.cookies["sharelatex.sid"] != post_login.cookies[
            "sharelatex.sid"]) or get_login.cookies["overleaf_session2"] != post_login.cookies[
                                                  "overleaf_session2"]):
            self._cookie = post_login.cookies

            # Enrich cookie with GCLB cookie from GET request above
            if not self._ce:
                self._cookie['GCLB'] = get_login.cookies['GCLB']

            # CSRF changes after making the login request, new CSRF token will be on the projects page
            projects_page = reqs.get(self._PROJECT_URL, cookies=self._cookie)
            self._csrf = BeautifulSoup(projects_page.content, 'html.parser').find('meta', {'name': 'ol-csrfToken'}) \
                .get('content')

            return {"cookie": self._cookie, "csrf": self._csrf}

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived and not trashed)
        Returns: List of project objects
        """
        projects_page = reqs.get(self._PROJECT_URL, cookies=self._cookie)
        bsoup = BeautifulSoup(projects_page.content, 'html.parser')
        projects_txt = bsoup.find('meta', {'name': 'ol-projects'})
        if projects_txt is None:
            projects_txt = bsoup.find('meta', {'name': 'ol-prefetchedProjectsBlob'}) 
            #{"content": re.compile('\{.*"projects".*\}')}
        
        if projects_txt is None:
            if "Log in to Overleaf" in bsoup.text:
                raise ValueError("Not logged in")
            raise ValueError("Projects not found")
        
        json_content = json.loads(projects_txt.get('content'))
            
        projects = list(OverleafClient.filter_projects(json_content["projects"]))
        return list(OverleafClient.filter_projects(json_content["projects"]))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """

        projects_page = reqs.get(self._PROJECT_URL, cookies=self._cookie)

        json_content = json.loads(
             BeautifulSoup(projects_page.content, 'html.parser').find("meta", {"content": re.compile('\{.*"projects".*\}')}).get('content'))
        return next(OverleafClient.filter_projects(json_content['projects'], {"name": project_name}), None)

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = reqs.get(self._DOWNLOAD_URL.format(project_id),
                     stream=True, cookies=self._cookie)
        return r.content

    def create_folder(self, project_id, parent_folder_id, folder_name):
        """
        Create a new folder in a project

        Params:
        project_id: the id of the project
        parent_folder_id: the id of the parent folder, root is the project_id
        folder_name: how the folder will be named

        Returns: folder id or None
        """

        params = {
            "parent_folder_id": parent_folder_id,
            "name": folder_name
        }
        headers = {
            "X-Csrf-Token": self._csrf
        }
        r = reqs.post(self._FOLDER_URL.format(project_id),
                      cookies=self._cookie, headers=headers, json=params)

        if r.ok:
            return json.loads(r.content)
        elif r.status_code == str(400):
            # Folder already exists
            return
        else:
            raise reqs.HTTPError()

    def get_project_infos(self, project_id):
        """
        Get detailed project infos about the project

        Params:
        project_id: the id of the project

        Returns: project details
        """
        project_infos = None

        # 兼容 ack 与事件两种回包模式
        def set_project_infos(*args):
            nonlocal project_infos
            # 旧版本回调参数通常是 (a, project_infos_dict, c, d)
            if len(args) >= 2 and isinstance(args[1], dict):
                project_infos = args[1]
                return
            # 新版本可能只返回一个 dict
            if args and isinstance(args[0], dict):
                project_infos = args[0]

        # Convert cookie dict to header
        if not self._ce:
            cookie = f"GCLB={self._cookie['GCLB']}; overleaf_session2={self._cookie['overleaf_session2']}"
        else:
            pairs = dict(self._cookie)
            sid_value = pairs.get("overleaf.sid") or pairs.get("sharelatex.sid")
            if sid_value:
                pairs.setdefault("overleaf.sid", sid_value)
                pairs.setdefault("sharelatex.sid", sid_value)
            cookie = "; ".join([f"{k}={v}" for k, v in pairs.items()])

        socket_io = SocketIO(
            self._BASE_URL,
            # 新 CE 握手要求 projectId；旧 CE 会忽略该参数
            params={'t': int(time.time()), 'projectId': project_id},
            headers={'Cookie': cookie}
        )

        socket_io.on('connect', lambda: None)
        socket_io.on('joinProjectResponse', set_project_infos)
        socket_io.wait_for_callbacks(seconds=2)

        # 发起 joinProject，并同时兼容 ack 回调
        socket_io.emit('joinProject', {'project_id': project_id}, set_project_infos)

        # 等待回包，尽量提升新旧版本兼容性
        for _ in range(8):
            socket_io.wait_for_callbacks(seconds=1)
            if isinstance(project_infos, dict):
                break

        if socket_io.connected:
            socket_io.disconnect()

        return project_infos

    def upload_file(self, project_id, project_infos, file_name, file_size, file):
        """
        Upload a file to the project

        Params:
        project_id: the id of the project
        file_name: how the file will be named
        file_size: the size of the file in bytes
        file: the file itself

        Returns: True on success, False on fail
        """

        # 兼容 project_infos 结构差异：
        # - 旧版：{'rootFolder': [...]}
        # - 新版：{'project': {'rootFolder': [...]}, ...}
        project_tree = project_infos.get('project', project_infos)

        # Set the folder_id to the id of the root folder
        folder_id = project_tree['rootFolder'][0]['_id']

        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            local_folders = file_name.split(PATH_SEP)[:-1]  # Remove last item since this is the file name
            file_name = file_name.split(PATH_SEP)[-1]

            current_overleaf_folder = project_tree['rootFolder'][0]['folders']  # Set the current remote folder

            for local_folder in local_folders:
                exists_on_remote = False
                for remote_folder in current_overleaf_folder:
                    # Check if the folder exists on remote, continue with the new folder structure
                    if local_folder.lower() == remote_folder['name'].lower():
                        exists_on_remote = True
                        folder_id = remote_folder['_id']
                        current_overleaf_folder = remote_folder['folders']
                        break
                # Create the folder if it doesn't exist
                if not exists_on_remote:
                    new_folder = self.create_folder(project_id, folder_id, local_folder)
                    current_overleaf_folder.append(new_folder)
                    folder_id = new_folder['_id']
                    current_overleaf_folder = new_folder['folders']
        headers = {
            "X-Csrf-Token": self._csrf
        }
        params = {
            "folder_id": folder_id,
            # "_csrf": self._csrf,
            # "qquuid": str(uuid.uuid4()),
            # "qqfilename": file_name,
            # "qqtotalfilesize": file_size,
        }
        form_data = {
            # "relativePath" : "null",
            # "type": "application/octet-stream",
            "name": file_name,
        }
        files = {
            "qqfile": file
        }

        # Upload the file to the predefined folder
        r = reqs.post(self._UPLOAD_URL.format(project_id), cookies=self._cookie, 
            headers=headers, params=params, data=form_data, files=files)
        
        # return json.loads(r.content), r.status_code
        return r.status_code == 200 and json.loads(r.content)["success"]

    def delete_file(self, project_id, project_infos, file_name):
        """
        Deletes a project's file

        Params:
        project_id: the id of the project
        file_name: how the file will be named

        Returns: True on success, False on fail
        """

        file = None
        type_ = "doc"

        # 兼容 project_infos 结构差异（同 upload_file）
        project_tree = project_infos.get('project', project_infos)
        root_folder = project_tree['rootFolder'][0]

        parts = [p for p in file_name.split(PATH_SEP) if p]
        if not parts:
            return False

        target_name = parts[-1]
        folder = root_folder
        for part in parts[:-1]:
            next_folder = next(
                (f for f in folder.get('folders', []) if f.get('name', '').lower() == part.lower()),
                None
            )
            if next_folder is None:
                return False
            folder = next_folder

        file = next((v for v in folder.get('docs', []) if v.get('name') == target_name), None)
        if file is None:
            file = next((v for v in folder.get('fileRefs', []) if v.get('name') == target_name), None)
            type_ = "file"

        # File not found!
        if file is None:
            return False

        headers = {
            "X-Csrf-Token": self._csrf
        }

        r = reqs.delete(self._DELETE_URL.format(project_id, type_, file['_id']), 
            cookies=self._cookie, headers=headers, json={})

        # return r.content, r.status_code 
        return r.status_code == (204)

    def download_pdf(self, project_id):
        """
        Compiles and returns a project's PDF

        Params:
        project_id: the id of the project

        Returns: PDF file name and content on success
        """
        headers = {
            "X-Csrf-Token": self._csrf
        }

        body = {
            "check": "silent",
            "draft": False,
            "incrementalCompilesEnabled": True,
            "rootDoc_id": "",
            "stopOnFirstError": False
        }

        r = reqs.post(self._COMPILE_URL.format(project_id), cookies=self._cookie, headers=headers, json=body)

        if not r.ok:
            raise reqs.HTTPError()

        compile_result = json.loads(r.content)

        if compile_result["status"] != "success":
            raise reqs.HTTPError()

        pdf_file = next(v for v in compile_result['outputFiles'] if v['type'] == 'pdf')

        download_req = reqs.get(self._BASE_URL + pdf_file['url'], cookies=self._cookie, headers=headers)

        if download_req.ok:
            return pdf_file['path'], download_req.content

        return None
