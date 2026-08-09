# -*- coding: utf-8 -*-
from utils.base_robot import BaseRobot
import requests


class LarkMinutes(BaseRobot):

    def __init__(self, robot_name: str = None):
        super().__init__(robot_name=robot_name)
        

    def get_transcript(self, minutes_url: str = None, minutes_token: str = None):
        if minutes_url is not None:
            minutes_token = minutes_url.split("/")[-1]
        url = f"https://open.feishu.cn/open-apis/minutes/v1/minutes/{minutes_token}/transcript?file_format=txt&need_speaker=true"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        res = requests.get(url=url, headers=headers)
        if res.status_code != 200:
            raise Exception(f"获取飞书妙计失败，状态码：{res.status_code}")
        res = res.content.decode('utf-8').split('\n\n')[2:]
        res = [i.replace(" \n", ": ") for i in res]
        res = '\n'.join(res)
        return res

if __name__ == "__main__":
    lm = LarkMinutes()
    lm.get_transcript(minutes_url = "https://s3tlxskbq3.feishu.cn/minutes/obcnzj7211f47437u4d4cern")
