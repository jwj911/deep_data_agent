# -*- coding: utf-8 -*-

from utils.tools import get_config, get_root_path
from utils.base_robot import BaseRobot
import json
import requests
import pandas as pd
import math
import time
import numpy as np
import os
from utils.log import init_log

logger = init_log("multidimension_table_robot")


class MultidimensionTable(BaseRobot):

    def __init__(self, robot_name: str = None):
        super().__init__(robot_name=robot_name)

    def download_attachment(
        self, file_token: str = None, save_path: str = None, extra: str = ""
    ):
        if save_path is None:
            root_path = get_root_path()
            save_path = os.path.join(root_path, "temp", "test.m4a")
        url = f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download"
        if len(extra) > 0:
            url += f"?extra={extra}"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
        }
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()  # 如果响应状态码不是 200，抛出异常
            # 写入文件到本地
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):  # 每次读取 8KB
                    if chunk:
                        f.write(chunk)

        print(f"✅ 文件已成功下载并保存至: {save_path}")

    def to_dict(self, data: pd.DataFrame = None):
        for key in data.columns:
            if data[key].dtype == "datetime64[ns]":
                data[key] = pd.to_datetime(data[key])
                data[key] = data[key].astype(int) / 1000000
                data[key].astype(int)
        data = data.to_dict(orient="records")
        return data

    def insert_data2table(
        self,
        insert_data: pd.DataFrame = None,
        table_name="",
        table_id="",
        mode="by_config",
    ):
        insert_data = insert_data.replace(np.nan, None)
        # insert_data.fillna("", inplace=True)
        if insert_data.shape[0] == 0:
            return
        data_list = self.to_dict(insert_data)
        page_size = 500
        total_page = math.ceil(len(insert_data) / page_size)
        global_config = get_config()
        if mode == "by_config":
            table_config = global_config.get("multidimension_table").get(table_name)
            token = table_config.get("token")
            table_id = table_config.get(table_id)
        elif mode == "by_origin":
            token = table_name
            table_id = table_id
        url = "https://open.feishu.cn/open-apis/bitable/v1/apps/{}/tables/{}/records/batch_create".format(
            token, table_id
        )
        for page in range(0, total_page):
            insert_data = data_list[page * page_size : (page + 1) * page_size]
            data = {"records": []}
            for item in insert_data:
                data["records"].append({"fields": item})
            data = json.dumps(data)
            headers = {
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": "application/json; charset=utf-8",
            }
            response = requests.post(url=url, headers=headers, data=data).json()
        return response

    def _retrieve(
        self,
        filter=None,
        table_name="",
        table_id="",
        page_size=500,
        page_token=None,
        mode="by_config",
    ):
        global_config = get_config()
        if mode == "by_config":
            table_config = global_config.get("multidimension_table").get(table_name)
            token = table_config.get("token")
            table_id = table_config.get(table_id)
        elif mode == "by_origin":
            token = table_name
            table_id = table_id
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{token}/tables/{table_id}/records/search?page_size={page_size}"
        body = {}
        if filter:
            body["filter"] = filter
        if page_token:
            url += "&page_token={}".format(page_token)
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        response = requests.post(url=url, headers=headers, data=json.dumps(body)).json()
        page_token = None
        if response.get("data", {}).get("has_more", False):
            page_token = response["data"]["page_token"]
        if response["msg"] != "success":
            return pd.DataFrame(), None
        response = response["data"]["items"]
        res = []
        for item in response:
            item["fields"]["record_id"] = item["record_id"]
            item = item["fields"]
            keys = item.keys()
            for key in keys:
                if (
                    isinstance(item[key], list)
                    and len(item[key]) >= 1
                    and isinstance(item[key][0], dict)
                    and item[key][0].get("type") == "text"
                ):
                    item[key] = "\n".join([_item["text"] for _item in item[key]])
            res.append(item)
        response = res
        response = pd.DataFrame(data=response)
        return res, page_token

    def retrieve(
        self,
        filter=None,
        table_name="",
        table_id="",
        page_size=500,
        page_token=None,
        total_num=500,
        mode="by_config",
    ) -> pd.DataFrame:
        res = []
        total = 0
        if total_num < page_size:
            page_size = total_num
        while True and total < total_num:
            data, page_token = self._retrieve(
                filter=filter,
                table_name=table_name,
                table_id=table_id,
                page_size=page_size,
                page_token=page_token,
                mode=mode,
            )
            res.extend(data)
            total += len(data)
            if not page_token:
                break
        res = pd.DataFrame(data=res)
        res = res[0:total_num]
        return res

    def update_data2table(
        self, update_data=[{}], table_name="", table_id="", mode="by_config"
    ):  # mode: by_config, by_origin
        data = {"records": []}
        for item in update_data:
            record_id = item.get("record_id")
            del item["record_id"]
            data["records"].append({"record_id": record_id, "fields": item})
        global_config = get_config()
        table_config = global_config.get("multidimension_table").get(table_name)
        if mode == "by_config":
            token = table_config.get("token")
            table_id = table_config.get(table_id)
        elif mode == "by_origin":
            token = table_name
            table_id = table_id
        url = "https://open.feishu.cn/open-apis/bitable/v1/apps/{}/tables/{}/records/batch_update".format(
            token, table_id
        )
        data = json.dumps(data)
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        response = requests.post(url=url, headers=headers, data=data).json()
        return response

    def _export_task(self, file_token: str = ""):
        url = "https://open.feishu.cn/open-apis/drive/v1/export_tasks"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        body = {
            "file_extension": "xlsx",
            "token": file_token,
            "type": "sheet",
        }
        response = requests.post(url=url, headers=headers, data=json.dumps(body))
        return response.json()

    def wait_until_export_finished(
        self, export_id: str = "", file_token: str = "", count: str = 0
    ):
        MAX_TRY = 60
        SLEEP_GAP = 1

        url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks/{export_id}?token={file_token}"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        res = requests.get(url=url, headers=headers)
        res = res.json()
        if (
            res.get("data", {}).get("result", {}).get("job_status") not in [0, 1, 2]
            or count > MAX_TRY
        ):
            return False
        elif res.get("data", {}).get("result", {}).get("job_status") == 0:
            return res.get("data", {}).get("result", {}).get("file_token")
        else:
            time.sleep(SLEEP_GAP)
            return self.wait_until_export_finished(
                export_id=export_id, file_token=file_token, count=count + 1
            )

    def download_file(self, file_token: str = "", file_name: str = ""):
        res = self._export_task(file_token=file_token)
        res = self.wait_until_export_finished(
            export_id=res["data"]["ticket"], file_token=file_token
        )
        if res is not False:
            url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks/file/{res}/download"
            headers = {
                "Authorization": "Bearer {}".format(self.tenant_access_token),
                "Content-Type": "application/json; charset=utf-8",
            }
            res = requests.get(url=url, headers=headers)
            with open(file_name, "wb") as f:
                f.write(res.content)

    def get_by_record_ids(
        self, record_id_list: list = [], table_name: str = "", table_id: str = ""
    ):
        global_config = get_config()
        table_config = global_config.get("multidimension_table").get(table_name)
        token = table_config.get("token")
        table_id = table_config.get(table_id)
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{token}/tables/{table_id}/records/batch_get"
        data = {"record_ids": record_id_list}
        data = json.dumps(data)
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        response = requests.post(url=url, headers=headers, data=data).json()
        if response["msg"] != "success":
            return pd.DataFrame(), None
        response = response["data"]["records"]
        res = []
        for item in response:
            item["fields"]["record_id"] = item["record_id"]
            item = item["fields"]
            keys = item.keys()
            for key in keys:
                if (
                    isinstance(item[key], list)
                    and len(item[key]) >= 1
                    and isinstance(item[key][0], dict)
                    and item[key][0].get("type") == "text"
                ):
                    item[key] = "\n".join([_item["text"] for _item in item[key]])
            res.append(item)
        return pd.DataFrame(data=res)

    def get_lark_files(
        self, file_name: str = "", after_time: int = 0, file_type="sheet"
    ):
        url = "https://open.feishu.cn/open-apis/drive/v1/files?direction=DESC&order_by=EditedTime&page_size=50"
        user_access_token = self.refresh_user_access_token()
        headers = {
            "Authorization": "Bearer {}".format(user_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        res = requests.get(url=url, headers=headers)
        res = res.json()
        if res["msg"] != "success":
            return None
        files = res.get("data", {}).get("files", [])
        for file in files:
            # 检查文件名是否匹配
            name_condition = file_name and file.get("name") == file_name
            type_condition = file_type and file.get("type") == file_type
            time_condition = (
                after_time and int(file.get("created_time", 0)) >= after_time
            )
            if name_condition and type_condition and time_condition:
                return file.get("token")

    def insert_or_update_data2table(
        self,
        data: pd.DataFrame = None,
        table_name: str = "",
        table_id: str = "",
        id_columns: list = [],
        mode: str = "by_config",
    ) -> dict:
        exist_df = self.retrieve(
            table_name=table_name,
            table_id=table_id,
            total_num=500000,
            mode=mode,
        )
        update_list = pd.DataFrame()
        insert_data = pd.DataFrame()
        if exist_df.shape[0] > 0:
            data["_id"] = data[id_columns].apply(
                lambda row: "_".join(row.astype(str)), axis=1
            )
            exist_df["_id"] = exist_df[id_columns].apply(
                lambda row: "_".join(row.astype(str)), axis=1
            )
            insert_data = data[~data["_id"].isin(exist_df["_id"])]
            insert_data.drop(columns=["_id"], inplace=True)
            update_list = data[data["_id"].isin(exist_df["_id"])]
            exist_df = exist_df[id_columns + ["record_id"]]
            if update_list.shape[0] > 0:
                update_list = update_list.merge(exist_df, on=id_columns, how="left")
                update_list.drop(columns=["_id"], inplace=True)
        else:
            insert_data = data
        if update_list.shape[0] > 0:
            update_list = update_list.replace({np.nan: None}).to_dict(orient="records")
            res_update = self.update_data2table(
                update_data=update_list,
                table_name=table_name,
                table_id=table_id,
                mode=mode,
            )
            logger.info(f"update data done, res: {res_update}")
        if insert_data.shape[0] > 0:
            insert_data = insert_data.replace({np.nan: None})
            res_insert = self.insert_data2table(
                insert_data=insert_data,
                table_name=table_name,
                table_id=table_id,
                mode=mode,
            )
            logger.info(f"insert data done, res: {res_insert}")

    def get_table_id_by_name(
        self, table_token: str = None, table_name: str = None
    ) -> str:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables"
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json",
        }
        res = requests.get(url=url, headers=headers).json()
        table_list = res.get("data", {}).get("items", [])
        for item in table_list:
            if item.get("name") == table_name:
                return item.get("table_id")
        return None

    def delete_table(
        self, table_token: str = "", table_id: str = None, table_name: str = None
    ):
        if table_name is not None and table_id is None:
            table_id = self.get_table_id_by_name(
                table_token=table_token, table_name=table_name
            )
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables/{table_id}"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
        }
        res = requests.delete(url=url, headers=headers).json()
        if res["msg"] != "success":
            return None
        return res

    def create_table(
        self, table_name: str = "", table_token: str = "", fields: list = []
    ):
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        data = {
            "table": {
                "name": table_name,
                "default_view_name": "查询结果",
                "fields": fields,
            }
        }
        res = requests.post(url=url, headers=headers, json=data).json()
        if res["msg"] != "success":
            return None
        return res["data"]["table_id"]

    def df2table(
        self, data: pd.DataFrame = None, table_token: str = "", table_name: str = ""
    ):
        columns = data.columns.tolist()
        fields = []
        for column in columns:
            fields.append(
                {
                    "field_name": column,
                    "type": 1,
                }
            )
        self.delete_table(table_token=table_token, table_name=table_name)
        table_id = self.create_table(
            table_name=table_name, table_token=table_token, fields=fields
        )

        if table_id:
            data = data.astype(str)
            res = self.insert_data2table(
                insert_data=data,
                table_name=table_token,
                table_id=table_id,
                mode="by_origin",
            )
            return table_id

    @classmethod
    def extract_person(cls, data):
        if pd.isna(data):
            return None
        return ",".join([item["name"] for item in data])


if __name__ == "__main__":
    table = MultidimensionTable()
    # table.download_attachment()
    table.download_file(file_token="BqFBskbTThqlwdt9V1scB9hjnhc", file_name="test.xlsx")
