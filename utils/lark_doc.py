# -*- coding: utf-8 -*-

from utils.tools import get_config, get_root_path
from utils.base_robot import BaseRobot
import json
import requests
import pandas as pd
import math
import time
import os


class LarkDoc(BaseRobot):

    def __init__(
        self, robot_name: str = None, folder_token: str = "COk5fVSROl9A0Rd535ecEaJsnQh"
    ):
        super().__init__(robot_name=robot_name)
        self.folder_token = folder_token
        # self.folder_token = None

    def _create_doc(self, title: str = "新建文档"):
        url = "https://open.feishu.cn/open-apis/docx/v1/documents"
        data = json.dumps(
            {
                "folder_token": self.folder_token,
                "title": title,
            }
        )
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        res = requests.post(url=url, headers=headers, data=data).json()
        return res.get("data").get("document").get("document_id")

    def _gen_content(self, content: str = None, content_type="markdown"):
        url = "https://open.feishu.cn/open-apis/docx/v1/documents/blocks/convert"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        data = json.dumps(
            {
                "content": content,
                "content_type": content_type,
            }
        )
        res = requests.post(url=url, headers=headers, data=data).json()
        blocks = res.get("data").get("blocks")
        children_id = res.get("data").get("first_level_block_ids")
        return children_id, blocks

    def _insert_content(
        self, document_id: str = None, children_id: list = [], descendants: list = []
    ):
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/descendant"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        data = json.dumps(
            {
                "children_id": children_id,
                "descendants": descendants,
            }
        )
        res = requests.post(url=url, headers=headers, data=data).json()
        print(res)

    def gen_doc(self, title: str = None, content: str = None):
        document_id = self._create_doc(title=title)
        children_id, blocks = self._gen_content(content=content)

        self._insert_content(
            document_id=document_id, children_id=children_id, descendants=blocks
        )
        return document_id

    def get_content(self, document_id: str = None):
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/raw_content?lang=0"
        headers = {
            "Authorization": "Bearer {}".format(self.tenant_access_token),
            "Content-Type": "application/json; charset=utf-8",
        }
        res = requests.get(url=url, headers=headers).json()
        if res.get("code") != 0:
            return None
        return res.get("data").get("content")


if __name__ == "__main__":
    ld = LarkDoc()
    content = f"""
- **公司概况**  
  创业公司专注于通过AI生成个性化音频内容，围绕书籍讲解、资讯摘要及娱乐化内容构建平台。创始人曾任职于零一万物、商汤科技，具备大模型研发与产品化经验，团队定位为“以音频为核心的内容生产与消费平台”。

- **业务**  
  - **技术**：基于MiniMax、Google等TTS模型复刻音色与个性化风格，利用提示工程（prompt engineering）和SFT实现风格化内容生成（如“蒋勋讲《红楼梦》”）。  
  - **产品**：初期聚焦书籍讲解，支持用户选择不同“host”风格（如丘吉尔、川普）生成内容，后续扩展至资讯、论文聚合及娱乐化音频短剧。  
  - **应用场景**：满足用户碎片化时间的高质量信息获取需求，目标人群为“想阅读但无暇深入阅读”的用户。  
  - **未来规划**：从音频切入，探索视频工具端机会，长期目标为构建内容生产、消费与分发的综合平台。

- **市场分析**  
  - **痛点**：传统音频内容生产成本高、个性化不足，用户需依赖人工创作者。  
  - **增长驱动力**：AI生成降低创作门槛，提供高度个性化内容；音频形态适配通勤、运动等场景。  
  - **竞争格局**：竞争者包括Pocket FM（印度音频短剧平台）、喜马拉雅、番茄小说等，但差异化在于AI生成效率及风格化能力。

- **商业模式**  
  - **收费模式**：采用订阅制，用户付费获取特定host内容或高级功能（如自定义音色复刻）。  
  - **销售渠道**：通过社交媒体（小红书等）推广，结合内容创作者合作分发。

- **财务数据**  
  未明确披露营收、毛利及现金流，但提到当前注册用户约1万（含中国与海外），付费用户占比约7%，续费率约60%（数据量较小）。

- **团队情况**  
  - **核心成员背景**：创始人具备大模型研发与产品化经验，团队成员包括设计师、前后端开发者，后续计划引入算法专家与市场运营人才。  
  - **团队总人数及股权分配**：当前全职5人，未提及具体股权分配。

- **融资需求**  
  - **融资历史**：近期完成种子轮，由明势资本领投，估值约1600万美元，融资额400万美元。  
  - **本轮融资**：计划用于团队扩张（算法、市场岗位）、产品迭代（娱乐化方向）及用户增长。  
  - **核心业务拓展规划与融资用途**：优先打磨音频内容消费闭环，验证用户反馈机制，后续探索工具化与多模态内容扩展。
    """
    # content = "test"
    # ld.gen_doc(title="test", content=content)

    ld.get_content(document_id="OsJ6d9BYPoiFxnxUxcDcZQp7n2f")
