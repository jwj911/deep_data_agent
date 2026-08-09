import requests
import json
from utils.tools import get_config
from utils.base_robot import BaseRobot

# 配置参数
app_config = get_config()
APP_ID = app_config['robot']['app_id'] # 替换为你的应用App ID
APP_SECRET = app_config['robot']['app_secret'] # 替换为你的应用App Secret

class LarkCard(BaseRobot):
    
    def send_card_message(self, chat_id: str=''):
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {
            "receive_id_type": "chat_id"
        }
        headers = {
            "Authorization": f"Bearer {self.tenant_access_token}",
            "Content-Type": "application/json"
        }
        
        # 卡片消息内容（根据实际需求修改）
        card_content = {
            "msg_type": "interactive",
            "card": {
                "elements": [{
                    "tag": "div",
                    "text": {
                        "content": "这是一条测试卡片消息\n时间：{{DATA_AGO}}",
                        "tag": "lark_md"
                    }
                }],
                "header": {
                    "title": {
                        "content": "测试卡片标题",
                        "tag": "plain_text"
                    }
                }
            }
        }
        
        data = {
            "receive_id": chat_id,
            "content": json.dumps(card_content),
            "msg_type": "interactive"
        }
        
        response = requests.post(url, params=params, headers=headers, json=data)
        result = response.json()
        return result

# 主程序
if __name__ == "__main__":
    lc = LarkCard()
    result = lc.send_card_message(chat_id='')