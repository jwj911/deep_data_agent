import requests
import pandas as pd
import os
import json
import logging
from requests_toolbelt import MultipartEncoder
import numpy as np
from configobj import ConfigObj
from utils.tools import get_config, get_root_path

open_id_type = "union_id"  # 可以是open_id, union_id


class BaseRobot(object):
    def __init__(self, robot_name: str = None):
        self.root = get_root_path()
        self._get_main_robot(robot_name=robot_name)
        self._get_tenant_access_token()
        # 更新全部成员
        # self.update_all_members()
        # 更新全部群
        # self.update_all_groups()

    # 注意这是获取app的token，当lark接口需要的参数是用户token的时候不能用这里获得的token
    def _get_tenant_access_token(self):
        data = requests.post(
            url="https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/",
            data={
                "app_id": self.robot["app_id"],
                "app_secret": self.robot["app_secret"],
            },
        ).json()
        try:
            self.tenant_access_token = data["tenant_access_token"]
            logging.info("token" + self.tenant_access_token)
        except Exception as e:
            logging.error(data)

    # 名字起的不好，不要被误导，这一步是通过code换取refresh token
    def get_user_access_token(self, code: str = None, redirect_uri: str = None):
        if redirect_uri is None:
            robot_config = get_config().get("robot", {}).get(self.robot_name, {})
            redirect_uri = robot_config.get("redirect_uri") or os.environ.get("LARK_REDIRECT_URI", "")
            if not redirect_uri:
                raise ValueError("Lark redirect_uri is not configured. Please set it in application.cfg or LARK_REDIRECT_URI env var.")
        body = {
            "grant_type": "authorization_code",
            "client_id": self.robot["app_id"],
            "client_secret": self.robot["app_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "scopes": ["offline_access"],
        }
        data = requests.post(
            url="https://open.feishu.cn/open-apis/authen/v2/oauth/token",
            headers={"Content-Type": "application/json; charset=utf-8"},
            data=json.dumps(body),
        ).json()
        try:
            refresh_token = data["refresh_token"]
            config_path = os.path.join(get_root_path(), "application.cfg")
            config = ConfigObj(config_path, encoding="utf8")
            config["robot"][self.robot_name]["refresh_token"] = refresh_token
            config.write()
            return data["access_token"]
        except Exception as e:
            logging.error(data)
            return 'error'

    # 名字起的不好，不要被误导，这一步才是通过refresh token换取user_access_token
    def refresh_user_access_token(self):
        refresh_token = get_config()["robot"][self.robot_name]["refresh_token"]
        data = requests.post(
            url="https://open.feishu.cn/open-apis/authen/v2/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": self.robot["app_id"],
                "client_secret": self.robot["app_secret"],
                "refresh_token": refresh_token,
            },
        ).json()
        try:
            user_access_token = data["access_token"]
            refresh_token = data["refresh_token"]
            config_path = os.path.join(get_root_path(), "application.cfg")
            config = ConfigObj(config_path, encoding="utf8")
            config["robot"][self.robot_name]["refresh_token"] = refresh_token
            config.write()
            logging.info("token" + user_access_token)
            return user_access_token
        except Exception as e:
            # 给管理员发送消息（如果配置了 admin_open_id）
            robot_config = get_config().get("robot", {}).get(self.robot_name, {})
            admin_open_id = robot_config.get("admin_open_id") or os.environ.get("LARK_ADMIN_OPEN_ID")
            if admin_open_id:
                self.send_message(
                    receive_id=admin_open_id,
                    content="token刷新失败",
                    msg_type="text",
                )
            logging.error(data)
    
    def get_user_info_by_token(self, user_access_token: str=None):
        url = f"https://open.feishu.cn/open-apis/authen/v1/user_info"
        headers = {
            "Authorization": f"Bearer {user_access_token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        return requests.get(url, headers=headers).json()

    def _get_main_robot(self, robot_name: str = None):
        self.robot_name = robot_name or "default_robot"
        global_config = get_config()
        robot = global_config.get("robot").get(self.robot_name)
        self.robot = {"app_id": robot["app_id"], "app_secret": robot["app_secret"]}

    def update_all_members(self):
        all_member_ids = self.get_user_ids("0")
        all_member_ids = list(set(all_member_ids))
        arr = np.array_split(all_member_ids, 5)
        result = []
        for lis in arr:
            query = "employee_ids={}".format("&employee_ids=".join(lis))
            data = requests.get(
                url="https://open.feishu.cn/open-apis/contact/v1/user/batch_get?{}".format(
                    query
                ),
                headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
            ).json()
            if data["code"] == 0:
                result.extend(data["data"]["user_infos"])
            else:
                raise Exception("获取用户列表失败" + data["msg"])
        user_infos = pd.DataFrame(result)
        user_infos.to_csv(
            "{}/config/lark-users.csv".format(self.root), encoding="utf_8_sig"
        )

    def get_user_ids(self, department_id):
        has_more = True
        department_children = []
        users = []
        data = requests.get(
            url="https://open.feishu.cn/open-apis/contact/v3/departments/{}/children?page_size=50".format(
                department_id
            ),
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        if data["code"] == 0:
            for item in data["data"].get("items", []):
                department_children.append(item["open_department_id"])
        else:
            raise Exception("获取用户id列表失败" + data["msg"])
        for department_child in department_children:
            child_users = self.get_user_ids(department_child)
            users.extend(child_users)
        data = requests.get(
            url="https://open.feishu.cn/open-apis/contact/v3/users/find_by_department?page_size=50&user_id_type=user_id&department_id={}".format(
                department_id
            ),
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        if data["code"] == 0:
            for item in data["data"].get("items", []):
                users.append(item["user_id"])
        else:
            raise Exception("获取用户id列表失败" + data["msg"])
        return users

    def update_all_groups(self):
        data = requests.get(
            url="https://open.feishu.cn/open-apis/chat/v4/list",
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        print(data)
        if data["code"] == 0:
            groups = pd.DataFrame(data["data"]["groups"])
            groups.to_csv(
                "{}/config/lark-user-groups.csv".format(self.root), encoding="utf_8_sig"
            )
        else:
            raise Exception("获取主机器人所在群列表失败")

    def get_user_info(self, usernames=None):
        if usernames is None or len(usernames) == 0:
            return None
        user_infos = pd.read_csv("{}/config/lark-users.csv".format(self.root))
        if user_infos["name"].duplicated().any():
            logging.error("有重名用户，请检查")
        else:
            pattern = []
            for name in usernames:
                pattern.append("^{}$".format(name))
            pattern = "|".join(pattern)
            pattern = r"" + pattern
            return user_infos[user_infos["name"].str.contains(pattern)]

    def _get_open_ids(self, usernames=None):
        # 如果有同花名用户则抛出异常
        return self.get_user_info(usernames=usernames)[open_id_type].values.tolist()

    def get_group_info(self, groupnames=None):
        groups = pd.read_csv("{}/config/lark-user-groups.csv".format(self.root))
        if groupnames is None or len(groupnames) == 0:
            return None
        if groups["name"].duplicated().any():
            raise Exception("有重名群，请检查")
        else:
            pattern = []
            for name in groupnames:
                pattern.append("^{}$".format(name))
            pattern = "|".join(pattern)
            pattern = r"" + pattern
            return groups[groups["name"].str.contains(pattern)]

    def _get_group_ids(self, groupnames=None):
        # 如果有同名group则抛出异常
        return self.get_group_info(groupnames=groupnames)["chat_id"]

    def _get_user_info_by_id(self, user_id=None):
        data = requests.get(
            url="https://open.feishu.cn/open-apis/contact/v3/users/{}".format(user_id),
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        return data

    def send_message(
        self, receive_id_type=open_id_type, receive_id=None, content="", msg_type="text"
    ):
        msg_body = json.dumps(
            {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": json.dumps(content),
            }
        )
        response = requests.post(
            url="https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={}".format(
                receive_id_type
            ),
            headers={
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": "application/json; charset=utf-8",
            },
            data=msg_body,
        )
        result = response.json()
        headers = response.headers
        return result, headers

    def update_card_message(self, token=None, open_ids=None, content=None):
        content[f"{open_id_type}s"] = open_ids
        msg_body = json.dumps({"token": token, "card": content})
        result = requests.post(
            url="https://open.feishu.cn/open-apis/interactive/v1/card/update/",
            headers={
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": "application/json; charset=utf-8",
            },
            data=msg_body,
        ).json()
        return result

    def send_message_batch(self, open_ids=None, content="", msg_type="text"):
        msg_body = {
            f"{open_id_type}s": open_ids,
            "msg_type": msg_type,
        }
        if msg_type == "interactive":
            msg_body["card"] = json.dumps(content)
            msg_body["card"] = content
        else:
            msg_body["content"] = content
        msg_body = json.dumps(msg_body)
        response = requests.post(
            url="https://open.feishu.cn/open-apis/message/v4/batch_send/",
            headers={
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": "application/json",
            },
            data=msg_body,
        )
        result = response.json()
        headers = response.headers
        return result, headers

    def upload_file(self, file_path=None, file_name=None):

        form = {
            "file_type": "stream",
            "file_name": file_name,
            "file": (file_name, open(file_path, "rb"), "text/plain"),
        }  # 需要替换具体的path  具体的格式参考  https://www.w3school.com.cn/media/media_mimeref.asp
        multi_form = MultipartEncoder(form)
        result = requests.post(
            url="https://open.feishu.cn/open-apis/im/v1/files",
            headers={
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": multi_form.content_type,
            },
            data=multi_form,
        ).json()
        return result

    def get_history_msg(
        self,
        container_id_type="chat",
        container_id=None,
        start_time=None,
        end_time=None,
        page_token=None,
        page_size=50,
    ):
        msg_body = json.dumps(
            {
                "container_id_type": container_id_type,
                "container_id": container_id,
                "start_time": start_time,
                "end_time": end_time,
                "page_token": page_token,
                "page_size": page_size,
            }
        )
        query = "container_id_type={}&container_id={}".format(
            container_id_type, container_id
        )
        if page_token:
            query += "&page_token={}".format(page_token)
        result = requests.get(
            url="https://open.feishu.cn/open-apis/im/v1/messages?{}".format(query),
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        return result

    def get_read_users(self, message_id=None):
        result = requests.get(
            url="https://open.feishu.cn/open-apis/im/v1/messages/{}/read_users?user_id_type=open_id&page_size=100".format(
                message_id
            ),
            headers={"Authorization": "Bearer {}".format(self.tenant_access_token)},
        ).json()
        return result


if __name__ == "__main__":
    br = BaseRobot()
    # br.get_user_access_token(code="2DysHbc6K3054Exw90DKeKH5z6Iz1baw")
    br.update_all_members()
    # br.update_all_groups()
    # open_ids = []
    # user_list = []
    # for open_id in open_ids:
    #     data = br._get_user_info_by_id(user_id=open_id)
    #     try:
    #         print(data['data']['user']['name'], open_id)
    #         _item = {open_id_type: open_id, 'name': data['data']['user']['name']}
    #         user_list.append(_item)
    #     except:
    #         print(data, open_id)
    # pd.DataFrame(data=user_list).to_csv('user.csv', index=False)
