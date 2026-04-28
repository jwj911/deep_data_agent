import os
import logging
from logging.handlers import TimedRotatingFileHandler
from utils.tools import get_root_path
import time

def init_log(log_name='default'):
    log_name = '{}.log'.format(log_name)
    log_dir = os.path.join(get_root_path(), 'log')
    log_path = os.path.join(log_dir, log_name)

    if not os.path.exists(log_dir):
        os.mkdir(log_dir)

    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)

    # 避免重复添加 handler，如果 logger 已经有 handler 则直接返回
    if logger.handlers:
        return logger

    handler = TimedRotatingFileHandler(
        filename=log_path, when='MIDNIGHT', interval=1, backupCount=30)
    fmt = "[%(asctime)s] [%(process)d] [%(levelname)s] - %(module)s.%(funcName)s (%(filename)s:%(lineno)d) - %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    handler.suffix = "%Y-%m-%d.log"
    logger.addHandler(handler)
    return logger


# 创建全局 logger 实例，可以直接导入使用
# 使用方式: from utils.log import logger
logger = init_log(log_name='global')
class TimingRecorder:
    """全局时间记录器，可以动态添加属性来记录各个时间点"""
    pass

timing_recorder = TimingRecorder()
timing_recorder.start = time.time()
timing_recorder.voice = "loongbella_v2"
timing_recorder.stop = False
timing_recorder.language = "en"


if __name__ == '__main__':
    logger = init_log(log_name='test')
    logger.info('test')
    logger.warning('warning')
    logger.error('error')