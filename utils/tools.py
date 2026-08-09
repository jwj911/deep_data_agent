import os
from configobj import ConfigObj
import json
from urllib import parse
from urllib.parse import quote
import datetime
import logging
import re
from functools import lru_cache
import unicodedata

def get_root_path():
    this_file_name = os.path.join('utils', 'tools.py')
    return os.path.dirname(os.path.abspath(__file__).replace(this_file_name, ''))


@lru_cache(maxsize=10)
def get_config():
    file_path = 'application.cfg'
    config_path = os.path.join(get_root_path(), file_path)
    config = ConfigObj(config_path)
    return config


def get_subscription_config(task_name='', subscription=None):
    task_cfg = get_json_file('subscriptions/{}.json'.format(task_name))
    if subscription is None:
        return task_cfg
    subscriptions = list(filter(lambda x: x.get(
        'subscription_name', '') == subscription, task_cfg.get('subscriptions', [])))
    if len(subscriptions) == 0:
        logging.error('subscription {} is not found'.format(subscription))
    subscription_cfg = subscriptions[0]
    return task_cfg, subscription_cfg


def get_json_file(file_path, encoding='utf-8'):
    file_path = os.path.join(
        get_root_path(), file_path)
    with open(file_path, encoding=encoding) as template:
        normalized_content = unicodedata.normalize('NFKC', template.read())
        data = json.loads(normalized_content)
    return data

def get_text_file(file_path:str=None):
    file_path = os.path.join(
        get_root_path(), file_path)
    with open(file_path, encoding='utf-8') as template:
        data = template.read()
    return data

def json2file(data, file_path):
    file_path = os.path.join(
        get_root_path(), file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))

def remove_emoji(text:str=""):
    filtered_text = re.sub(r"[^\w\s,.?!''，。？！]", "", text)
    filtered_text = filtered_text.lower().strip()
    
    # 检测是否只包含标点符号和空格，没有有效的字母、数字或中文字符
    # 移除所有标点符号和空格，检查是否还有内容
    content_only = re.sub(r"[,.?!''，。？！\s]", "", filtered_text)
    if not content_only:
        return ""
    
    return filtered_text

if __name__ == '__main__':
    print(get_root_path())
    # print(get_config())
    # url = gen_redirect_url('http://www.baidu.com?xixi=中国&haha=houhou', params={'key': 'value'})
    # print(url)
    # task_list = get_tasks()
    # print(task_list)
    # data = get_text_file(file_path="results/spk/test.txt")
    # print(data)


    
