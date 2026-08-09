# -*- coding: utf-8 -*-

# 将文件保存到oss
# 配置环境变量
# mac
# echo "export OSS_ACCESS_KEY_ID='LTAI5tDHwJpXvf98AbkM6Dnp'" >> ~/.zshrc
# echo "export OSS_ACCESS_KEY_SECRET='ux6YM8PzYdbbL4hTYliV1KGmwViV7j'" >> ~/.zshrc
# source ~/.zshrc
# linux
# echo "export OSS_ACCESS_KEY_ID='LTAI5tDHwJpXvf98AbkM6Dnp'" >> ~/.bashrc
# echo "export OSS_ACCESS_KEY_SECRET='ux6YM8PzYdbbL4hTYliV1KGmwViV7j'" >> ~/.bashrc
# source ~/.bashrc
# echo $OSS_ACCESS_KEY_ID
# echo $OSS_ACCESS_KEY_SECRET
import os

import oss2
from oss2 import determine_part_size, SizedFileAdapter
from oss2.models import PartInfo
from utils.tools import get_config
import alibabacloud_oss_v2 as oss
import argparse

app_config = get_config()


class OssAli:
    @classmethod
    def save_data_to_oss(
        cls, oss_data_base_path: str = "test.wav", file_path: str = ""
    ):
        oss_config = app_config.get("oss", {})
        access_key_id = oss_config.get("access_key_id")
        access_key_secret = oss_config.get("access_key_secret")
        endpoint = oss_config.get("endpoint")
        bucket_name = oss_config.get("bucket_name")
        bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret), endpoint, bucket_name
        )
        total_size = os.path.getsize(file_path)
        part_size = determine_part_size(total_size, preferred_size=100 * 1024)
        upload_id = bucket.init_multipart_upload(oss_data_base_path).upload_id
        parts = []
        with open(file_path, "rb") as fileobj:
            part_number = 1
            offset = 0
            while offset < total_size:
                print("uploading")
                num_to_upload = min(part_size, total_size - offset)
                result = bucket.upload_part(
                    oss_data_base_path,
                    upload_id,
                    part_number,
                    SizedFileAdapter(fileobj, num_to_upload),
                )
                parts.append(PartInfo(part_number, result.etag))
                offset += num_to_upload
                part_number += 1
        bucket.complete_multipart_upload(oss_data_base_path, upload_id, parts)

    # 查询指定目录数据
    @classmethod
    def get_data_from_oss(cls, oss_data_base_path: str = ""):
        oss_config = app_config.get("oss", {})
        access_key_id = oss_config.get("access_key_id")
        access_key_secret = oss_config.get("access_key_secret")
        endpoint = oss_config.get("endpoint")
        bucket_name = oss_config.get("bucket_name")
        bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret), endpoint, bucket_name
        )
        # for obj in oss2.ObjectIteratorV2(bucket):
        #     print(obj.key)
        result = bucket.list_objects(oss_data_base_path)
        return [obj.key for obj in result.object_list]

    # 删除指定目录数据
    @classmethod
    def delete_data_from_oss(cls, oss_data_base_path: str = ""):
        app_config = get_config()
        oss_config = app_config.get("oss", {})
        access_key_id = oss_config.get("access_key_id")
        access_key_secret = oss_config.get("access_key_secret")
        endpoint = oss_config.get("endpoint")
        bucket_name = oss_config.get("bucket_name")
        bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret), endpoint, bucket_name
        )
        result = bucket.list_objects(oss_data_base_path)
        for obj in result.object_list:
            bucket.delete_object(obj.key)

    @classmethod
    def get_sign_link(cls, oss_data_base_path: str = "", file_name: str = ""):
        parser = argparse.ArgumentParser(description="presign get object sample")
        parser.add_argument(
            "--region",
            help="The region in which the bucket is located.",
            default="cn-beijing",
        )
        parser.add_argument(
            "--bucket",
            help="The name of the bucket.",
            default=app_config.get("oss", {}).get("bucket_name"),
        )
        parser.add_argument(
            "--endpoint",
            help="The domain names that other services can use to access OSS",
            default="https://oss-cn-beijing.aliyuncs.com",
        )
        parser.add_argument("--key", help="The name of the object.", default=file_name)
        args = parser.parse_args()
        credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()
        cfg = oss.config.load_default()
        cfg.credentials_provider = credentials_provider
        cfg.region = args.region
        if args.endpoint is not None:
            cfg.endpoint = args.endpoint

        # 使用上述配置初始化OSS客户端，准备与OSS交互
        client = oss.Client(cfg)

        # 生成预签名的GET请求
        pre_result = client.presign(
            oss.GetObjectRequest(
                bucket=args.bucket,  # 指定存储空间名称
                key=args.key,  # 指定对象键名
            )
        )
        print(pre_result.url)

        # # 打印预签名请求的方法、过期时间和URL
        # print(f'method: {pre_result.method},'
        #     f' expiration: {pre_result.expiration.strftime("%Y-%m-%dT%H:%M:%S.000Z")},'
        #     f' url: {pre_result.url}'
        # )

        # # 打印预签名请求的已签名头信息
        for key, value in pre_result.signed_headers.items():
            print(f"signed headers key: {key}, signed headers value: {value}")
        return pre_result.url


if __name__ == "__main__":

    OssAli.get_sign_link()
