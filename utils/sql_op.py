from sqlalchemy import create_engine, text
import pandas as pd
import hashlib
import os
import logging
from utils.tools import get_root_path, get_config
from urllib.parse import quote_plus as urlquote
from sshtunnel import SSHTunnelForwarder

engine_map = {}
engine_map_pg = {}


def get_engine(database: str = None):
    if engine_map.get(database) is None:
        app_config = get_config()
        db_config = app_config["database"]
        host = db_config["host"]
        username = db_config["username"]
        password = db_config["password"]
        database = db_config[database]
        port = db_config.get("port", 3306)
        mysql_url = (
            f"mysql+mysqlconnector://{username}:{password}@{host}:{port}/{database}"
        )
        engine = create_engine(
            mysql_url,
            echo=False,
            pool_size=10,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        engine_map[database] = engine
    return engine_map[database]


def get_engine_pg(database: str = None):
    if engine_map_pg.get(database) is None:
        app_config = get_config()
        db_config = app_config["database_pg"]

        # SSH隧道配置
        ssh_host = db_config.get("ssh_host")
        ssh_port = int(db_config.get("ssh_port", 22))
        ssh_username = db_config.get("ssh_username")
        ssh_password = db_config.get("ssh_password", None)

        # 数据库配置
        db_host = db_config.get("host", "localhost")
        db_port = int(db_config.get("port", 5432))
        username = db_config["username"]
        password = db_config["password"]
        print(f"db_host: {db_host}, db_port: {db_port}, username: {username}, password: {password}")
        print(f"ssh_host: {ssh_host}, ssh_port: {ssh_port}, ssh_username: {ssh_username}, ssh_password: {ssh_password}")

        if ssh_host:
            # 创建SSH隧道
            tunnel = SSHTunnelForwarder(
                (ssh_host, ssh_port),
                ssh_username=ssh_username,
                ssh_password=ssh_password,
                remote_bind_address=(db_host, db_port),  # 确保这个参数有值
                local_bind_address=("127.0.0.1", 0),
            )
            tunnel.start()
            logging.info(
                f"SSH tunnel started for {database} on local port {tunnel.local_bind_port}"
            )
            # 通过SSH隧道连接
            pg_url = f"postgresql+pg8000://{username}:{password}@127.0.0.1:{tunnel.local_bind_port}/{database}"
        else:
            # 直接连接（无SSH隧道）
            pg_url = f"postgresql+pg8000://{username}:{password}@{db_host}:{db_port}/{database}"

        engine = create_engine(
            pg_url,
            echo=False,
            pool_size=10,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
        engine_map_pg[database] = engine

    return engine_map_pg[database]


# 参数要注意，不要误用
def insert_data(
    engine=None,
    database=None,
    table=None,
    data=None,
    gen_id_columns=[],
    full_columns=None,
    has_id=False,
    rename_id="id",
):
    if not has_id and len(gen_id_columns) > 0:
        unique_columns = [data[col] for col in gen_id_columns]
        data[rename_id] = ""
        data[rename_id] = data[rename_id].str.cat(unique_columns, sep="-")
        data = data.fillna("")
        data[rename_id] = data[rename_id].map(
            lambda item: hashlib.md5(item.encode("utf-8")).hexdigest()
        )
        has_id = rename_id
    if has_id:
        data.drop_duplicates(subset=has_id, keep="first", inplace=True)
        ids = ["{}".format(str(id)) for id in data[has_id].values.tolist()]
        ids_str = '("{}")'.format('","'.join([str(x) for x in ids]))
        table_exist_result = pd.read_sql(
            text("""
                SELECT * FROM information_schema.TABLES 
                WHERE table_name = :table_name AND table_schema = :table_schema
            """),
            engine,
            params={"table_name": table, "table_schema": database},
        )
        if table_exist_result.shape[0] > 0:
            placeholders = ", ".join([f":id_{i}" for i in range(len(ids))])
            exist_ids_query = text(
                f"select {has_id} from {table} where {has_id} in ({placeholders})"
            )
            params = {f"id_{i}": str(id_val) for i, id_val in enumerate(ids)}
            exist_ids = pd.read_sql(exist_ids_query, con=engine, params=params)
            data = data[~data[has_id].isin(exist_ids[has_id].values.tolist())]
        elif full_columns is not None:
            pd.DataFrame(columns=full_columns).to_sql(
                table, con=engine, if_exists="append", index=False
            )
    if data.shape[0] > 0:
        try:
            res = data.to_sql(con=engine, name=table, if_exists="append", index=False)
            logging.info(f"insert data success {res}")
            return res
        except Exception as e:
            logging.error(e)
            return None
    else:
        return None


def table_exist(table=None, database=None, engine=None):
    result = pd.read_sql(
        text("""
            SELECT * FROM information_schema.TABLES 
            WHERE table_name = :table_name AND table_schema = :table_schema
        """),
        con=engine,
        params={"table_name": table, "table_schema": database},
    )
    return result.shape[0] > 0


test = []

if __name__ == "__main__":
    # # engine = get_engine('wy', 'test', 'ods')
    # engine = get_engine(
    #         username='root', database='octopus')

    # data = pd.DataFrame(data=[{
    #             'title': 'test',
    #             'title_url': 'test'
    #         }])
    # # res = data.to_sql(con=engine, name=table)
    # res = data.to_sql(con=engine, name='octopus_ods_2024_09_21', if_exists='append', index=False)
    # print(res)

    engine_pg = get_engine_pg(database="mindsite_lark")
    data = pd.read_sql("SELECT * from ms_operate_event limit 1", con=engine_pg)
    print(data)
