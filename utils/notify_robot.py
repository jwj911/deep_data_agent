import requests
import pandas as pd
import os
import json
from utils.base_robot import BaseRobot
from utils.log import init_log
from utils.tools import get_root_path
import logging

init_log("notify_robot")


class NotifyRobot(BaseRobot):

    def __init__(self, robot_name: str = None):
        super().__init__(robot_name=robot_name)

    def notify_by_groupnames(self, groupnames=None, content="", msg_type="text"):
        self._get_tenant_access_token()
        group_ids = self._get_group_ids(groupnames)
        if group_ids.shape[0] != len(groupnames):
            logging.error("有群{}未找到,请核查".format(groupnames))
        res = self.notify_by_groupids(
            group_ids=group_ids, content=content, msg_type=msg_type
        )
        return res

    def notify_by_groupids(self, group_ids=None, content="", msg_type="text"):
        self._get_tenant_access_token()
        res = {}
        for chat_id in group_ids:
            _res, _headers = self.send_message(
                receive_id=chat_id, content=content, msg_type=msg_type
            )
            res["res_{}".format(chat_id)] = _res
            res["headers_{}".format(chat_id)] = _headers
            logging.info(
                "notify_by_groupids{}-{}-{}-{}".format(
                    str(_res), chat_id, content, msg_type
                )
            )
        return res

    def notify_by_usernames(self, usernames=None, content="", msg_type="text"):
        self._get_tenant_access_token()
        open_ids = self._get_open_ids(usernames)
        if len(open_ids) != len(usernames):
            logging.error("有用户{}未找到,请核查".format(usernames))
        res, headers = self.notify_by_open_ids(
            open_ids=open_ids, content=content, msg_type=msg_type
        )
        return res, headers

    def notify_by_open_ids(self, open_ids=None, content="", msg_type="text"):
        res, headers = self.send_message_batch(
            open_ids=open_ids, content=content, msg_type=msg_type
        )
        logging.info(
            "notify_by_open_ids{}-{}-{}-{}".format(
                str(res), open_ids, content, msg_type
            )
        )
        return res, headers

    def notify_by_open_id(self, open_id=None, content="", msg_type="text"):
        res, headers = self.send_message(
            receive_id=open_id, content=content, msg_type=msg_type
        )
        logging.info(
            "notify_by_open_id{}-{}-{}-{}".format(str(res), open_id, content, msg_type)
        )
        return res, headers

    def send_file_by_usernames(self, usernames=None, file_path=None, file_name=None):
        open_ids = self._get_open_ids(usernames)
        res = self.send_file_by_open_ids(
            open_ids=open_ids, file_path=file_path, file_name=file_name
        )
        logging.info(
            "send_file_by_usernames{}-{}-{}-{}".format(
                str(res), usernames, file_path, file_name
            )
        )
        return res

    def send_file_by_open_ids(self, open_ids=None, file_path=None, file_name=None):
        res = self.upload_file(file_path, file_name)
        if res["code"] == 0:
            file_key = res["data"]["file_key"]
            for open_id in open_ids:
                res, headers = self.send_message(
                    receive_id_type="open_id",
                    receive_id=open_id,
                    content={
                        "file_key": file_key,
                    },
                    msg_type="file",
                )
                logging.info(
                    "send_file_by_open_ids{}-{}-{}".format(str(res), open_id, file_key)
                )
            return True
        else:
            return False

    def get_history_msg_by_groupnames(
        self, groupnames=[], start_time=None, end_time=None, page_num=1000
    ):
        group_ids = self._get_group_ids(groupnames)
        page_token = None
        count = 0
        kpnews = 0
        content_list = []
        for group_id in group_ids:
            while True:
                res = self.get_history_msg(
                    container_id=group_id,
                    start_time=start_time,
                    end_time=end_time,
                    page_token=page_token,
                )
                if res["code"] == 0:
                    page_token = res["data"].get("page_token", None)
                    items = res["data"]["items"]
                    content_list.extend(items)
                if page_token == "" or count >= page_num:
                    break
                count += 1
        return content_list


if __name__ == "__main__":
    nr = NotifyRobot()
    # yesterday = (pd.to_datetime('today') -
    #              pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    res = nr.notify_by_usernames(
        usernames=["韦辰睿"], content={"text": "欢迎辰睿进行内测"}, msg_type="text"
    )
    print(res)
