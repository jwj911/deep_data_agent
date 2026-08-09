from elasticsearch import Elasticsearch, exceptions
from elasticsearch.helpers import bulk
import datetime
import sys
import warnings
import pandas as pd
warnings.filterwarnings('ignore')
from datetime import datetime, timedelta


class TourSkyElasticsearch(object):
    def __init__(self, url='http://localhost:9200', username='elastic', password=None):
        if password is None:
            password = os.environ.get("ES_PASSWORD")
            if not password:
                raise ValueError("Environment variable ES_PASSWORD is not set")
        self.client = Elasticsearch(
            url,
            basic_auth=(username, password)
            # ca_certs=False,
            # verify_certs=False
        )

    def create_index(self, index_name=None, mappings={}):
        return self.client.indices.create(index=index_name, body=mappings)

    def del_index(self, index_name=None):
        return self.client.indices.delete(index=index_name, ignore=[400, 404])

    def exit_ids(self, data, id_name, index_name):
        ids = data[id_name].tolist()
        ids = list(map(lambda item: {"match_phrase": {
            '_id': item
        }}, ids))
        query = {
            "query": {
                "bool": {
                    "should": ids
                }
            },
            '_source': ['_id'],
            "size": 500,

        }
        result = self.client.search(index=index_name, body=query)
        exit_ids = list(map(lambda item: item['_id'],result['hits']['hits']))
        return exit_ids

    def insert_batch(self, index_name:str=None, data: pd.DataFrame = [], operate_type:str='index', id_name:str=None):
        exit_ids = self.exit_ids(data = data, id_name = id_name, index_name = index_name)
        data['if_drop'] = data.apply(
                lambda item: item[id_name] in exit_ids, axis=1)
        data = data[data['if_drop'] != True]
        actions = []
        for index, item in data.iterrows():
            action = {
                '_op_type': operate_type,
                '_source': item.to_dict()
            }
            if id_name is not None and item.get(id_name) is not None:
                action.update({'_id': item.get(id_name)})
            actions.append(action)
        return bulk(client=self.client, actions=actions, index=index_name, raise_on_exception=False, raise_on_error=False)
    
    def delete_documents_by_date_range(self, index_name, date_from, date_to):
        client = self.client

        # 转换日期字符串为 datetime 对象
        date_format = "%Y-%m-%d"
        date_from = datetime.strptime(date_from, date_format)
        date_to = datetime.strptime(date_to, date_format)

        # 删除指定日期范围内创建的所有文档
        query = {
            "query": {
                "range": {
                    "create_at": {
                        "gte": date_from.isoformat(),
                        "lt": (date_to + timedelta(days=1)).isoformat(),
                        "format": "yyyy-MM-dd'T'HH:mm:ss"
                    }
                }
            }
        }
        result = client.delete_by_query(index=index_name, body=query)
        
        # 返回删除的文档数
        return result["deleted"]
    
    def copy_index(self, source='', destination=''):
        reindex_body = {
            "source": {"index": source},
            "dest": {"index": destination}
        }
        response = self.client.reindex(body=reindex_body, request_timeout=1200)

if __name__ == '__main__':
    import os
    url = os.environ.get("ES_URL", "http://localhost:9200")
    tes = TourSkyElasticsearch(url=url)
    # tes.copy_index(source = 'index_toursky_news', destination = 'index4alignment')
    # res = tes.client.count(index='index4alignment', body={})
    # print(res)
    pass
    